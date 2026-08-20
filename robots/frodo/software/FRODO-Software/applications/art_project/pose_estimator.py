# =====================================================================
#  POSE ESTIMATOR - ADIM 1: ONGORU (prediction) + ADIM 4: EKF DUZELTME
#  SURUM 3 - ArUco ile Kalman duzeltmesi eklendi
#
#  Durum:  p = [x, y, psi]        (metre, metre, radyan)
#
#  Model (hocanin tahtada yazdigi, ileri Euler):
#    x_{k+1}   = x_k   + dt * cos(psi_k) * v
#    y_{k+1}   = y_k   + dt * sin(psi_k) * v
#    psi_{k+1} = psi_k + dt * psi_dot
#
#  ------------------- BIRIMLER (OLCULDU) -------------------
#  setTrackSpeed()  KOMUTU        : m/s
#  speed_left/right GERI BESLEMESI: cm/s VARSAYILMISTI, ama calib_odom.py
#  sonucu (K_SCALE ~0.00102, beklenen ~0.01'in 10 kati kucuk) bu varsayimin
#  YANLIS oldugunu gosteriyor - ham deger cm/s degil, muhtemelen tick/s
#  gibi daha kucuk adimli bir birim. K_SCALE/RADIUS yine de dogru CALISIR
#  (ikisi de ayni ham birimden turetildigi icin birbirini telafi eder),
#  sadece RADIUS artik "iz genisligi santimetre" gibi fiziksel okunmuyor.
#
#  v       = K_SCALE * (sL + sR) / 2         [m/s]
#  psi_dot = (sR - sL) / RADIUS              [rad/s]
#
#  ------------------- EKF DUZELTME (ADIM 4) -------------------
#  frodo.sensors.aruco_detector zaten arka planda calisiyor (frodo.start()
#  ile baslar) ve .measurements listesinde ArucoMeasurement(marker_id,
#  rotation_vec, translation_vec, distance) veriyor - KAMERA CERCEVESINDE.
#
#  frodo.sensors.getSample().aruco_measurements KULLANILMADI: o yol
#  ./model.yaml dosyasina bagimli (measurement_model_from_file) ve bu
#  dosya repoda yok -> kirilgan. Onun yerine ham olcumden KENDI basit
#  donusumumuzu yapiyoruz (marker_to_robot_frame), hocanin istedigi tam
#  olarak bu: "kamera cercevesinden robot merkezine cevir".
#
#  Marker montaj YONU (heading) fiziksel olarak guvenilir degil/bilinmiyor
#  -> EKF duzeltmesi SADECE KONUM (x,y) kullanir, psi tamamen odometriden
#  gelmeye devam eder (bkz. MARKER_WORLD_MAP, sadece (x,y) tutuyor).
# =====================================================================
import time
import threading
import numpy as np


# ---------------------------------------------------------------------
#  KALIBRASYON SABITLERI
# ---------------------------------------------------------------------
K_SCALE = 0.000979   # OLCULDU: 3 farkli mesafede (0.95/2.0/3.0 m) TEST [a] oranlarinin ortalamasi
                      # (1.0128, 1.0122, 1.0098 -> ort. 1.0116) ile 0.000968'in duzeltilmesi
RADIUS = 126.5       # OLCULDU: test_estimator.py TEST [c] kare icindeki 4 donusun pusula olcumu
                      # (333->238->143->47->312: her donus ~95.5 deg, hedef 90 deg, hep AYNI yonde -
                      #  sistematik. RADIUS 133.835*(90/95.25) ile duzeltildi.)

# Encoder bias'i (smoke_test.py'den). Yoksa 0 birak.
BIAS_LEFT = 0.0
BIAS_RIGHT = 0.0

# Akla yatkinlik sinirlari - sacma kalibrasyonu erken yakalamak icin.
# Eskiden "ham=cm/s" varsayimiyla dar tutulmustu (K_SCALE~0.01, RADIUS~25-35);
# gercek kalibrasyon bu varsayimi gecersiz kildigi icin sinirlar genisletildi.
K_SCALE_RANGE = (0.0005, 2.0)
RADIUS_RANGE = (5.0, 250.0)


