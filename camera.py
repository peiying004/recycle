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

# ==========================================
CLASS_NAME = "background"
PHOTO_COUNT = 15 # 配合內部空間，降為 15 張
# ==========================================

print("=== AI 資料收集相機 (內部空間模式) ===")
print("即將拍攝: [" + CLASS_NAME + "]")
print("5秒後開始，請準備...")
time.sleep(5)

for i in range(PHOTO_COUNT):
    img = sensor.snapshot()
    lcd.display(img)
    # 存檔路徑改為內建記憶體
    filename = "/flash/" + CLASS_NAME + "_" + str(i) + ".jpg"
    img.save(filename)
    print("已存檔: " + filename + " (" + str(i+1) + "/" + str(PHOTO_COUNT) + ")")

    time.sleep(1.5)

print("🎉 單組拍攝完成！請記得將照片下載到 Mac。")
