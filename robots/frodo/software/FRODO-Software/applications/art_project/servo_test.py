# =====================================================================================
#  Bagimsiz servo donanim testi - robotu calistirmaz, sadece PWM/servo pinini dogrular.
#  Once bunu calistirip servonun duzgun 0 -> 90 -> 180 -> 0 hareket ettigini gorun,
#  sonra servo_aruco_trigger.py'a gecin.
# =====================================================================================
import time

from hardware.hardware.servo import HardwareServo

SERVO_PIN = 19  # BCM GPIO19 (fiziksel pin 35, PWM1) - servo_pin_scan.py
                # taramasiyla dogrulandi (servo bu pinde hareket etti).
                # HardwareServo icin /boot/firmware/config.txt'de
                # "dtoverlay=pwm-2chan,pin=18,func=2,pin2=19,func2=2" aktif
                # ve Pi yeniden baslatilmis olmali.


def main():
    servo = HardwareServo(pin=SERVO_PIN)
    try:
        for angle in (0, 90, 180, 90, 0):
            print(f"-> {angle} derece")
            servo.setAngle(angle, settle_time=1.0)
    finally:
        servo.release()
        servo.stop()
        print("Test bitti.")


if __name__ == "__main__":
    main()
