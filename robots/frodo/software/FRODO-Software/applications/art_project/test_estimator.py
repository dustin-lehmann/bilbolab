# =====================================================================
#  ADIM 3-5 - ESTIMATOR DOGRULAMA
#  SURUM 2
#
#  ILK SURUMDEKI HATA VE DUZELTMESI:
#    RADIUS 100 kat kucuktu -> estimator psi'yi 100 kat hizli sayiyordu
#    -> turn_to her kontrolde 29.6 derece atliyor ama pencere 3.4 derece
#    -> pencereyi rastgele yakaliyor, robot RASTGELE bir acida duruyor
#    -> testler yine de "GECTI" diyordu (sadece yuzde karsilastiriyordu)
#
#    Eklenen 3 savunma:
#      1) sanity_check() - hareket ETMEDEN once sabitleri dogrula
#      2) turn_to icinde beklenen sure kontrolu
#      3) turn_to icinde ISARET DEGISIMI - pencereyi iskalasa bile durur
#      4) tum girdiler SANTIMETRE, fiziksel ust sinir kontrollu
#
#  Once pose_estimator.py icindeki K_SCALE ve RADIUS'u doldur!
# =====================================================================
import time
import numpy as np

from robot.frodo import FRODO
from robot.control.frodo_control import FRODO_ControlMode
from pose_estimator import PoseEstimator, wrap_pi, sanity_check, K_SCALE, RADIUS, MARKER_WORLD_MAP


DRIVE_SPEED = 0.08          # m/s
TURN_SPEED = 0.08           # m/s (tekerlek) - calib TEST 2 ile AYNI olmali
LEG_TIME = 3.0                # s  -> nominal ~0.24 m, ama GERCEK kat edilen mesafe komuttan (v*t)
                               # daha fazla cikiyor (gozlemlendi: 6.25s ~1m+ gitti, ~0.5m beklenirken).
                               # setTrackSpeed komutu ile fiziksel hiz arasinda ayri bir kalibrasyon
                               # farki var (K_SCALE'den bagimsiz - o sadece encoder geri beslemesini
                               # yorumluyor). Degeri deneysel olarak KISA tut, ilk denemede robotu
                               # izle, gerekirse Ctrl+C ile durdur.


# ---------------------------------------------------------------------
def drive(frodo, vl, vr, duration):
    frodo.control.setTrackSpeed(vl, vr)
    time.sleep(duration)
    frodo.control.setTrackSpeed(0.0, 0.0)
    time.sleep(0.6)              # atalet sonsun, encoder sifira insin


def show(est, tag):
    x, y, psi = est.get()
    print(f"  {tag:16} x={x:+.3f} m  y={y:+.3f} m  psi={np.degrees(psi):+7.1f} deg")
    return x, y, psi


def ask_cm(prompt, max_cm=None):
    """Santimetre sor, fiziksel ust siniri asarsa uyar. Metre dondurur."""
    while True:
        v = float(input(prompt))
        if max_cm is not None and v > max_cm:
            print(f"  !!! {v:.1f} cm, fiziksel ust sinir {max_cm:.0f} cm'den buyuk.")
            print("      Yanlislikla metre mi girdin? Tekrar gir.")
            continue
        return v / 100.0


