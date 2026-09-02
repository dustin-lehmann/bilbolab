# =====================================================================
#  ADIM 1-2 - ODOMETRI KALIBRASYONU
#  SURUM 2
#
#  DEGISIKLIKLER:
#    - Mesafe girdisi artik SANTIMETRE (metre/cm karisikligi bitsin)
#    - TEST 2 suresi 20 s -> 60 s (yaklasik 5 tur, aci hatasi bolunur)
#    - Yorum bolumleri cm/s birimlerine gore guncellendi
#    - Fiziksel ust sinir kontrolu eklendi
#
#  MANTIK:
#    K_SCALE = D_gercek[m] / integral(v_ham) dt
#    RADIUS  = integral(sR - sL) dt / delta_psi_gercek[rad]
#
#  RADIUS icin K_SCALE'e GEREK YOK - ham birimlerden dogrudan turetiliyor
#  ve palet kaymasini da icine yutuyor. Beklenen deger 25-35 civari
#  (geometrik iz genisligi 15 cm, kayma yuzunden buyuyor).
#
#  DIKKAT: Batarya DOLU olsun. Ayni zeminde, ayni oturusta yap.
# =====================================================================
import time
import numpy as np

from robot.frodo import FRODO
from robot.control.frodo_control import FRODO_ControlMode


# --------------------------------------------------------------------
def integrate_run(frodo, cmd_l, cmd_r, duration, progress=False):
    """Komutu uygula, geri beslemeyi GERCEK dt ile integre et.

    Donus:
      sum_mean : integral (sL+sR)/2 dt     -> mesafe (ham birim)
      sum_diff : integral (sR-sL)   dt     -> aci * RADIUS (ham birim)
      peak     : gorulen en buyuk mutlak hiz
      hz       : ornekleme hizi
    """
    sum_mean = 0.0
    sum_diff = 0.0
    peak = 0.0
    n = 0

    t0 = time.time()
    t_prev = t0
    t_prog = t0
    frodo.control.setTrackSpeed(cmd_l, cmd_r)
    try:
        while time.time() - t0 < duration:
            now = time.time()
            dt = now - t_prev
            t_prev = now
            if dt <= 0.0 or dt > 0.5:
                time.sleep(0.005)
                continue

            d = frodo.estimation.getSample().lowlevel_data
            sl, sr = d.speed_left, d.speed_right

            sum_mean += 0.5 * (sl + sr) * dt
            sum_diff += (sr - sl) * dt
            peak = max(peak, abs(sl), abs(sr))
            n += 1

            if progress and (now - t_prog) >= 5.0:
                t_prog = now
                print(f"    ... {now - t0:.0f} s")

            time.sleep(0.005)
    finally:
        frodo.control.setTrackSpeed(0.0, 0.0)

    T = time.time() - t0
    time.sleep(0.6)          # atalet sonsun
    return sum_mean, sum_diff, peak, (n / T if T > 0 else 0.0)


# --------------------------------------------------------------------
def summarize(name, values, unit=""):
    """3 tekrarin ortalamasi + sacilim. Sacilim buyukse uyar."""
    a = np.array(values, dtype=float)
    mean, std = a.mean(), a.std()
    spread = (std / abs(mean) * 100.0) if mean != 0 else float("inf")

    print(f"\n  {name}")
    for i, v in enumerate(a, 1):
        print(f"    #{i}: {v:.5f} {unit}")
    print(f"    ORTALAMA : {mean:.5f} {unit}")
    print(f"    sacilim  : {spread:.1f} %")
    if spread > 5.0:
        print("    !!! %5'ten fazla sacilim. Zemin kaygan olabilir")
        print("        veya olcumun tutarsiz. TEKRARLA.")
    else:
        print("    --> Kabul edilebilir.")
    return mean


# --------------------------------------------------------------------
def test1_straight(frodo, n_rep=3, duration=5.0, speed=0.08):
    print("\n" + "=" * 62)
    print("TEST 1 - DUZ SURUS  ->  K_SCALE")
    print("=" * 62)
    print("HAZIRLIK:")
    print("  - Robotun merkezine bir bant isareti yapistir")
    print("  - Duz, uzun bir alan sec")
    print("  - Seritmetre hazir olsun")
    print(f"  - Beklenen mesafe: ~{speed*duration*100:.0f} cm")

    scales = []
    for rep in range(1, n_rep + 1):
        print(f"\n--- Tekrar {rep}/{n_rep} ---")
        input("  Robotu baslangica koy, yere isaretle, ENTER...")

        mean, diff, peak, hz = integrate_run(frodo, speed, speed, duration)

        print(f"  ornekleme     : {hz:.0f} Hz")
        print(f"  geri besl.tepe: {peak:.4f}")
        print(f"  integral v dt : {mean:.4f}  [ham birim]")
        print(f"  integral fark : {diff:.4f}  (0'a yakin olmali - duz gitti mi?)")

        if abs(mean) < 1e-9:
            print("  !!! Integral ~0. Motorlar donmedi veya encoder okumuyor.")
            continue

        # ---- DIKKAT: SANTIMETRE ----
        D_cm = float(input("  Gercekte kac SANTIMETRE gitti? "))
        D = D_cm / 100.0

        # fiziksel ust sinir kontrolu
        d_max_cm = speed * duration * 100.0 * 1.5
        if D_cm > d_max_cm:
            print(f"  !!! {D_cm:.1f} cm, fiziksel ust sinir {d_max_cm:.0f} cm'den buyuk.")
            print("      Yanlislikla metre mi girdin? Tekrarla.")
            continue

        k = D / mean
        print(f"  --> k = {k:.6f}")
        scales.append(k)

    if not scales:
        return None

    k = summarize("K_SCALE", scales)

    print("\n  BIRIM YORUMU:")
    if 0.80 < k < 1.25:
        print("    k ~ 1      ->  hizlar m/s cinsinden.")
    elif 0.008 <= k <= 0.013:
        print("    k ~ 0.01   ->  hizlar cm/s cinsinden. (Beklenen sonuc.)")
    elif 0.015 < k < 0.080:
        print(f"    k = {k:.4f} ->  hizlar rad/s, k = tekerlek yaricapi (m).")
    else:
        print(f"    k = {k:.6f} ->  tick/s veya RPM olabilir. Hocaya sor.")
    return k


