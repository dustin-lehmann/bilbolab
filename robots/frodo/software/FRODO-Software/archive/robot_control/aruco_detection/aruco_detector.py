import datetime
import sys
import threading
import time
import yaml
from flask import Response
from flask import Flask
from flask import render_template
import pathlib

import cv2
import cv2.aruco as arc
import numpy as np
import picamera2

# local imports
import archive.robot_control.aruco_detection.utils.chess_calibration_old as calibration
from archive.robot_control.aruco_detection.utils.ip import get_ip_address

V3_CALIB_PATH = '/home/admin/robot_old/software/aruco/calibrations/calibration_v3_chess.yaml'
V2_CALIB_PATH = './aruco/calibrations/calibration_v2_chess.yaml'
V1_CALIB_PATH = './aruco/calibrations/calibration_v1_chess.yaml'

MARKER_SIZE = 0.08


class ArucoDetector:
    calibrate: bool
    '''Calibration Routine on Start'''
    streaming: bool
    '''Stream Video Feed of Robot to Flask Server'''
    auto_measurements: bool
    '''Repetetivly capture Pictures in Thread'''
    version: str
    '''Version of Camera Module'''

    dictionary: arc.Dictionary
    '''Dictionary of Aruco Markers'''
    detector: arc.ArucoDetector
    '''cv2.aruco.ArucoDetector Object'''
    detector_params: arc.DetectorParameters
    '''Configuration Parameters for cv2.aruco.ArucoDetector'''

    picam: picamera2.Picamera2
    '''Picamera2 Object'''
    picam_config: picamera2.configuration
    '''Configuration Parameters for Picamera2 Object'''

    orig_frame: np.array
    '''Original Frame captured by picam'''
    out_frame: bytes
    '''Output Frame for Streaming with highlighted Aruco Markers'''
    stream_if: str
    '''Interface for Output Frame Streaming'''

    cam_matrix: np.array
    '''Camera Configuration Matrix'''
    cam_dist_coeff: np.array
    '''Camera Distortion Coefficient'''

    collect_img_task: threading.Thread
    '''Thread for Capturing Images (activated by self.auto_measurements)'''
    measurement_task: threading.Thread
    '''Thread for automated Image Analysiss (activated by self.auto_measurements)'''
    calibration_task: threading.Thread
    '''Thread for generating a Calibration before start (activated by self.calibrate)'''
    flask_task: threading.Thread
    '''Thread for Flask Server to stream Output Frame (activated by self.streaming)'''

    def __init__(self, version="v3", stream_if="wlan0", calibrate=False, streaming=False, auto_measurements=False):

        # init program parameters
        self.calibrate = calibrate
        self.streaming = streaming
        self.auto_measurements = auto_measurements
        self.version = version

        # init Aruco
        # self.dictionary = arc.getPredefinedDictionary(arc.DICT_6X6_250)
        self.dictionary = arc.getPredefinedDictionary(arc.DICT_4X4_1000)
        self.detector_params = arc.DetectorParameters()
        self.detector = arc.ArucoDetector(self.dictionary, self.detector_params)

        # init Picam
        self.picam = picamera2.Picamera2()
        if version == "v2":
            self.picam_config = self.picam.create_video_configuration(raw={"size": (1640, 1232)},
                                                                      main={"format": "RGB888", "size": (640, 480)},
                                                                      buffer_count=5)
        elif version == "v3":
            self.picam_config = self.picam.create_video_configuration(raw={"size": (2304, 1296)},
                                                                      main={"format": "RGB888", "size": (1280, 720)},
                                                                      buffer_count=5)
        elif version == "v1":
            self.picam_config = self.picam.create_video_configuration(raw={"size": (2592, 1944)},
                                                                      main={"format": "RGB888", "size": (640, 480)},
                                                                      buffer_count=5)

        self.picam.configure(self.picam_config)
        self.picam.start()
        self.orig_frame = None
        self.out_frame = None
        self.stream_if = stream_if
        time.sleep(2.0)

        # init camera calibration parameters, if existing calibration shall be used
        if not calibrate:
            self.__init_calibration()

        # init tasks
        self.collect_img_task = threading.Thread(target=self.__get_frame)
        self.measurement_task = threading.Thread(target=self.__measurements)
        self.calibration_task = threading.Thread(target=self.__generate_calib_data)
        self.flask_task = threading.Thread(target=self.__flask)

    def __init_calibration(self, calib_path=""):
        '''init cv2 camera calibration parameters'''
        if calib_path == "":
            if self.version == "v2":
                calib_path = V2_CALIB_PATH
            elif self.version == "v3":
                calib_path = V3_CALIB_PATH
            elif self.version == "v1":
                calib_path = V1_CALIB_PATH

        # Load saved Parameters
        loadeddict = None
        with open(calib_path) as f:
            loadeddict = yaml.safe_load(f)

        mtx = loadeddict.get("camera_matrix")
        dist = loadeddict.get("dist_coeff")
        self.cam_matrix = np.array(mtx)
        self.cam_dist_coeff = np.array(dist)

        print("Successfully calibrated camera!", file=sys.stderr)

    def start(self):
        '''start Aruco Detector, activate configured features'''

        # capture one frame to not start with empty frame
        self.orig_frame = self.picam.capture_array()
        if self.streaming:
            self.flask_task.start()
        if self.auto_measurements:
            self.collect_img_task.start()
            self.measurement_task.start()
        if self.calibrate:
            self.calibration_task.start()
            self.calibration_task.join()


    def __flask(self):
        '''web stream of current output frame to stream_if:5000'''
        app = Flask(__name__)
        ip = get_ip_address(self.stream_if)

        def send_frames():
            time1 = time.perf_counter()
            while True:
                if self.out_frame is not None:
                    # print(f"time: {time.perf_counter() - time1}")
                    time1 = time.perf_counter()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + self.out_frame + b'\r\n')
                    self.out_frame = None

                time.sleep(0.01)

        @app.route('/')
        def index():
            return render_template('index.html')

        @app.route('/video_feed')
        def video_feed():
            return Response(send_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

        app.run(debug=True, threaded=True, host=ip, use_reloader=False)

    def __generate_calib_data(self):
        '''- function to capture calibration images and build a calibration
           - when configured to, called before start
           - saves calibration at ./calib_data/calibration_your_custom_input.yaml'''
        path = "./calib_data/"

        # create calib_data folder, if not exists
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
        count = 0
        time.sleep(3)

        # Capture images as calibration data, repeat at least 20 times
        print("Started Data Generation, press Enter to Capture, write exit to continue with calibration build",
              file=sys.stderr)
        while True:
            if self.picam is not None:
                print("Press Enter to Capture", file=sys.stderr)
                msg = input()
                if msg == 'exit':
                    break
                name = path + str(count) + ".jpg"
                img = self.picam.capture_array()
                cv2.imwrite(name, img)
                print(f"wrote image {count}", file=sys.stderr)
                count += 1
            time.sleep(0.1)
        msg = input("Desired Calibration File name, empty for standard: ")
        msg = "calibration_" + self.version + "_" + msg + ".yaml"

        print("Calculate calibration")
        calib_path = calibration.main(filename=msg)
        self.__init_calibration(calib_path=calib_path)

    def __get_frame(self):
        '''capture frame and analyze for video output'''
        while True:
            self.orig_frame = self.picam.capture_array()
            ret, buffer = cv2.imencode('.jpg', self.orig_frame)
            # normal detection, work on frame copy to not mess with original frame
            frame_cpy = np.copy(self.orig_frame)
            marker_corners, marker_ids, rejected_candidates = self.detector.detectMarkers(self.orig_frame)
            frame_out = np.copy(self.orig_frame)

            if marker_ids is not [] and marker_ids is not None:
                # frame_cpy will be changed too, as drawDetectedMarkers(...) is originally a c++ function
                frame_out = arc.drawDetectedMarkers(frame_cpy, marker_corners, marker_ids)
            else:
                if not self.calibrate and self.auto_measurements:
                    ...
                    # print("No markers found (Vis)", file=sys.stderr)
            ret, buffer = cv2.imencode('.jpg', frame_out)
            self.out_frame = buffer.tobytes()
            time.sleep(0.04)

    def get_out_frame(self):
        return self.out_frame

    def measurement(self):
        '''- measure translation and rotation of all visible aruco markers;
            - return: list of marker IDs, list of translation vecs, list of rotation vecs'''
        # capture frame
        if not self.auto_measurements:
            self.orig_frame = self.picam.capture_array()

        # image analysis
        if self.orig_frame is not None:
            marker_corners, marker_ids, rejected_candidates = self.detector.detectMarkers(self.orig_frame)

            if marker_ids is not [] and marker_ids is not None:
                rotation_vec, translation_vec, objpts = cv2.aruco.estimatePoseSingleMarkers(marker_corners,
                                                                                            MARKER_SIZE,
                                                                                            self.cam_matrix,
                                                                                            self.cam_dist_coeff)

                return marker_ids, translation_vec, rotation_vec
            else:
                return [], [], []
        else:
            return [], [], []

    def __measurements(self):
        '''- measure distorted and undistorted translation and rotation of current image and print to stdout 
            - values only calculated for first visible marker'''
        msr_cnt = 0
        print("time; dist_trans; dist_rot; undist_trans; undist_rot")
        while True:
            print("Input message to name measurement, press enter to measure", file=sys.stderr)
            msg = input()
            print("measurement", msr_cnt, msg)
            msr_cnt += 1
            j = 0
            while j < 10:
                if self.orig_frame is not None:
                    dist_rotation_vec = []
                    dist_translation_vec = []

                    #distorted image analysis
                    marker_corners, marker_ids, rejected_candidates = self.detector.detectMarkers(self.orig_frame)
                    j += 1
                    if marker_ids is not [] and marker_ids is not None:
                        dist_rotation_vec, dist_translation_vec, objpts = cv2.aruco.estimatePoseSingleMarkers(
                            marker_corners, 0.08,
                            self.cam_matrix,
                            self.cam_dist_coeff)
                        distance = np.sqrt(dist_translation_vec[0][0][0] ** 2 + dist_translation_vec[0][0][1] ** 2 +
                                           dist_translation_vec[0][0][2] ** 2)

                        print("Distorted Distance:", distance, file=sys.stderr)
                    else:
                        print(f"No markers found in distorted image, Measurement {msr_cnt}, Iteration {j}",
                              file=sys.stderr)

                    current_time = datetime.datetime.now()
                    # print(current_time, ";", dist_translation_vec, ";", dist_rotation_vec)
                    time.sleep(0.3)
            print("Measurement written!", file=sys.stderr)


if __name__ == '__main__':
    #select Version from ["v2", "v3"]
    arc_detector = ArucoDetector(version="v3", stream_if="wlan0", calibrate=True, streaming=True, auto_measurements=False)
    arc_detector.start()

    while True:
        marker_ids, translation_vec, rotation_vec = arc_detector.measurement()
        if len(marker_ids) > 0:
            print(f"Marker IDs: {marker_ids}")
        time.sleep(1)
