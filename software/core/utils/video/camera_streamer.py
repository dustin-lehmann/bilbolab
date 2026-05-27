try:
    import cv2
except ImportError:
    cv2 = None
import logging
import threading
import time
from flask import Flask, Response, stream_with_context


class VideoStreamer:
    def __init__(self,
                 camera_source=0,
                 host='0.0.0.0',
                 port=5000,
                 path='/video',
                 stream_type='mjpeg',
                 width=640,
                 height=480,
                 fps=30,
                 jpeg_quality=70):
        """
        camera_source: 0,1,... for webcam, or string '/dev/video0', or Raspberry Pi CSI camera pipeline
        host, port: where to bind the server
        path: URL path (e.g. '/video' or '/stream1')
        stream_type: 'mjpeg' or 'rtsp'
        width, height, fps: desired capture settings
        jpeg_quality: JPEG encode quality (1-100, lower = smaller/faster)
        """
        self.camera_source = camera_source
        self.host = host
        self.port = port
        self.path = path
        self.stream_type = stream_type.lower()
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality

        assert self.stream_type in ['mjpeg', 'rtsp'], "stream_type must be 'mjpeg' or 'rtsp'"
        if self.stream_type == 'rtsp':
            raise NotImplementedError(
                "[RTSP] Note: RTSP support is a placeholder. You would need to implement a GStreamer or live555 server.")

        if cv2 is None:
            raise RuntimeError("VideoStreamer requires opencv-python; install with `pip install opencv-python`")

        # VideoCapture
        self.cap = cv2.VideoCapture(self.camera_source)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        # For MJPEG server
        self.app = Flask(__name__)
        # Suppress Flask/Werkzeug dev-server warning and per-request access logs
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        self._setup_routes()

        self.thread = None
        self.is_running = False

    def _frame_generator(self):
        """Yield JPEG frames as multipart/x-mixed-replace for MJPEG."""
        frame_interval = 1.0 / self.fps
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        next_frame_time = time.monotonic()

        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                continue
            ret2, jpeg = cv2.imencode('.jpg', frame, encode_params)
            if not ret2:
                continue
            frame_bytes = jpeg.tobytes()
            yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )
            # Sleep only the remaining time to hit the target frame rate
            next_frame_time += frame_interval
            sleep_time = next_frame_time - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_frame_time = time.monotonic()

    def _setup_routes(self):
        @self.app.route(self.path)
        def video_feed():
            return Response(
                stream_with_context(self._frame_generator()),
                mimetype='multipart/x-mixed-replace; boundary=frame'
            )

        @self.app.route('/')
        def index():
            return (
                f"<html><body>"
                f"<h1>VideoStreamer MJPEG</h1>"
                f"<img src='{self.path}'/>"
                f"</body></html>"
            )

    def _run_mjpeg(self):
        # Start Flask in its own thread
        self.app.run(host=self.host, port=self.port, threaded=True,
                     debug=False, use_reloader=False)

    def _run_rtsp(self):
        # Placeholder for RTSP: in practice, you'd launch GStreamer / live555 here
        print(f"[RTSP] Would run RTSP server at rtsp://{self.host}:{self.port}{self.path}")

    def start(self):
        """Starts the chosen streaming server."""
        if self.is_running:
            print("Already running!")
            return
        self.is_running = True

        if self.stream_type == 'mjpeg':
            self.thread = threading.Thread(target=self._run_mjpeg, daemon=True)
        elif self.stream_type == 'rtsp':
            self.thread = threading.Thread(target=self._run_rtsp, daemon=True)
        else:
            raise ValueError("stream_type must be 'mjpeg' or 'rtsp'")
        self.thread.start()
        print(f"Started {self.stream_type.upper()} stream on {self.host}:{self.port}{self.path}")

    def stop(self):
        """Stops streaming and releases the camera."""
        self.is_running = False
        time.sleep(0.5)  # allow threads to wind down
        self.cap.release()
        print("Stopped streaming and released camera.")


if __name__ == '__main__':
    # Example usage:
    streamer = VideoStreamer(
        camera_source=0,
        host='0.0.0.0',
        port=8000,
        path='/video',
        stream_type='mjpeg',
        width=1280,
        height=720,
        fps=24
    )
    try:
        streamer.start()
        print("Press Ctrl+C to stop...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        streamer.stop()
