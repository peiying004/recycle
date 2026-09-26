import sensor, image, lcd, time
import os

lcd.init()
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.run(1)

# ==========================================
CLASS_NAME = "paper"  # 分類名稱
PHOTO_COUNT = 15      # 這次要拍張數
START_INDEX = 20      # 起始編號從 15 開始
# ==========================================

print("=== AI 資料收集相機 ===")
print("即將拍攝分類: [" + CLASS_NAME + "] (編號從 " + str(START_INDEX) + " 開始)")
print("5秒後開始，請把紙類放到鏡頭前準備...")
time.sleep(5)

# 使用 range 設定從 START_INDEX 開始，總共拍 PHOTO_COUNT 張
for i in range(START_INDEX, START_INDEX + PHOTO_COUNT):
    img = sensor.snapshot()
    lcd.display(img)

    # 組合出檔名 (例如 paper_15.jpg, paper_16.jpg ...)
    filename = "/flash/" + CLASS_NAME + "_" + str(i) + ".jpg"
    img.save(filename)

    # 計算目前的進度顯示
    current_progress = (i - START_INDEX) + 1
    print("已存檔: " + filename + " (" + str(current_progress) + "/" + str(PHOTO_COUNT) + ")")

    # 拍攝間隔 1.5 秒
    time.sleep(1.5)

print("🎉 本次拍攝完成！")
