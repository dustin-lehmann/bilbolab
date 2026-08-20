import time

from core.utils.data import clamp
import core.hardware.rpi_gpio as gpio


# ======================================================================================================================
class _ServoAngleMixin:
    """Aci (derece) <-> duty cycle (%) donusumunu paylasir. Alt siniflar
    frequency/min_pulse_ms/max_pulse_ms/min_angle/max_angle alanlarini set eder."""

    def _angleToDutyCycle(self, angle: float) -> float:
        angle = clamp(angle, self.min_angle, self.max_angle)
        span = self.max_angle - self.min_angle
        pulse_ms = self.min_pulse_ms + (angle - self.min_angle) / span * (self.max_pulse_ms - self.min_pulse_ms)
        period_ms = 1000.0 / self.frequency
        return pulse_ms / period_ms * 100.0

    def getAngle(self) -> float | None:
        return self._current_angle


# ======================================================================================================================
class Servo(_ServoAngleMixin):
    """
    Standart hobi servosu (SG90 vb.) icin YAZILIM PWM tabanli aci kontrolu
    (RPi.GPIO uzerinden). Herhangi bir GPIO pininde calisir ama sinyal, ana
    islemcinin zamanlamasina baglidir - ayni anda agir CPU isi (ornegin
    OpenCV/kamera goruntu isleme) calisirsa titreme (jitter) gorulebilir.
    Bu durumda GPIO18/19 uzerinde HardwareServo kullanin.

    50 Hz'lik (20 ms periyot) bir sinyalin HIGH kaldigi sure (pulse genisligi)
    ile pozisyonlanir. Tipik SG90 araligi ~0.5 ms (0 derece) ile ~2.5 ms
    (180 derece) arasidir - gercek servonuz farkli olabilir, gerekirse
    min_pulse_ms/max_pulse_ms degerlerini kalibre edin.
    """

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, pin: int, frequency: int = 50,
                 min_pulse_ms: float = 0.5, max_pulse_ms: float = 2.5,
                 min_angle: float = 0.0, max_angle: float = 180.0):
        self.pin = pin
        self.frequency = frequency
        self.min_pulse_ms = min_pulse_ms
        self.max_pulse_ms = max_pulse_ms
        self.min_angle = min_angle
        self.max_angle = max_angle

        self._current_angle = None
        self._pwm = gpio.pwm_setup(pin, frequency)
        self._pwm.start(0)

    # ------------------------------------------------------------------------------------------------------------------
    def setAngle(self, angle: float, settle_time: float = 0.3):
        """Servoyu verilen aciya (derece) hareket ettirir ve sinyali göndermeye
        devam eder (tutma torku icin). settle_time > 0 ise, servo fiilen o
        aciya ulasana kadar (yaklasik) bloklar."""
        duty_cycle = self._angleToDutyCycle(angle)
        self._pwm.ChangeDutyCycle(duty_cycle)
        self._current_angle = angle
        if settle_time > 0:
            time.sleep(settle_time)

    # ------------------------------------------------------------------------------------------------------------------
    def release(self):
        """Sinyali keser (duty_cycle=0) - servo artik tutma torku uygulamaz,
        pozisyonunu kaybedebilir ama titreme/uultu durur."""
        self._pwm.ChangeDutyCycle(0)

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self._pwm.stop()


# ======================================================================================================================
class HardwareServo(_ServoAngleMixin):
    """
    GPIO19 icin DONANIM PWM tabanli aci kontrolu (RP1/SoC PWM cevre birimi
    uzerinden, rpi-hardware-pwm paketiyle).

    Sinyal dogrudan donanim tarafindan uretildigi icin ana islemcideki CPU
    yukunden (kamera/OpenCV isleme vb.) ETKILENMEZ - Servo sinifinin aksine
    titreme (jitter) yasanmaz.

    ON KOSUL: /boot/firmware/config.txt icinde ilgili PWM overlay'i aktif
    olmali:
        dtoverlay=pwm,pin=19,func=2
    ve Pi yeniden baslatilmis olmali. NOT: bu Pi (CM5/RP1) icin GPIO19,
    pwmchip0 uzerinde donanimsal olarak kanal 3'e (PWM0_CHAN3) denk geliyor -
    "pwm-2chan" overlay'i ile beklenen sirali 0/1 eslemesi (klasik BCM2711
    davranisi) RP1'de calismadigi icin tek kanalli "pwm" overlay'i ve
    dogrudan sysfs testiyle (pinctrl get 19) dogrulanan kanal kullanildi.
    """

    _PIN_TO_CHANNEL = {19: 3}

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, pin: int, chip: int = 0, frequency: int = 50,
                 min_pulse_ms: float = 0.5, max_pulse_ms: float = 2.5,
                 min_angle: float = 0.0, max_angle: float = 180.0):
        if pin not in self._PIN_TO_CHANNEL:
            raise ValueError(
                f"HardwareServo su an sadece GPIO19'u destekler (config.txt'de dtoverlay=pwm,pin=19,func=2 aktif), verilen pin: {pin}. "
                f"Baska bir pin icin yazilim tabanli Servo sinifini kullanin.")

        from rpi_hardware_pwm import HardwarePWM  # sadece Pi'de mevcut, importu burada gecikmeli yap

        self.pin = pin
        self.frequency = frequency
        self.min_pulse_ms = min_pulse_ms
        self.max_pulse_ms = max_pulse_ms
        self.min_angle = min_angle
        self.max_angle = max_angle

        self._current_angle = None
        self._pwm = HardwarePWM(pwm_channel=self._PIN_TO_CHANNEL[pin], hz=frequency, chip=chip)
        self._pwm.start(0)

    # ------------------------------------------------------------------------------------------------------------------
    def setAngle(self, angle: float, settle_time: float = 0.3):
        duty_cycle = self._angleToDutyCycle(angle)
        self._pwm.change_duty_cycle(duty_cycle)
        self._current_angle = angle
        if settle_time > 0:
            time.sleep(settle_time)

    # ------------------------------------------------------------------------------------------------------------------
    def release(self):
        self._pwm.change_duty_cycle(0)

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self._pwm.stop()
