import sensor, image, lcd, time
import KPU as kpu
import gc
from machine import Timer, PWM

# ================= 1. 初始化馬達 =================
SERVO_PIN = 9

tim = Timer(Timer.TIMER0, Timer.CHANNEL0, mode=Timer.MODE_PWM)
servo = PWM(tim, freq=50, duty=7.5, pin=SERVO_PIN)

current_angle = 90
pause_motor_until = 0  # 新增：馬達罷工計時器

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

        # 畫上文字 (這次相機保持運作，絕對看得見)
        img.draw_string(10, 10, label_text, scale=2, color=(0, 255, 0))
        img.draw_string(10, 35, cat_text, scale=2, color=(255, 0, 0))
        lcd.display(img)

        # ================= 4. 馬達平滑分流與防重複觸發邏輯 =================
        if category_text in ["Recycle (回收)", "General (一般垃圾)"]:

            # 如果是 bottle，設定馬達未來 20 秒內不准動
            if raw_label == 'bottle' and time.time() > pause_motor_until:
                print("=> 偵測到 bottle！相機保持運作，馬達暫停 20 秒讓你截圖！")
                pause_motor_until = time.time() + 20

            # 檢查是否超過了暫停時間
            if time.time() >= pause_motor_until:
                if category_text == "Recycle (回收)":
                    move_servo_slowly(150, delay_ms=30)
                else:
                    move_servo_slowly(30, delay_ms=30)

                time.sleep(1.0)
                move_servo_slowly(90, delay_ms=10)
                time.sleep(0.5)

                for _ in range(15):
                    sensor.snapshot()
            else:
                # 在這 20 秒內，馬達什麼都不做，直接跳過 (讓畫面保持高 FPS 更新)
                pass

        del img_kpu
        gc.collect()

except Exception as e:
    print("發生錯誤:", e)
finally:
    kpu.deinit(task)