# ---------------------------------------------------------------------
#  EKF SABITLERI (ADIM 4)
# ---------------------------------------------------------------------
# OLCULDU: test_estimator.py TEST [c] (kare testi), L=0.96 m, e=0.7 cm,
# aci hatasi=1 deg -> ham sigma=0.0102 m/sqrt(m). TEK DENEMEDEN geldigi icin
# (kendi script'in 3 tekrar oneriyor - std tek ornekten guvenilir tahmin
# edilemez) ~1.5x pay birakildi. Daha fazla tekrar yapilirsa buraya ortalama
# ile guncellenebilir.
SIGMA_POS_PER_SQRT_M = 0.015   # [m / sqrt(m)]

# OLCULDU: ayni TEST [c] kosusu, toplam sure ~25.2 s (4 kenar x (3.0s surus +
# 0.6s bekleme) + 4 donus (2.11+2.10+2.10+2.11 s) + 4x0.6s bekleme),
# aci hatasi=1 deg -> ham sigma=0.00348 rad/sqrt(s). Yine TEK DENEMEDEN
# geldigi icin ~1.5x pay birakildi.
Q_PSI_PER_SEC = (np.radians(1.0) / np.sqrt(25.2) * 1.5) ** 2   # [rad^2/s]

# Marker'in ArUco olcumu mesafeyle birlikte guvenilirligini kaybeder
# (perspektif bozulmasi, piksel cozunurlugu). Basit dogrusal buyume:
SIGMA_MEAS_BASE = 0.03         # [m] - marker cok yakinken bile olan taban hata
SIGMA_MEAS_PER_M = 0.05        # [m/m] - mesafeyle ekstra hata

# Bu mesafeden uzak olculen markerlara guvenme (ARUCO_Y_MIN filtresinin
# metre karsiligi - bkz. art_project_frodo.py).
MAX_RELIABLE_DISTANCE_M = 1.2

# marker_id -> (x_world_m, y_world_m). id0 orijin (0,0) kabul edilerek elle
# mezurayla OLCULDU (santimetreden metreye cevrildi). Grid indeksleri:
# id0:(0,0) id1:(1,0) id2:(2,0) id3:(0,1) id4:(1,1) id5:(2,1) id6:(0,2)
# id7:(1,2) id8:(2,2) - CITY_MAP (art_project_frodo.py) ile ayni duzen.
MARKER_WORLD_MAP: dict[int, tuple[float, float]] = {
    0: (0.000, 0.000),
    1: (0.380, 0.000),
    2: (0.720, 0.000),
    3: (0.000, 0.325),
    4: (0.380, 0.373),
    5: (0.720, 0.325),
    6: (0.000, 0.720),
    7: (0.368, 0.720),
    8: (0.715, 0.720),
}


def wrap_pi(a):
    """Aciyi [-pi, +pi] araligina katla.

    NEDEN GEREKLI: cos/sin icin fark etmez, ama Adim 4'te Kalman
    yeniligi y = z - x_hat hesaplanirken psi=6.28 ve z=0.02 arasindaki
    fark 6.26 rad gorunur - halbuki gercek fark ~0. Filtre bozulur.
    """
    return (a + np.pi) % (2.0 * np.pi) - np.pi