# ---------------------------------------------------------------------
def turn_to(frodo, est, dpsi, tol_deg=1.7, timeout=20.0):
    """KAPALI CEVRIM donus: kor zamanlama degil, KESTIRIME bakarak don.

    Bu fonksiyon ayni zamanda ana koddaki TURNING_LEFT/RIGHT durumunun
    yerini alacak olan seyin prototipi. Basarili olursa TURN_MIN_TIME /
    TURN_TIMEOUT / kayma katsayisi tahmini gereksizlesir.
    """
    tol = np.radians(tol_deg)
    psi0 = est.get()[2]
    target = wrap_pi(psi0 + dpsi)
    err_prev = wrap_pi(target - psi0)

    # --- SAVUNMA 1: donus makul surede bitecek mi? ---
    w_beklenen = (2.0 * TURN_SPEED * 100.0) / RADIUS      # rad/s
    t_beklenen = abs(dpsi) / w_beklenen if w_beklenen > 0 else float("inf")
    if not (0.3 < t_beklenen < 30.0):
        print(f"  !!! DUR. Beklenen donus suresi {t_beklenen:.4f} s - fiziksel degil.")
        print(f"      RADIUS={RADIUS} yanlis. Kalibre etmeden devam etme.")
        return False
    print(f"  (beklenen donus suresi ~{t_beklenen:.2f} s)")

    t0 = time.time()
    hit = False
    while time.time() - t0 < timeout:
        err = wrap_pi(target - est.get()[2])

        # --- SAVUNMA 2: pencereyi ISKALASA BILE dur ---
        # Hata isaret degistirdiyse hedefi gecmisiz demektir.
        # (abs(err) < pi/2 sarti: wrap_pi'nin +-pi sicramasini
        #  gercek gecisle karistirmamak icin.)
        if abs(err) < tol or (err * err_prev < 0.0 and abs(err) < np.pi / 2.0):
            hit = True
            break
        err_prev = err

        s = TURN_SPEED if err > 0 else -TURN_SPEED
        frodo.control.setTrackSpeed(-s, s)     # sagda +s -> CCW -> psi artar
        time.sleep(0.01)

    frodo.control.setTrackSpeed(0.0, 0.0)
    time.sleep(0.6)

    kalan = np.degrees(wrap_pi(target - est.get()[2]))
    if not hit:
        print(f"  !!! turn_to ZAMAN ASIMI ({timeout:.0f} s), kalan hata = {kalan:+.2f} deg")
        return False
    print(f"  donus bitti ({time.time()-t0:.2f} s), kalan hata = {kalan:+.2f} deg")
    return True


# ---------------------------------------------------------------------
def test_straight(frodo, est):
    print("\n" + "=" * 62)
    print("TEST [a] - DUZ SURUS  (K_SCALE dogrulamasi)")
    print("=" * 62)
    d_bek = DRIVE_SPEED * LEG_TIME
    print(f"  Beklenen mesafe: ~{d_bek*100:.0f} cm")
    input("  Baslangici ve YONU yere isaretle, ENTER...")

    est.reset(0.0, 0.0, 0.0)
    show(est, "BASLANGIC")
    drive(frodo, DRIVE_SPEED, DRIVE_SPEED, LEG_TIME)
    x, y, psi = show(est, "SONUC")

    # --- fiziksel ust sinir: kestirim makul mu? ---
    if abs(x) > d_bek * 1.5:
        print(f"\n  !!! DUR. Kestirim x={x:.2f} m, fiziksel ust sinir {d_bek*1.5:.2f} m.")
        print(f"      K_SCALE={K_SCALE} yanlis. Kalibrasyona don.")
        return

    D = ask_cm("\n  Seritmetre: gercek mesafe kac SANTIMETRE? ", max_cm=d_bek*150)
    err_pct = abs(x - D) / D * 100.0 if D else float("inf")

    print(f"\n  kestirim   : {x*100:.1f} cm")
    print(f"  gercek     : {D*100:.1f} cm")
    print(f"  x hatasi   : {err_pct:.1f} %   (kriter: < 5 %)")
    print(f"  y sapmasi  : {y*100:+.1f} cm")
    print(f"  psi sapmasi: {np.degrees(psi):+.1f} deg")

    if err_pct < 5.0:
        print("  --> GECTI (K_SCALE dogru)")
    else:
        print(f"  --> KALDI. K_SCALE ~{K_SCALE*D/x:.6f} olmali. ILERI GITME.")

    # fiziksel yon de olculsun: [c]'deki hatanin kaynagini ayirir
    a = input("\n  Robot fiziksel olarak kac DERECE sapti? (bilmiyorsan bos gec) ").strip()
    if a:
        a = float(a)
        print(f"  fiziksel sapma: {a:+.1f} deg,  kestirim: {np.degrees(psi):+.1f} deg")
        if abs(a) > 5.0:
            print("  !!! Duz giderken donuyor: paletlerden biri farkli calisiyor.")
            print("      Bu MEKANIK bir sorun, yazilimla duzelmez. Hocaya soyle.")


