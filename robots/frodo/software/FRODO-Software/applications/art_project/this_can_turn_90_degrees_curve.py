import time
import threading
import cv2
import numpy as np

# YENİ: QR Kod Kütüphanesi
from pyzbar.pyzbar import decode

from robot.frodo import FRODO
from robot.control.frodo_control import FRODO_ControlMode
from robot.utilities.video_streamer.video_streamer import VideoStreamer
from core.utils.network import getInterfaceIP

# --- GLOBAL VARIABLES FOR WEB STREAMING ---
stream_frame_lock = threading.Lock()
frame_out = None


def get_color_mask(frame, target_color):
    if frame.ndim == 2:
        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    else:
        bgr_frame = frame

    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)

    if target_color == "pink":
        lower_bound = np.array([140, 50, 50])
        upper_bound = np.array([179, 255, 255])
    elif target_color == "green":
        lower_bound = np.array([40, 100, 100])
        upper_bound = np.array([80, 255, 255])
    elif target_color == "blue":
        lower_bound = np.array([100, 100, 100])
        upper_bound = np.array([130, 255, 255])
    else:
        raise ValueError("Unknown color! Only use 'pink', 'green' or 'blue'.")

    mask = cv2.inRange(hsv, lower_bound, upper_bound)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    return mask


def calculate_deviation(mask, image_width, frame):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if len(contours) == 0:
        return 0.0, False

    c = max(contours, key=cv2.contourArea)
    M = cv2.moments(c)
    if M["m00"] == 0:
        return 0.0, False

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    camera_center = image_width // 2
    error = cx - camera_center

    cv2.drawContours(frame, [c], -1, (0, 255, 0), 2)
    cv2.circle(frame, (cx, cy), 8, (255, 0, 0), -1)

    height = frame.shape[0]
    cv2.line(frame, (camera_center, 0), (camera_center, height), (0, 255, 255), 2)
    cv2.line(frame, (camera_center, cy), (cx, cy), (0, 0, 255), 3)
    cv2.putText(frame, f"Error: {error} px", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    return error, True


def proportional_controller(error, kp, base_speed):
    abs_error = abs(error)

    if abs_error > 120:
        forward_speed = base_speed * 0.2
    elif abs_error > 60:
        forward_speed = base_speed * 0.5
    else:
        forward_speed = base_speed

    angular_speed = -kp * error
    return forward_speed, angular_speed


def calculate_wheel_speeds(forward_speed, angular_speed, track_width):
    half_w = 0.5 * track_width
    v_left = forward_speed - half_w * angular_speed
    v_right = forward_speed + half_w * angular_speed
    return v_left, v_right


def main():
    global frame_out

    # 1. SETUP ROBOT
    frodo = FRODO()
    frodo.init()
    frodo.start()
    frodo.control.setMode(FRODO_ControlMode.EXTERNAL)

    # 2. SETUP VIDEO STREAMER
    def get_stream_frame():
        with stream_frame_lock:
            if frame_out is not None:
                return frodo.sensors.camera.getImageBufferBytes(frame_out)
            return None

    streamer = VideoStreamer(image_fetcher=get_stream_frame, port=5001)
    streamer.start()
    ip = getInterfaceIP("wlan0")
    print(f"\n---> LIVE: http://{ip}:5001/preview <--- \n")

    # 3. SYSTEM PARAMETERS
    CURRENT_TARGET_COLOR = "pink"  # Başlangıç Doğu (EAST) olduğu için pembe ile başlıyoruz.
    kp = 0.008
    base_speed = 0.12
    track_width = 0.150
    image_width = 728
    turn_speed = 0.10

    # --- GRID NAVIGATION SYSTEM ---
    ROBOT_STATE = "FOLLOWING"
    ROBOT_HEADING = "EAST"
    TARGET_COORD = (2, 2) # Hedefimiz ID 9 (En alt sağ köşe)
    LAST_SEEN_ID = None

    PARKING_TIME = 0.8
    stop_timer = 0

    # Fotoğraftaki Yeni 3x3 QR Koordinat Haritası
    CITY_MAP = {
        "1": (0, 0),
        "2": (1, 0),
        "3": (2, 0),
        "4": (0, 1),
        "5": (1, 1),
        "6": (2, 1),
        "7": (0, 2),
        "8": (1, 2),
        "9": (2, 2)
    }
    # -----------------------------------------------------

    print(f"Autonomous Grid Navigation Started (QR Code Mode).")
    print(f"Target Destination: {TARGET_COORD} | Current Heading: {ROBOT_HEADING}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            frame = frodo.sensors.camera.events.frame.get_data()
            if frame is None:
                continue

            display_frame = frame.copy()

            # --- EĞER ROBOT DURDURULDUYSA DİREKT MOTORLARI KES VE ÇIK ---
            if ROBOT_STATE == "STOPPED":
                frodo.control.setTrackSpeed(0.0, 0.0)
                cv2.putText(display_frame, "DESTINATION REACHED", (150, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.5,
                            (0, 255, 0), 4)

                with stream_frame_lock:
                    frame_out = display_frame

                print("\n*** MISSION ACCOMPLISHED. Motors locked. Exiting program loop. ***")
                break

            # =========================================================
            # YENİ: QR KOD ALGILAMA VE YAKINLIK/ŞERİT FİLTRESİ
            # =========================================================
            # Performansı artırmak ve yalpalamayı (FPS drop) önlemek için görüntüyü siyah-beyaza çeviriyoruz
            gray_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2GRAY)
            decoded_objects = decode(gray_frame)

            for obj in decoded_objects:
                # QR kodu metne çevir (Örn: "5")
                detected_id = obj.data.decode('utf-8').strip()

                # QR kodun köşelerini bul ve ekrana çiz
                pts = np.array([[pt.x, pt.y] for pt in obj.polygon], np.int32)
                pts = pts.reshape((-1, 1, 2))
                cv2.polylines(display_frame, [pts], True, (255, 0, 255), 3)

                # Tabelanın ekrandaki dikey (Y) ve yatay (X) konumu
                center_x = int(np.mean([pt.x for pt in obj.polygon]))
                center_y = int(np.mean([pt.y for pt in obj.polygon]))

                # 1. Y EKSENİ FİLTRESİ: Ekranın alt sınırına gelene kadar bekle (330 tatlı nokta)
                if center_y < 330:
                    cv2.putText(display_frame, f"QR {detected_id}: TOO FAR", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 1,
                                (0, 0, 255), 2)
                    continue

                # 2. X EKSENİ FİLTRESİ: Yan şeritleri yoksay!
                # (Ekran 728px, merkez 364px. Sadece 210 ile 518 pikselleri arasındaki kodları kabul et)
                if center_x < 210 or center_x > 518:
                    cv2.putText(display_frame, f"QR {detected_id}: WRONG LANE", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 1,
                                (0, 165, 255), 2)
                    continue

                cv2.putText(display_frame, f"QR ID: {detected_id} DETECTED", (10, 80), cv2.FONT_HERSHEY_SIMPLEX,
                            1, (0, 255, 0), 2)

                # --- KARAR VERME (PATHFINDING) ---
                if detected_id in CITY_MAP and detected_id != LAST_SEEN_ID and ROBOT_STATE == "FOLLOWING":
                    current_coord = CITY_MAP[detected_id]
                    LAST_SEEN_ID = detected_id

                    print(f"\n--- LOCATION UPDATED: {current_coord} (QR {detected_id}) ---")

                    # Hedefe Ulaştık Mı?
                    if current_coord == TARGET_COORD:
                        print(f"*** TARGET IDENTIFIED! Initiating parking sequence for {PARKING_TIME} sec... ***")
                        ROBOT_STATE = "PARKING"
                        stop_timer = time.time() + PARKING_TIME
                        break

                    # Hedefe Ulaşmadıysak Yeni Yönü Hesapla
                    else:
                        dx = TARGET_COORD[0] - current_coord[0]
                        dy = TARGET_COORD[1] - current_coord[1]

                        if dx > 0:
                            desired_heading = "EAST"
                        elif dx < 0:
                            desired_heading = "WEST"
                        elif dy > 0:
                            desired_heading = "NORTH"
                        elif dy < 0:
                            desired_heading = "SOUTH"

                        print(f"Current Heading: {ROBOT_HEADING} | Desired Heading: {desired_heading}")

                        if ROBOT_HEADING == desired_heading:
                            print("Action: CONTINUE (Going straight)")
                        else:
                            if (ROBOT_HEADING == "EAST" and desired_heading == "SOUTH") or \
                               (ROBOT_HEADING == "SOUTH" and desired_heading == "WEST") or \
                               (ROBOT_HEADING == "WEST" and desired_heading == "NORTH") or \
                               (ROBOT_HEADING == "NORTH" and desired_heading == "EAST"):
                                ROBOT_STATE = "TURNING_RIGHT"
                                print("Action: TURN RIGHT")

                            elif (ROBOT_HEADING == "EAST" and desired_heading == "NORTH") or \
                                 (ROBOT_HEADING == "NORTH" and desired_heading == "WEST") or \
                                 (ROBOT_HEADING == "WEST" and desired_heading == "SOUTH") or \
                                 (ROBOT_HEADING == "SOUTH" and desired_heading == "EAST"):
                                ROBOT_STATE = "TURNING_LEFT"
                                print("Action: TURN LEFT")

                            # Renk Karar Mekanizması: Doğu-Batı PEMBE, Kuzey-Güney YEŞİL
                            if desired_heading in ["EAST", "WEST"]:
                                CURRENT_TARGET_COLOR = "pink"
                            elif desired_heading in ["NORTH", "SOUTH"]:
                                CURRENT_TARGET_COLOR = "green"

                            ROBOT_HEADING = desired_heading

                    break

            # =========================================================

            # ---------------------------------------------------------
            # STATE 1 & PARKING: ÇİZGİ İZLEME
            # ---------------------------------------------------------
            if ROBOT_STATE in ["FOLLOWING", "PARKING"]:
                mask = get_color_mask(display_frame, CURRENT_TARGET_COLOR)
                error, line_detected = calculate_deviation(mask, image_width, display_frame)

                if line_detected:
                    forward_speed, angular_speed = proportional_controller(error, kp, base_speed)
                    v_left, v_right = calculate_wheel_speeds(forward_speed, angular_speed, track_width)
                    frodo.control.setTrackSpeed(v_left, v_right)
                else:
                    frodo.control.setTrackSpeed(0.0, 0.0)

                # Eğer park ediyorsak ve süremiz dolduysa motorları kalıcı olarak durdur!
                if ROBOT_STATE == "PARKING":
                    cv2.putText(display_frame, "PARKING...", (150, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 165, 255), 3)
                    if time.time() > stop_timer:
                        ROBOT_STATE = "STOPPED"

            # ---------------------------------------------------------
            # STATE 2: MANEVRA ESNASI (KÖR DÖNÜŞ)
            # ---------------------------------------------------------
            elif ROBOT_STATE in ["TURNING_LEFT", "TURNING_RIGHT"]:
                mask = get_color_mask(display_frame, CURRENT_TARGET_COLOR)
                error, line_detected = calculate_deviation(mask, image_width, display_frame)

                if ROBOT_STATE == "TURNING_LEFT":
                    frodo.control.setTrackSpeed(-turn_speed, turn_speed)
                elif ROBOT_STATE == "TURNING_RIGHT":
                    frodo.control.setTrackSpeed(turn_speed, -turn_speed)

                if line_detected and abs(error) < 30:
                    print(f"New road ({CURRENT_TARGET_COLOR}) centered! Moving forward.")
                    frodo.control.setTrackSpeed(0.0, 0.0)
                    ROBOT_STATE = "FOLLOWING"

            # --- SEND FRAME TO WEB BROWSER ---
            with stream_frame_lock:
                frame_out = display_frame

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("Interrupted by user. Shutting down motors...")
        frodo.control.setTrackSpeed(0.0, 0.0)


if __name__ == '__main__':
    main()