def sanity_check(verbose=True):
    """Sabitler fiziksel olarak makul mu? Hareket ETMEDEN once cagir.

    Bu fonksiyonun varlik sebebi: ilk turda RADIUS 100 kat kucuktu,
    estimator robotun saniyede 8 tur attigini saniyordu ve testler
    yine de 'GECTI' dedi. Buyukluk kontrolu olmadan yuzde
    karsilastirmasi hicbir sey ispatlamaz.
    """
    ok = True
    if not (K_SCALE_RANGE[0] <= K_SCALE <= K_SCALE_RANGE[1]):
        print(f"!!! K_SCALE={K_SCALE} makul araligin disinda {K_SCALE_RANGE}")
        ok = False
    if not (RADIUS_RANGE[0] <= RADIUS <= RADIUS_RANGE[1]):
        print(f"!!! RADIUS={RADIUS} makul araligin disinda {RADIUS_RANGE}")
        print("    Hatirlatma: RADIUS = efektif iz genisligi, SANTIMETRE cinsinden.")
        ok = False
    if not (0.0 < SIGMA_POS_PER_SQRT_M < 1.0):
        print(f"!!! SIGMA_POS_PER_SQRT_M={SIGMA_POS_PER_SQRT_M} makul degil (0-1 m/sqrt(m) beklenir)")
        ok = False
    if not (0.0 < MAX_RELIABLE_DISTANCE_M < 5.0):
        print(f"!!! MAX_RELIABLE_DISTANCE_M={MAX_RELIABLE_DISTANCE_M} makul degil")
        ok = False
    if not MARKER_WORLD_MAP:
        print("  UYARI: MARKER_WORLD_MAP bos - EKF duzeltmesi hicbir zaman calismayacak,")
        print("         sadece prediction (ADIM 1) calisir. Grid kurulunca doldur.")

    if verbose:
        print(f"  K_SCALE = {K_SCALE:.6f}  ->  1 ham birim = {K_SCALE*100:.3f} cm/s")
        print(f"  RADIUS  = {RADIUS:.3f}    ->  efektif iz genisligi = {RADIUS:.1f} cm")
        w = (2 * 8.0) / RADIUS       # her tekerlek 8 cm/s, zit yonde
        print(f"  Ornek: +-0.08 m/s yerinde donus -> {w:.3f} rad/s "
              f"({np.degrees(w):.1f} deg/s), 90 derece = {(np.pi/2)/w:.2f} s")
        print(f"  SIGMA_POS_PER_SQRT_M = {SIGMA_POS_PER_SQRT_M:.3f} m/sqrt(m)")
        print(f"  MAX_RELIABLE_DISTANCE_M = {MAX_RELIABLE_DISTANCE_M:.2f} m")
        print(f"  MARKER_WORLD_MAP = {len(MARKER_WORLD_MAP)} marker taniniyor")
    return ok


def marker_to_robot_frame(measurement, camera_to_center_distance):
    """ArucoMeasurement (KAMERA cercevesi, rvec/tvec) -> robot govde cercevesinde (x_rel, y_rel).

    x_rel: robotun onune dogru mesafe [m], y_rel: robotun soluna dogru mesafe [m].
    Marker montaj yonu (psi) fiziksel olarak guvenilir olmadigi icin kullanilmiyor -
    sadece konum (trilaterasyon) cikariliyor.
    """
    tvec = measurement.translation_vec
    x_rel = float(tvec[2]) + camera_to_center_distance
    y_rel = -float(tvec[0])
    return x_rel, y_rel


