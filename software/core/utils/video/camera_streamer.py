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
        self.cap = self._open_capture()

        # For MJPEG server
        self.app = Flask(__name__)
        # Suppress Flask/Werkzeug dev-server warning and per-request access logs
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        self._setup_routes()

        self.thread = None              # Flask server thread
        self._capture_thread = None     # background frame grabber thread
        self.is_running = False

        # Latest encoded JPEG frame, shared between the grabber and all client
        # generators. The condition variable lets each client block until a new
        # frame is available (and wakes them on shutdown).
        self._latest_jpeg = None
        self._frame_seq = 0
        self._frame_cond = threading.Condition()

    # ------------------------------------------------------------------------------------------------------------------
    def _open_capture(self):
        """Open the VideoCapture and apply the desired capture settings."""
        cap = cv2.VideoCapture(self.camera_source)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        return cap

    def _reopen_capture(self):
        """Release and reopen the capture device to recover from a stalled camera."""
        try:
            self.cap.release()
        except Exception:
            pass
        self.cap = self._open_capture()

    # ------------------------------------------------------------------------------------------------------------------
    def _capture_loop(self):
        """Continuously grab frames into the shared buffer.

        Runs from start() onward, independently of whether any client is
        connected. This keeps the camera actively read so it never goes into the
        opened-but-idle state that makes ``cap.read()`` fail permanently on many
        UVC / AVFoundation backends. On repeated read failures it reopens the
        device so the stream self-heals instead of going dark until a restart.
        """
        frame_interval = 1.0 / self.fps
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        next_frame_time = time.monotonic()
        consecutive_failures = 0

        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                consecutive_failures += 1
                # ~1.5 s of failed reads (at the target fps) → assume the camera
                # has stalled and try to recover it.
                if consecutive_failures >= max(int(self.fps * 1.5), 15):
                    print(f"[VideoStreamer] camera read failing, reopening {self.camera_source}")
                    self._reopen_capture()
                    consecutive_failures = 0
                time.sleep(0.05)
                continue
            consecutive_failures = 0

            ret2, jpeg = cv2.imencode('.jpg', frame, encode_params)
            if not ret2:
                continue

            with self._frame_cond:
                self._latest_jpeg = jpeg.tobytes()
                self._frame_seq += 1
                self._frame_cond.notify_all()

            # Sleep only the remaining time to hit the target frame rate
            next_frame_time += frame_interval
            sleep_time = next_frame_time - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_frame_time = time.monotonic()

    def _frame_generator(self):
        """Yield the latest grabbed JPEG as multipart/x-mixed-replace for MJPEG.

        Serves whatever the grabber last produced, so multiple clients can read
        the same camera concurrently and a slow client simply skips to the most
        recent frame instead of competing for ``cap.read()``.
        """
        # Start at the grabber's initial sequence so the first iteration blocks
        # until a real frame exists (rather than busy-spinning before frame 1).
        last_seq = 0
        while self.is_running:
            with self._frame_cond:
                # Block until a frame newer than the one we last sent is ready.
                while self.is_running and self._frame_seq == last_seq:
                    self._frame_cond.wait(timeout=1.0)
                if not self.is_running:
                    break
                if self._latest_jpeg is None:
                    continue
                frame_bytes = self._latest_jpeg
                last_seq = self._frame_seq

            yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )

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

        # Start grabbing frames immediately so the camera is never left opened-but-idle.
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

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
        # Wake any blocked client generators so they can exit.
        with self._frame_cond:
            self._frame_cond.notify_all()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
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
