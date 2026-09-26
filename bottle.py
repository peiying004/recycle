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

CLASS_NAME = "bottle"
PHOTO_COUNT = 15      # 這次要拍張數
START_INDEX = 15      # 起始編號從 15 開始


print("=== AI 資料收集相機 ===")
print("即將拍攝分類: [" + CLASS_NAME + "]")
print("5秒後開始，請把寶特瓶放到鏡頭前準備...")
time.sleep(5)
for i in range(START_INDEX, START_INDEX + PHOTO_COUNT):
    img = sensor.snapshot()
    lcd.display(img)
    filename = "/flash/" + CLASS_NAME + "_" + str(i) + ".jpg"
    img.save(filename)
    print("已存檔: " + filename + " (" + str(i+1) + "/" + str(PHOTO_COUNT) + ")")
    time.sleep(1.5)

print("🎉 寶特瓶單組拍攝完成！請用左邊的檔案總管下載並刪除。")
