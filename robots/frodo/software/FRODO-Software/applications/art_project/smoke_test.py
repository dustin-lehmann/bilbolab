# =====================================================================
#  ADIM 0 - SMOKE TEST
#  Amac: estimation API'si gercekten calisiyor mu? Alan isimleri dogru mu?
#        Encoder bias'i var mi? Ornekleme hizi kac Hz?
#  MOTORLAR HIC CALISMAZ. Robot masada, tekerlekler bosta olabilir.
# =====================================================================
import time
import numpy as np

from robot.frodo import FRODO


def main():
    frodo = FRODO()
    frodo.init()
    frodo.start()
    time.sleep(1.0)          # sensorler otursun

    # -----------------------------------------------------------------
    # 1) ALAN ISIMLERINI KESFET
    #    Hoca iskeleti hizli yazdi; isimler farkli olabilir.
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("1) API KESFI")
    print("=" * 60)

    sample = frodo.estimation.getSample()
    print(f"getSample() tipi : {type(sample).__name__}")
    print(f"  alanlar        : {[a for a in dir(sample) if not a.startswith('_')]}")

    if not hasattr(sample, "lowlevel_data"):
        print("\n!!! 'lowlevel_data' YOK. Yukaridaki alan listesine bak,")
        print("    hiz bilgisi hangi alanda? Scripti ona gore duzelt.")
        return

    ll = sample.lowlevel_data
    print(f"\nlowlevel_data tipi : {type(ll).__name__}")
    print(f"  alanlar          : {[a for a in dir(ll) if not a.startswith('_')]}")

    for name in ("speed_left", "speed_right"):
        if not hasattr(ll, name):
            print(f"\n!!! '{name}' YOK. Yukaridaki listeden dogru ismi bul.")
            return

    print("\n--> speed_left / speed_right mevcut. Devam.")

    # -----------------------------------------------------------------
    # 2) BIAS + ORNEKLEME HIZI  (robot TAMAMEN hareketsiz)
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("2) BIAS OLCUMU  -  robota DOKUNMA, 5 saniye")
    print("=" * 60)
    input("Hazir oldugunda ENTER...")

    left, right, stamps = [], [], []
    t0 = time.time()
    while time.time() - t0 < 5.0:
        d = frodo.estimation.getSample().lowlevel_data
        left.append(d.speed_left)
        right.append(d.speed_right)
        stamps.append(time.time())
        time.sleep(0.005)

    left = np.array(left, dtype=float)
    right = np.array(right, dtype=float)
    dts = np.diff(np.array(stamps))

    print(f"\n  ornek sayisi   : {len(left)}")
    print(f"  ornekleme hizi : {1.0 / dts.mean():.1f} Hz  "
          f"(dt ort={dts.mean()*1000:.2f} ms, max={dts.max()*1000:.2f} ms)")
    print(f"\n  SOL   ort={left.mean():+.6f}  std={left.std():.6f}  "
          f"min={left.min():+.4f}  max={left.max():+.4f}")
    print(f"  SAG   ort={right.mean():+.6f}  std={right.std():.6f}  "
          f"min={right.min():+.4f}  max={right.max():+.4f}")

    bias_limit = 1e-4
    if abs(left.mean()) > bias_limit or abs(right.mean()) > bias_limit:
        print("\n  !!! BIAS VAR. Bu degerleri NOT AL - Kalman'da lazim olacak.")
        print(f"      bias_left = {left.mean():+.6f}")
        print(f"      bias_right= {right.mean():+.6f}")
    else:
        print("\n  --> Bias ihmal edilebilir. Iyi.")

    print(f"\n  Olcum gurultusu std: sol={left.std():.6f}  sag={right.std():.6f}")
    print("  (Bu sayilar da Adim 3'te Q matrisi icin ipucu.)")

    # -----------------------------------------------------------------
    # 3) ELLE CEVIRME  -  sensor gercekten tepki veriyor mu?
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("3) ELLE CEVIRME  -  15 saniye boyunca paletleri elinle cevir")
    print("=" * 60)
    print("ONEMLI: once SADECE SOL, sonra SADECE SAG paleti cevir.")
    print("Boylece hangi degerin hangi palete ait oldugunu dogrularsin.")
    input("Hazir oldugunda ENTER...")

    peak_l = peak_r = 0.0
    t0 = time.time()
    t_print = t0
    while time.time() - t0 < 15.0:
        d = frodo.estimation.getSample().lowlevel_data
        peak_l = max(peak_l, abs(d.speed_left))
        peak_r = max(peak_r, abs(d.speed_right))
        now = time.time()
        if now - t_print > 0.25:
            t_print = now
            print(f"  sol={d.speed_left:+9.4f}   sag={d.speed_right:+9.4f}")
        time.sleep(0.01)

    print(f"\n  tepe degerler: sol={peak_l:.4f}   sag={peak_r:.4f}")
    print("\n  BIRIM TAHMINI (elle cevirme yavas oldugu icin sadece fikir verir):")
    print("    ~0.05-0.3   -> m/s")
    print("    ~1-10       -> rad/s  (tekerlek acisal hizi)")
    print("    >50         -> tick/s veya RPM")
    print("\n  Kesin cevap calib_odom.py TEST 1'den gelecek.")

    print("\n" + "=" * 60)
    print("SMOKE TEST BITTI. Sonuclari not al, calib_odom.py'ye gec.")
    print("=" * 60)


if __name__ == "__main__":
    main()