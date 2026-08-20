# =====================================================================================
#  Servonun hangi GPIO pinine lehimlendigini bulmak icin tarama scripti.
#  Sirayla adaylardaki her pine kisa bir "0 -> 90 -> 0" servo hareketi gonderir.
#  Servo hangi pin test edilirken fiziksel olarak oynarsa, dogru pin odur.
#
#  SPI (STM32 haberlesmesi: GPIO7/8/9/10/11), I2C (IO expander: GPIO2/3) ve
#  bazi board revizyonlarinda kullanilan dahili pinler (GPIO5/6/16) ile UART
#  (GPIO14/15) listeye DAHIL EDILMEDI - onlar zaten baska islerde kullaniliyor.
# =====================================================================================
import time

from hardware.hardware.servo import Servo

CANDIDATE_PINS = [4, 12, 13, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]


def test_pin(pin: int):
    print(f"\n=== GPIO{pin} test ediliyor (servo simdi oynarsa: dogru pin = {pin}) ===")
    try:
        servo = Servo(pin=pin)
    except Exception as e:
        print(f"  GPIO{pin}: kullanilamiyor / baska bir seye ayrilmis ({e})")
        return

    try:
        servo.setAngle(0, settle_time=0.4)
        servo.setAngle(90, settle_time=0.4)
        servo.setAngle(0, settle_time=0.4)
    except Exception as e:
        print(f"  GPIO{pin}: hareket sirasinda hata ({e})")
    finally:
        servo.release()
        servo.stop()

    time.sleep(0.4)


def main():
    print("Servoyu izleyin. Hangi GPIO numarasi yazarken servo oynadiysa, o pin dogru pindir.\n")
    for pin in CANDIDATE_PINS:
        test_pin(pin)
    print("\nTarama bitti. Servo hangi GPIO'da hareket ettiyse bana onu soyleyin.")


if __name__ == "__main__":
    main()
