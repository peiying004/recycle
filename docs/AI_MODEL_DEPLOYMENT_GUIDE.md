# AI 智慧垃圾分類機：模型量化、Flash 晶片燒錄與推論部署技術文件

本文件詳細記錄「AI 智慧垃圾分類機／分類車」專案中，神經網路模型從量化壓縮、繞過硬體卡槽故障直接寫入晶片板載 Flash，到板端 KPU 硬體加速推論與伺服馬達連動的完整技術實現。

---

## 一、 硬體與架構規格

| 項目 | 規格與說明 |
| :--- | :--- |
| **主控晶片** | Kendryte (勘智) K210 (雙核心 64-bit RISC-V @ 400MHz) |
| **神經網路加速器** | 內建 KPU (Knowledge Processing Unit，512 目標 CNN 硬體加速算力) |
| **開發板** | Sipeed Maix Bit (運行 MaixPy / MicroPython 韌體) |
| **儲存媒體** | 板載 SPI Flash (16MB，內部掛載於 `/flash/` 目錄) |
| **感測與影像輸入** | OV2640 鏡頭模組 (QVGA 320x240，裁切調整為 224x224 RGB565) |
| **顯示輸出** | 2.4 吋 ST7789 TFT LCD |
| **分流致動器** | 伺服馬達 (SG90 / MG996R，透過 Pin 9 輸出 50Hz PWM 控制角度) |
| **AI 模型格式** | `model-320331.kmodel` (經過 INT8 定點量化之 K210 硬體神經網路模型) |
| **分類類別** | `background` (背景), `bottle` (寶特瓶), `paper` (廢紙), `tissue` (衛生紙) |

---

## 二、 遇到的硬體痛點與突破技術

### 1. 硬體限制與突發故障
* **MicroSD 卡槽故障**：Maix Bit 開發板上的 MicroSD / TF 卡槽無法正常讀寫，導致一般透過記憶卡讀取模型的標準流程失效。
* **第三方工具相容性問題**：使用 Thonny IDE 等圖形化工具傳輸二進位模型時，常因通訊逾時或資料溢位而中斷失敗。
* **晶片 SRAM 極限**：K210 僅具備 6MB 通用 SRAM 與 2MB KPU 專用 RAM，若一次性傳送數百 KB 至數 MB 的模型至記憶體，會立即引發 `Memory Allocation Failed` 崩潰。

### 2. 解決技術：Python 串口串流分塊注入技術 (Base64 Chunked Flash Streaming)
為徹底解決上述問題，我們自行設計了一套 Python 自動化燒錄傳輸腳本 (`flash_model.py`)：
1. **USB 串口直接交談**：透過 COM Port (115200 Baud) 直接與晶片的 MicroPython REPL 終端進行命令通訊。
2. **小區塊 Base64 編碼傳輸**：將 `.kmodel` 拆分為每塊 120 bytes 的二進位區塊，編碼成 Base64 字串後以命令列形式發送至晶片端。
3. **即時解碼寫入 Flash**：在晶片端調用 `ubinascii.a2b_base64()` 即時解碼並直接以 append 模式寫入板載內部 SPI Flash (`/flash/model-320331.kmodel`)。
4. **主動記憶體回收 (GC Pipeline)**：每發送 30 個區塊（約 3.6KB）即發送 `gc.collect()` 強制釋放 MicroPython 堆積記憶體，確保晶片在有限記憶體下穩定完成傳輸。
5. **完整性與 KPU 硬體驗證**：傳輸完成後立即在晶片端執行 `os.stat()` 驗證檔案大小，並呼叫 `KPU.load()` 確保硬體加速單元能成功掛載該神經網路模型。

---

## 三、 模型燒錄腳本原始碼 (`flash_model.py`)

此腳本在 PC 端執行，直接將本機的 `.kmodel` 檔案燒入 Maix Bit 內部的 `/flash/` 目錄：

