import sensor, image, lcd, time
import os

lcd.init()
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.run(1)

for f in os.listdir('/flash/'):
    if f.endswith('.jpg'):
        os.remove('/flash/' + f)
print("照片已完全清空！")

CLASS_NAME = "tissue"  # 分類名稱改為 tissue (衛生紙團)
PHOTO_COUNT = 15       # 一次拍 15 張

print("=== AI 資料收集相機 ===")
print("即將拍攝分類: [" + CLASS_NAME + "]")
print("5秒後開始，請把衛生紙團放到鏡頭前準備...")
time.sleep(5)

for i in range(PHOTO_COUNT):
    img = sensor.snapshot()
    lcd.display(img)
    filename = "/flash/" + CLASS_NAME + "_" + str(i) + ".jpg"
    img.save(filename)
    print("已存檔: " + filename + " (" + str(i+1) + "/" + str(PHOTO_COUNT) + ")")

    # 拍攝間隔 1.5 秒，可以稍微翻轉一下衛生紙團
    time.sleep(1.5)

print("🎉 衛生紙單組拍攝完成！請用左邊的檔案總管下載並刪除。")
