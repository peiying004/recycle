"""
flash_model.py
功能：透過串口與 K210 MicroPython REPL 交談，將 kmodel 模型以分塊 Base64 串流寫入板載 Flash。
使用前請確保已安裝 pyserial: pip install pyserial
"""

import serial
import serial.tools.list_ports
import time
import base64
import sys
import hashlib
import os
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="K210 模型板載 Flash 燒錄工具 (Base64 Chunked Flash Streaming)"
    )
    parser.add_argument("--port", type=str, default=None, help="序列埠號 (例如: COM7 或 /dev/ttyUSB0，未指定時將自動偵測)")
    parser.add_argument("--baud", type=int, default=115200, help="序列埠傳輸鮑率 (預設: 115200)")
    parser.add_argument("--model", type=str, default="model-320331.kmodel", help="目標 .kmodel 檔案路徑 (預設: model-320331.kmodel)")
    parser.add_argument("--dest", type=str, default=None, help="晶片端目標檔案路徑 (預設: /flash/<model_name>)")
    return parser.parse_args()

def resolve_serial_port(requested_port):
    if requested_port:
        return requested_port

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("[!] 錯誤：未偵測到任何連接的序列埠，請確認 Maix Bit 開發板已連接至電腦！")
        sys.exit(1)

    if len(ports) == 1:
        selected = ports[0].device
        print(f"[*] 自動偵測並選用序列埠: {selected} ({ports[0].description})")
        return selected

    print("[*] 偵測到多個可用序列埠，請選擇：")
    for idx, p in enumerate(ports):
        print(f"  [{idx}] {p.device} - {p.description}")
    try:
        choice = int(input("請輸入序列埠編號: ").strip())
        if not 0 <= choice < len(ports):
            raise IndexError
        return ports[choice].device
    except (ValueError, IndexError):
        print("[!] 輸入無效，操作已取消。")
        sys.exit(1)

def resolve_model_file(model_path):
    if os.path.exists(model_path):
        return os.path.abspath(model_path)

    parent_check = os.path.join("..", model_path)
    if os.path.exists(parent_check):
        return os.path.abspath(parent_check)

    model_name = os.path.basename(model_path)
    model_stem = os.path.splitext(model_name)[0]
    download_candidates = (
        os.path.expanduser(os.path.join("~", "Downloads", model_name)),
        os.path.expanduser(os.path.join("~", "Downloads", model_stem, model_name)),
    )
    for candidate in download_candidates:
        if os.path.exists(candidate):
            print(f"[*] 自動於下載目錄找到模型: {candidate}")
            return candidate

    print(f"[!] 錯誤：找不到模型檔案 {model_path}")
    sys.exit(1)

# 1. 解析命令列參數與自動解析路徑/埠號
args = parse_arguments()
COM_PORT = resolve_serial_port(args.port)
BAUD_RATE = args.baud
KMODEL_PATH = resolve_model_file(args.model)
dest_filename = args.dest if args.dest else f"/flash/{os.path.basename(KMODEL_PATH)}"

with open(KMODEL_PATH, "rb") as f:
    kmodel_data = f.read()

total_bytes = len(kmodel_data)
if total_bytes == 0:
    print(f"[!] 錯誤：模型檔案是空的：{KMODEL_PATH}")
    sys.exit(1)

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
print(f"[*] 正在初始化晶片 Flash 寫入環境：{dest_filename} ...")
execute("import ubinascii, os, gc")
execute("gc.collect()")

execute(f"f = open({dest_filename!r}, 'wb')")
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
stat_res = execute(f"print('FLASH_SIZE:', os.stat({dest_filename!r})[6])")
print(stat_res)

if f"FLASH_SIZE: {total_bytes}" not in stat_res:
    print(f"[!] 板端檔案大小校驗失敗，預期為 {total_bytes} bytes。")
    s.close()
    sys.exit(1)

print("[*] 呼叫 K210 硬體 KPU 加載測試：")
execute("import KPU as kpu")
load_res = execute(f"task = kpu.load({dest_filename!r}); print('KPU_LOAD_RESULT:', task); kpu.deinit(task)")
print(load_res)

if "Traceback" in load_res or "Error" in load_res:
    print("[!] KPU 加載測試失敗，請依照上方訊息檢查模型與韌體版本。")
    s.close()
    sys.exit(1)

print("\n=== 模型已成功常駐於晶片內部 Flash，可直接供 main.py 調用 ===")
s.close()
