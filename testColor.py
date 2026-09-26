import sensor, image, lcd, time
from machine import Timer, PWM

# --- 第一部分：硬體初始化 ---
lcd.init()
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.run(1)

# 初始化伺服馬達 (設定在 Pin 9)
tim = Timer(Timer.TIMER0, Timer.CHANNEL0, mode=Timer.MODE_PWM)
servo = PWM(tim, freq=50, duty=0, pin=9)

def set_servo_angle(angle):
    duty = ((angle / 180) * 10 + 2.5)
    servo.duty(duty)

current_angle = 90

# --- ✨ 緩步移動函數 ---
def slow_move(target_angle):
    global current_angle
    step = 1 if target_angle > current_angle else -1
    for angle in range(current_angle, target_angle + step, step):
        set_servo_angle(angle)
        time.sleep(0.015)
    current_angle = target_angle

slow_move(90)
time.sleep(1)

# --- 第二部分：主迴圈 ---
print("系統啟動，防斷線模式運作中！")

while True:
    img = sensor.snapshot()
    r, g, b = img.get_pixel(160, 120)

    print("目前中心顏色 - R:", r, " G:", g, " B:", b)

    classification_result = "未知"

    if r > 130 and g > 130 and b < 100:
        classification_result = "黃色"
        print("偵測到：黃色，向左推！")
        slow_move(45)
        time.sleep(1)
        slow_move(90)

    elif r > 100 and g > 100 and b > 100:
        classification_result = "白色"
        print("偵測到：白色，向右推！")
        slow_move(135)
        time.sleep(1)
        slow_move(90)

    img.draw_cross(160, 120, color=(0, 255, 0), size=10)
    img.draw_string(10, 10, classification_result, color=(255, 0, 0), scale=2)
    lcd.display(img)
