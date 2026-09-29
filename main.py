import sensor, image, lcd, time
import KPU as kpu
import gc
from machine import Timer, PWM

# ================= 1. 初始化馬達 =================
SERVO_PIN = 9

tim = Timer(Timer.TIMER0, Timer.CHANNEL0, mode=Timer.MODE_PWM)
servo = PWM(tim, freq=50, duty=7.5, pin=SERVO_PIN)

current_angle = 90

def set_servo_angle(angle):
    global current_angle
    duty = 2.5 + (angle / 180.0) * 10
    servo.duty(duty)
    current_angle = angle

def move_servo_slowly(target_angle, delay_ms=15):
    global current_angle
    step = 1 if target_angle > current_angle else -1

    for a in range(current_angle, target_angle + step, step):
        duty = 2.5 + (a / 180.0) * 10
        servo.duty(duty)
        time.sleep_ms(delay_ms)

    current_angle = target_angle

set_servo_angle(90)
time.sleep(1)

# ================= 2. 初始化螢幕與相機 =================
lcd.init()
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.run(1)

# ================= 3. 載入模型 =================
task = kpu.load("/flash/model-320331.kmodel")
labels = ['background', 'bottle', 'paper', 'tissue']
print("=== AI 垃圾分類機啟動成功 ===")

try:
    while True:
        img = sensor.snapshot()
        img_kpu = img.resize(224, 224)
        img_kpu.pix_to_ai()

        fmap = kpu.forward(task, img_kpu)
        plist = fmap[:]
        pmax = max(plist)
        max_index = plist.index(pmax)

        raw_label = labels[max_index]

        # 信心門檻：低於 0.45 直接強制歸零為 background
        if pmax < 0.45:
            raw_label = 'background'

        if raw_label == 'background':
            category_text = "Background"
        elif raw_label in ['bottle', 'paper']:
            category_text = "Recycle (回收)"
        elif raw_label == 'tissue':
            category_text = "General (一般垃圾)"
        else:
            category_text = "Unknown"

        label_text = "Label: %s (%.2f)" % (raw_label, pmax)
        cat_text = "Type: %s" % category_text

        # 在 LCD 即時顯示標籤、信心值與分類結果
        img.draw_string(10, 10, label_text, scale=2, color=(0, 255, 0))
        img.draw_string(10, 35, cat_text, scale=2, color=(255, 0, 0))
        lcd.display(img)

        # ================= 4. 馬達平滑分流與防重複觸發邏輯 =================
        if category_text in ["Recycle (回收)", "General (一般垃圾)"]:
            print("=> 偵測到 %s，分流至 %s" % (raw_label, category_text))

            # 緩步轉動可降低伺服馬達瞬間抽載，避免供電不穩
            if category_text == "Recycle (回收)":
                move_servo_slowly(150, delay_ms=30)   # 寶特瓶 / 紙類 -> 回收槽
            else:
                move_servo_slowly(30, delay_ms=30)    # 衛生紙 -> 一般垃圾槽

            time.sleep(1.0)
            move_servo_slowly(90, delay_ms=10)        # 回到中立位置
            time.sleep(0.5)

            # 丟棄殘留畫面，避免同一物體被重複觸發
            for _ in range(15):
                sensor.snapshot()

        del img_kpu
        gc.collect()

except Exception as e:
    print("發生錯誤:", e)
finally:
    kpu.deinit(task)
