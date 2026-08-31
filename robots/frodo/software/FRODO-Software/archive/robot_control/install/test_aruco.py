import cv2
import cv2.aruco as arc
import numpy as np
import os
import picamera2
import sys

os.environ["LIBCAMERA_LOG_LEVELS"] = "3"

MARKER_SIZE = 0.08
ARUCO_DICT = arc.DICT_4X4_1000

camera_matrix = np.asarray(
    [[559.933357702163, 0.0, 640.5283169916149], [0.0, 556.8863039163979, 362.6814257152788], [0.0, 0.0, 1.0]])
dist_coeff = np.asarray(
    [[-0.05152339363259177, 0.1397406416805854, -0.002481788522966798, 0.0002377054578621766, -0.09210858402238659]])

print("Initializing Camera", file=sys.stderr)
try:
    picam = picamera2.Picamera2()
    picam_config = picam.create_video_configuration(raw={"size": (2304, 1296)},
                                                    main={"format": "RGB888", "size": (1280, 720)}, buffer_count=5)

    picam.configure(picam_config)
    picam.start()

except Exception as e:
    print("Error trying to initialize camera!", file=sys.stderr)
    print(e, file=sys.stderr)


def test_camera():
    print("Testing camera", file=sys.stderr)
    try:
        frame = picam.capture_array()
        return frame
    except Exception as e:
        print("Error trying to capture a frame!", file=sys.stderr)
        print(e, file=sys.stderr)


def test_aruco_detection(frame):
    dictionary = arc.getPredefinedDictionary(ARUCO_DICT)
    detector_params = arc.DetectorParameters()
    detector = arc.ArucoDetector(dictionary, detector_params)

    if frame is not None:
        try:
            marker_corners, marker_ids, rejected_candidates = detector.detectMarkers(frame)
            if marker_ids is not [] and marker_ids is not None:
                rvecs, tvecs, objpts = cv2.aruco.estimatePoseSingleMarkers(marker_corners, MARKER_SIZE, camera_matrix,
                                                                           dist_coeff)
                distances = [0 for tvec in tvecs]
                for idx, tvec in enumerate(tvecs):
                    distances[idx] = np.sqrt(tvec[0][0] ** 2 + tvec[0][1] ** 2 + tvec[0][2] ** 2)
                    print("Found Marker ", marker_ids[idx], " in distance ", distances[idx], file=sys.stderr)
            else:
                print("No Markers found, but everything else is working!")
        except Exception as e:
            print("Could not analyze for Aruco Markers!", file=sys.stderr)
            print(e, file=sys.stderr)
    else:
        print("Could not test Aruco Detection, as no frame could be captured!", file=sys.stderr)


if __name__ == "__main__":
    test_frame = test_camera()
    test_aruco_detection(test_frame)