def test_turn(frodo, est):
    print("\n" + "=" * 62)
    print("TEST [b] - 90 DERECE DONUS  (RADIUS dogrulamasi)")
    print("=" * 62)
    print("  Robotu duz bir kenara (masa/duvar) dayayarak hizala.")
    print("  ACI OLCUMU: bitiste govdeyi baska bir duz kenara dayamayi dene,")
    print("  ya da telefonunun pusula/acolcer uygulamasini robotun ustune koy.")
    print("  GOZLE 'yaklasik 90' DEME - ilk turda bu bizi yaniltti.")
    input("  ENTER...")

    est.reset(0.0, 0.0, 0.0)
    show(est, "BASLANGIC")
    if not turn_to(frodo, est, np.pi / 2.0):
        print("  --> Donus basarisiz. Kalibrasyona don.")
        return
    x, y, psi = show(est, "SONUC")

    real = float(input("\n  Gercekte kac DERECE dondu? "))
    fark = abs(np.degrees(psi) - real)

    print(f"\n  kestirim   : {np.degrees(psi):+.1f} deg")
    print(f"  gercek     : {real:+.1f} deg")
    print(f"  fark       : {fark:.1f} deg   (kriter: < 5)")
    print(f"  x,y kaymasi: {x*100:+.1f} cm, {y*100:+.1f} cm  (yerinde donus, ~0 olmali)")

    if fark < 5.0:
        print("  --> GECTI (RADIUS dogru, kapali cevrim donus calisiyor)")
    else:
        oneri = RADIUS * (np.degrees(psi) / real) if real else RADIUS
        print(f"  --> KALDI. RADIUS'u ~{oneri:.3f} deneyip tekrarla.")


def test_square(frodo, est):
    print("\n" + "=" * 62)
    print("TEST [c] - KARE  (KAPANMA HATASI - asil test)")
    print("=" * 62)
    print("  4 kenar x ~0.96 m + 4 donus. Yaklasik 1.5-2 dakika.")
    print("  Baslangic noktasini ve YONUNU yere isaretle!")
    input("  ENTER...")

    est.reset(0.0, 0.0, 0.0)
    show(est, "BASLANGIC")

    for i in range(4):
        print(f"\n  --- kenar {i+1}/4 ---")
        drive(frodo, DRIVE_SPEED, DRIVE_SPEED, LEG_TIME)
        show(est, f"kenar {i+1} sonu")
        if not turn_to(frodo, est, np.pi / 2.0):
            print("  --> Donus basarisiz, test iptal.")
            return
        show(est, f"donus {i+1} sonu")

    x, y, psi = show(est, "KAPANIS")
    print(f"\n  {est.stats()}")
    print(f"  Kestirime gore hata: {np.hypot(x, y)*100:.1f} cm, "
          f"{abs(np.degrees(psi)):.1f} deg")

    L = 4.0 * DRIVE_SPEED * LEG_TIME
    e = ask_cm("\n  FIZIKSEL olarak baslangictan kac SANTIMETRE uzakta? ",
               max_cm=L * 150)
    a = float(input("  Yonu kac DERECE sapmis? "))

    sigma = e / np.sqrt(L)

    print("\n" + "-" * 62)
    print("  BU SATIRLARI DEFTERINE YAZ:")
    print(f"    yol uzunlugu     L = {L:.2f} m")
    print(f"    konum hatasi     e = {e*100:.1f} cm")
    print(f"    aci hatasi         = {a:.1f} deg")
    print(f"    birim yol basina sigma = {sigma:.5f} m/sqrt(m)")
    print("-" * 62)
    print("  sigma, ADIM 3'te Q matrisinin kosegenini verecek.")
    print("  (Drift'in rastgele yuruyus gibi biriktigi varsayimiyla:")
    print("   bagimsiz hatalarin varyansi toplanir, std karekokle buyur.)")
    print("\n  3 TEKRAR YAP. Sonra sacilima bak:")
    print("    hep AYNI yone sapiyorsa -> SISTEMATIK (kalibrasyon eksik)")
    print("    rastgele saciliyorsa    -> STOKASTIK (gercek gurultu, Q bunu modeller)")