class PoseEstimator:
    """Tekerlek odometrisiyle [x, y, psi] kestirimi.

    Ayri bir daemon thread'de ~100 Hz kosar. Goruntu dongusu ~15 Hz'de
    calistigi icin ayrilar: kestirim HIZLI ve duzenli olmali, gorme
    YAVAS ve duzensiz. (Klasik predict-fast / update-slow mimarisi.)
    """

    def __init__(self, frodo, x0=0.0, y0=0.0, psi0=0.0, Ts=0.01, verbose=True):
        self.frodo = frodo
        self.Ts = Ts
        self.verbose = verbose
        self.state = np.array([x0, y0, psi0], dtype=float)
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

        # EKF kovaryansi. Baslangicta x0,y0,psi0'a tam guvenmiyoruz (kullanici
        # 0,0,0 verip robotu rastgele bir yere koymus olabilir) - ilk ArUco
        # gorulunce _correct() bunu otomatik sifirlayacak (bkz. _got_first_fix).
        self.P = np.diag([0.5 ** 2, 0.5 ** 2, np.radians(45.0) ** 2])
        self._got_first_fix = False
        self._prev_measurements_ref = None     # ayni detector turunu iki kere islememek icin
        self.n_corrections = 0

        # teshis
        self.n_updates = 0
        self.dt_max = 0.0
        self.path_length = 0.0       # toplam kat edilen yol (m)
        self.psi_dot_max = 0.0       # gorulen en buyuk acisal hiz (rad/s)

    # ---------------- disaridan guvenli erisim ----------------
    def get(self):
        """[x, y, psi] kopyasi dondurur."""
        with self.lock:
            return self.state.copy()

    def reset(self, x=0.0, y=0.0, psi=0.0):
        """Durumu zorla ayarla ve bunu GUVENILIR bir fix olarak isaretle.

        Testlerde robotu bilinen bir baslangic noktasina koyup burayi cagirmak,
        ArUco ile gelen ilk duzeltmeyle ayni etkiyi manuel olarak yaratir
        (bkz. _correct icindeki _got_first_fix dali).
        """
        with self.lock:
            self.state = np.array([x, y, psi], dtype=float)
            self.P = np.diag([SIGMA_MEAS_BASE ** 2, SIGMA_MEAS_BASE ** 2, np.radians(5.0) ** 2])
            self._got_first_fix = True
        self.path_length = 0.0
        self.psi_dot_max = 0.0

    # ---------------- ongoru dongusu ----------------
    def _loop(self):
        t_prev = time.time()
        t_print = t_prev

        while not self._stop.is_set():
            now = time.time()
            dt = now - t_prev
            t_prev = now

            # dt SABIT Ts DEGIL, OLCULEN deger: sleep(0.01) "en az 10 ms"
            # demektir, "tam 10 ms" degil. Sabit varsayarsan sistematik
            # (sifir ortalamali OLMAYAN) hata birikir - Kalman bunu
            # duzeltemez, cunku filtre gurultunun sifir ortalamali
            # oldugunu varsayar.
            if dt <= 0.0 or dt > 0.5:
                time.sleep(self.Ts)
                continue

            try:
                d = self.frodo.estimation.getSample().lowlevel_data
                sl = d.speed_left - BIAS_LEFT
                sr = d.speed_right - BIAS_RIGHT
            except Exception as e:
                print(f"[EST] sensor okuma hatasi: {e}")
                time.sleep(self.Ts)
                continue

            v = K_SCALE * 0.5 * (sl + sr)
            psi_dot = (sr - sl) / RADIUS

            with self.lock:
                x, y, psi = self.state

                # --- kovaryans yayilimi (predict) ---
                F = np.array([
                    [1.0, 0.0, -dt * v * np.sin(psi)],
                    [0.0, 1.0,  dt * v * np.cos(psi)],
                    [0.0, 0.0,  1.0],
                ])
                q_pos = (SIGMA_POS_PER_SQRT_M ** 2) * abs(v) * dt
                Q = np.diag([q_pos, q_pos, Q_PSI_PER_SEC * dt])
                self.P = F @ self.P @ F.T + Q

                self.state = np.array([
                    x + dt * np.cos(psi) * v,
                    y + dt * np.sin(psi) * v,
                    wrap_pi(psi + dt * psi_dot),
                ])

            self.n_updates += 1
            self.dt_max = max(self.dt_max, dt)
            self.path_length += abs(v) * dt
            self.psi_dot_max = max(self.psi_dot_max, abs(psi_dot))

            # --- ArUco duzeltme (update) - detector kendi hizinda (~10-40 Hz)
            # calisiyor, ayni turu iki kere islememek icin liste kimligine bak ---
            try:
                measurements = self.frodo.sensors.aruco_detector.measurements
            except Exception:
                measurements = None
            if measurements and measurements is not self._prev_measurements_ref:
                self._prev_measurements_ref = measurements
                self._correct(measurements)

            if self.verbose and (now - t_print) > 1.0:
                t_print = now
                x, y, psi = self.get()
                print(f"[EST] x={x:+.3f} m  y={y:+.3f} m  "
                      f"psi={np.degrees(psi):+7.1f} deg  yol={self.path_length:.2f} m  "
                      f"duzeltme={self.n_corrections}")

            time.sleep(self.Ts)

    # ---------------- duzeltme (update) ----------------
    def _correct(self, measurements):
        """Gorulen ArUco marker'lariyla EKF konum duzeltmesi (sadece x,y)."""
        try:
            camera_to_center_distance = self.frodo.settings.camera.camera_to_center_distance
        except Exception:
            return

        for m in measurements:
            if m.marker_id not in MARKER_WORLD_MAP:
                continue
            if m.distance > MAX_RELIABLE_DISTANCE_M:
                continue

            x_rel, y_rel = marker_to_robot_frame(m, camera_to_center_distance)
            mx, my = MARKER_WORLD_MAP[m.marker_id]
            sigma_r = SIGMA_MEAS_BASE + SIGMA_MEAS_PER_M * m.distance
            R = np.diag([sigma_r ** 2, sigma_r ** 2])

            with self.lock:
                if not self._got_first_fix:
                    # Ilk fix: yumusak Kalman karismasi degil, dogrudan ata
                    # (ADIM 3'teki reset() mantiginin otomatik hali).
                    x, y, psi = self.state
                    cos_p, sin_p = np.cos(psi), np.sin(psi)
                    self.state[0] = mx - (cos_p * x_rel - sin_p * y_rel)
                    self.state[1] = my - (sin_p * x_rel + cos_p * y_rel)
                    self.P[0:2, 0:2] = R
                    self._got_first_fix = True
                    self.n_corrections += 1
                    continue

                x, y, psi = self.state
                cos_p, sin_p = np.cos(psi), np.sin(psi)
                dx_w = mx - x
                dy_w = my - y
                x_pred = cos_p * dx_w + sin_p * dy_w
                y_pred = -sin_p * dx_w + cos_p * dy_w

                H = np.array([
                    [-cos_p, -sin_p, y_pred],
                    [ sin_p, -cos_p, -x_pred],
                ])
                innov = np.array([x_rel - x_pred, y_rel - y_pred])

                S = H @ self.P @ H.T + R
                K = self.P @ H.T @ np.linalg.inv(S)

                self.state = self.state + K @ innov
                self.state[2] = wrap_pi(self.state[2])
                self.P = (np.eye(3) - K @ H) @ self.P
                self.n_corrections += 1

    # ---------------- yasam dongusu ----------------
    def start(self):
        if self._thread is not None:
            return

        # frodo.sensors.aruco_detector, get_all_aruco_ids()'ten gelen bir
        # beyaz listeyle (robotlarin/statiklerin KENDI marker ID'leri,
        # bkz. robot/definitions.py ARUCO_SETTINGS/STATIC*) kurulu - bu
        # listede olmayan ID'ler (art_project grid'i icin cogu ID, orn. 4-8)
        # sessizce filtrelenip olcum listesine hic girmiyordu. _correct()
        # zaten MARKER_WORLD_MAP disindaki ID'leri kendi tarafimizda
        # eliyor, o yuzden burada filtreyi tamamen kapatmak guvenli.
        try:
            self.frodo.sensors.aruco_detector.allowed_marker_ids = None
        except Exception as e:
            print(f"[EST] allowed_marker_ids kapatilamadi: {e}")

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        time.sleep(0.2)          # ilk ornek gelsin

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def stats(self):
        with self.lock:
            sigma_x = np.sqrt(self.P[0, 0])
            sigma_y = np.sqrt(self.P[1, 1])
        return (f"guncelleme={self.n_updates}  dt_max={self.dt_max*1000:.1f} ms  "
                f"yol={self.path_length:.3f} m  "
                f"psi_dot_max={self.psi_dot_max:.2f} rad/s  "
                f"duzeltme={self.n_corrections}  "
                f"sigma_x={sigma_x*100:.1f} cm  sigma_y={sigma_y*100:.1f} cm")