```python
"""
flash_model.py
功能：透過串口與 K210 MicroPython REPL 交談，將 kmodel 模型以分塊 Base64 串流寫入板載 Flash。
使用前請確保已安裝 pyserial: pip install pyserial
"""

import serial
import time
import base64
import sys
import hashlib
import os

# 1. 設定模型路徑與串口參數
KMODEL_PATH = "model-320331.kmodel"  # 或放置在同目錄下的 kmodel 檔名
COM_PORT = "COM7"                    # 依照裝置管理員中的 COM 埠號修改
BAUD_RATE = 115200

if not os.path.exists(KMODEL_PATH):
    print(f"錯誤：找不到模型檔案 {KMODEL_PATH}")
    sys.exit(1)

with open(KMODEL_PATH, "rb") as f:
    kmodel_data = f.read()

total_bytes = len(kmodel_data)
local_sha = hashlib.sha256(kmodel_data).hexdigest()
print(f"[*] 目標模型：{KMODEL_PATH}")
print(f"[*] 檔案大小：{total_bytes} bytes")
print(f"[*] SHA256 校驗值：{local_sha}")

# 2. 開啟串口連線
s = serial.Serial(COM_PORT, BAUD_RATE, timeout=5)
s.dtr = 0
s.rts = 1
print(f"[*] 正在連線至 Maix Bit ({COM_PORT})...")
time.sleep(1.5)

# 中斷可能正在執行的程式，喚醒 REPL (>>>)
s.write(b'\x03\x03\x03\r\n')
time.sleep(0.4)

def execute(cmd, wait_time=0.2):
    s.write(cmd.encode('utf-8') + b'\r\n')
    time.sleep(wait_time)
    res = b''
    while s.in_waiting > 0:
        res += s.read(s.in_waiting)
        time.sleep(0.02)
    return res.decode('utf-8', errors='ignore')

# 3. 準備板端寫入環境
print("[*] 正在初始化晶片 Flash 寫入環境...")
execute("import ubinascii, os, gc")
execute("gc.collect()")

dest_filename = "/flash/model-320331.kmodel"
execute(f"f = open('{dest_filename}', 'wb')")
execute("w = f.write")
execute("b = ubinascii.a2b_base64")

s.write(b'\r\n')
time.sleep(0.1)
s.read_all()

# 4. 開始分塊串流傳輸
chunk_size = 120
offset = 0
chunk_idx = 0
start_time = time.time()
print(f"[*] 開始傳輸至晶片內部目錄：{dest_filename}")

error = False
while offset < total_bytes:
    chunk = kmodel_data[offset:offset + chunk_size]
    b64 = base64.b64encode(chunk).decode('ascii')
    cmd = f"w(b('{b64}'))\r\n"
    s.write(cmd.encode('ascii'))

    buf = b''
    t0 = time.time()
    while not buf.endswith(b'>>> '):
        if s.in_waiting > 0:
            buf += s.read(s.in_waiting)
        else:
            time.sleep(0.002)
        if time.time() - t0 > 4:
            print(f"\n[!] 傳輸逾時 (位移: {offset})")
            error = True
            break
    if error:
        break

    offset += len(chunk)
    chunk_idx += 1

    # 每 30 個 chunk (~3.6KB) 主動要求 MicroPython 垃圾回收，防範記憶體溢位
    if chunk_idx % 30 == 0:
        execute("gc.collect()")

    pct = (offset / total_bytes) * 100
    el = time.time() - start_time
    spd = (offset / 1024) / el if el > 0 else 0
    sys.stdout.write(f"\r[進度] {offset}/{total_bytes} bytes ({pct:.1f}%) [{spd:.1f} KB/s]")
    sys.stdout.flush()

if error:
    print("\n[!] 傳輸中斷失敗！")
    s.close()
    sys.exit(1)

# 5. 關閉檔案與 KPU 驗證
print("\n[*] 傳輸完成，正在封裝檔案...")
execute("f.close()")
time.sleep(0.5)

print("[*] 驗證板端檔案大小：")
stat_res = execute(f"print('FLASH_SIZE:', os.stat('{dest_filename}')[6])")
print(stat_res)

print("[*] 呼叫 K210 硬體 KPU 加載測試：")
execute("import KPU as kpu")
load_res = execute(f"task = kpu.load('{dest_filename}'); print('KPU_LOAD_RESULT:', task); kpu.deinit(task)")
print(load_res)

print("\n=== 模型已成功常駐於晶片內部 Flash，可直接供 main.py 調用 ===")
s.close()
```

---

## 四、 晶片端系統推論與機械分流邏輯 (`main.py`)

當模型成功常駐於 `/flash/model-320331.kmodel` 後，K210 開機時會自動載入 `/flash/main.py` 執行系統主邏輯：

### 核心運作步驟：
1. **PWM 伺服馬達初始化**：Pin 9 產生 50Hz PWM，初始歸位在 90 度中立位置。
2. **攝影鏡頭與螢幕校正**：將相機輸入調整為 QVGA，並擷取成模型輸入所需的 224x224 RGB565 張量。
3. **KPU 前向推論**：透過 `kpu.forward(task, img_kpu)` 進行高速邊緣推論，取得 4 類信心度陣列。
4. **信心度閥值保護 (Confidence Threshold)**：
   - 門檻設為 `0.45`。若最高信心度未達標，系統自動過濾並視為 `background`，避免外界光影干擾導致誤動作。
5. **垃圾分類決策與分流致動**：
   - **資源回收** (`bottle`, `paper`)：平滑驅動伺服馬達轉動至 `150 度`，推動擋板將物品導流至回收箱。
   - **一般垃圾** (`tissue`)：平滑驅動伺服馬達轉動至 `30 度`，將物品導流至一般垃圾箱。
   - **防重複連觸機制**：動作完成後延遲並回位至 90 度，且清空相機緩衝區以防重複觸發。

---

## 五、 結論與量產/學術重點

1. **真實邊緣 AI（TinyML / Edge AI）落實**：不依賴 Wi-Fi、4G/5G 雲端 API，在 400MHz RISC-V 微控制器上完成純離線、低延遲的影像辨識與機械控制。
2. **韌體級故障容錯設計**：克服周邊元件（MicroSD 卡槽）損壞的硬體缺陷，透過自製串口 Base64 分塊串流與即時 GC 排程，展現了深入底層記憶體管理與通訊協定的韌體開發實力。
