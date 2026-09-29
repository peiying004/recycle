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