# --------------------------------------------------------------------
def test2_rotation(frodo, n_rep=3, duration=60.0, speed=0.08):
    print("\n" + "=" * 62)
    print("TEST 2 - YERINDE DONUS  ->  RADIUS")
    print("=" * 62)
    print("HAZIRLIK:")
    print("  - Robotun burnuna gorulebilir bir isaret koy")
    print("  - Yere de sabit bir referans isareti koy")
    print("  - TAM TUR sayisini gozle sayacaksin (yarim tur = 0.5)")
    print(f"\n  NEDEN {duration:.0f} SANIYE:")
    print("    Gercek acisal hiz ~0.5 rad/s, yani ~5 tur doner.")
    print("    Gozle acı okuma hatan (+-10 derece) tur sayisina bolunur.")
    print(f"\n  NEDEN {speed} m/s (hizlandirip kisaltma!):")
    print("    Efektif iz genisligi HIZA BAGLI - kayma hizla degisir.")
    print("    Kalibrasyonu, kullanacagin calisma noktasinda yap.")
    print("    TURN_SPEED de 0.08 olacak.")
    print("\n  BEKLENTI: RADIUS ~25-35 (geometrik iz genisligi 15 cm).")

    radii = []
    for rep in range(1, n_rep + 1):
        print(f"\n--- Tekrar {rep}/{n_rep} ---")
        input(f"  Robotu referansa hizala, ENTER ({duration:.0f} s donecek)...")
        print("  Tur saymaya basla:")

        # sol negatif, sag pozitif -> saat yonunun TERSI (CCW), psi artar
        mean, diff, peak, hz = integrate_run(frodo, -speed, speed, duration,
                                             progress=True)

        print(f"\n  integral (sR-sL) dt = {diff:.4f}")
        print(f"  integral v dt       = {mean:.4f}  (0'a yakin olmali)")

        if abs(diff) < 1e-9:
            print("  !!! Integral ~0. Donmedi.")
            continue

        N = float(input("  Kac TAM TUR dondu? (kesirli: 5.25) "))
        if N <= 0:
            print("  Gecersiz.")
            continue

        r = diff / (N * 2.0 * np.pi)
        print(f"  --> RADIUS = {r:.4f}")
        radii.append(r)

    if not radii:
        return None

    r = summarize("RADIUS", radii)

    print("\n  YORUM:")
    print(f"    Efektif iz genisligi = {r:.1f} cm")
    ratio = r / 15.0
    print(f"    Geometrik iz genisligine oran = {ratio:.2f}")
    if ratio > 1.4:
        print("    --> Beklendigi gibi: palet kaymasi var, efektif deger buyuk.")
    elif 0.9 < ratio <= 1.4:
        print("    --> Kayma az. Zemin tutuyor demektir, sorun degil.")
    else:
        print("    --> Geometrikten KUCUK. Bu tuhaf, tur sayimini kontrol et.")
    return r


# --------------------------------------------------------------------
def main():
    frodo = FRODO()
    frodo.init()
    frodo.start()
    frodo.control.setMode(FRODO_ControlMode.EXTERNAL)

    k = None
    r = None
    try:
        while True:
            print("\n" + "-" * 62)
            print("  [1] TEST 1 - duz    -> K_SCALE")
            print("  [2] TEST 2 - donus  -> RADIUS")
            print("  [s] sonuclari goster")
            print("  [q] cikis")
            c = input("  Secim > ").strip().lower()

            if c == "q":
                break
            elif c == "1":
                k = test1_straight(frodo) or k
            elif c == "2":
                r = test2_rotation(frodo) or r
            elif c == "s":
                print("\n" + "=" * 62)
                print("  pose_estimator.py DOSYASINA YAZ:")
                print("=" * 62)
                print(f"    K_SCALE = {k:.6f}" if k else "    K_SCALE = ???  (TEST 1 yapilmadi)")
                print(f"    RADIUS  = {r:.4f}" if r else "    RADIUS  = ???  (TEST 2 yapilmadi)")
                print("=" * 62)
    except KeyboardInterrupt:
        print("\nKesildi.")
    finally:
        try:
            frodo.control.setTrackSpeed(0.0, 0.0)
            print("Motorlar durduruldu.")
        except Exception:
            pass


if __name__ == "__main__":
    main()