def test_aruco_correction(frodo, est):
    print("\n" + "=" * 62)
    print("TEST [d] - ARUCO DUZELTME  (EKF - ADIM 4)")
    print("=" * 62)
    if not MARKER_WORLD_MAP:
        print("  !!! MARKER_WORLD_MAP bos (pose_estimator.py). Grid kurulmadan")
        print("      bu test calismaz - once en az bir marker'in dunya")
        print("      konumunu (metre) MARKER_WORLD_MAP'e ekle.")
        return
    print(f"  Taninan markerlar: {list(MARKER_WORLD_MAP.keys())}")
    print("  Robotu, gorecegin bir markerin karsisina koy.")
    print("  Bu testte BILEREK yanlis bir baslangic konumu verilecek")
    print("  (drift simulasyonu) - sonra marker gorulunce duzelmesi bekleniyor.")

    mid = int(input("  Hangi marker ID'sini kullanacaksin? "))
    if mid not in MARKER_WORLD_MAP:
        print(f"  !!! {mid} MARKER_WORLD_MAP'te yok.")
        return
    mx, my = MARKER_WORLD_MAP[mid]
    print(f"  Marker {mid} dunya konumu: ({mx:.2f}, {my:.2f}) m")

    # bilerek yanlis baslangic: gercek konumdan rastgele-benzeri bir ofsetle uzaklastir
    fake_x = mx - 1.0
    fake_y = my + 0.3
    est.reset(fake_x, fake_y, 0.0)
    print(f"\n  Baslangic BILEREK yanlis verildi: ({fake_x:+.2f}, {fake_y:+.2f})")
    show(est, "DUZELTME ONCESI")
    print(f"  {est.stats()}")

    print("\n  Robotu markera dogru cevirip goruyor olmasini bekle (Ctrl+C ile durdur)...")
    t0 = time.time()
    last_n = est.n_corrections
    try:
        while time.time() - t0 < 15.0:
            if est.n_corrections > last_n:
                print(f"  [{time.time()-t0:4.1f}s] duzeltme #{est.n_corrections}: "
                      + " ".join(f"{v:+.3f}" for v in est.get()))
                last_n = est.n_corrections
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    x, y, psi = show(est, "DUZELTME SONRASI")
    print(f"  {est.stats()}")

    err_before = np.hypot(fake_x - mx, fake_y - my)
    err_after = np.hypot(x - mx, y - my)
    print(f"\n  hata ONCE (markere gore, kaba fikir): {err_before*100:.1f} cm")
    print(f"  hata SONRA                          : {err_after*100:.1f} cm")
    if est.n_corrections == last_n and last_n == 0:
        print("  --> HIC duzeltme olmadi. Marker gorulmedi mi? Kamerayi/mesafeyi kontrol et.")
    elif err_after < err_before:
        print("  --> GECTI (duzeltme hatayi kucultuyor)")
    else:
        print("  --> KALDI. sigma_x/sigma_y cok mu kucuk/ buyuk? pose_estimator.py'deki")
        print("      SIGMA_MEAS_* / SIGMA_POS_PER_SQRT_M degerlerini gozden gecir.")


# ---------------------------------------------------------------------
def main():
    print("=" * 62)
    print("SABIT KONTROLU")
    print("=" * 62)
    if not sanity_check():
        print("\n!!! Sabitler makul degil. calib_odom.py'yi calistir, sonra don.")
        return
    if abs(RADIUS - 31.0) < 1e-9:
        print("\n  UYARI: RADIUS hala varsayilan tahmin (31.0).")
        print("  calib_odom.py TEST 2'yi calistirip GERCEK degeri yazdin mi?")
        if input("  Yine de devam? (e/h) ").strip().lower() != "e":
            return

    frodo = FRODO()
    frodo.init()
    frodo.start()
    frodo.control.setMode(FRODO_ControlMode.EXTERNAL)

    est = PoseEstimator(frodo, verbose=False)
    est.start()

    try:
        while True:
            print("\n" + "-" * 62)
            print("  [a] duz     -> K_SCALE dogrulamasi")
            print("  [b] 90 der  -> RADIUS dogrulamasi")
            print("  [c] kare    -> kapanma hatasi")
            print("  [d] aruco   -> EKF duzeltme testi (ADIM 4)")
            print("  [p] anlik pozu goster")
            print("  [q] cikis")
            c = input("  Secim > ").strip().lower()

            if c == "q":
                break
            elif c == "a":
                test_straight(frodo, est)
            elif c == "b":
                test_turn(frodo, est)
            elif c == "c":
                test_square(frodo, est)
            elif c == "d":
                test_aruco_correction(frodo, est)
            elif c == "p":
                show(est, "ANLIK")
                print(f"  {est.stats()}")
    except KeyboardInterrupt:
        print("\nKesildi.")
    finally:
        try:
            frodo.control.setTrackSpeed(0.0, 0.0)
        except Exception:
            pass
        est.stop()
        print("Motorlar durduruldu, estimator kapatildi.")


if __name__ == "__main__":
    main()