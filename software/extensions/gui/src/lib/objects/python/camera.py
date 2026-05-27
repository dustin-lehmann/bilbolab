import glob
import json
import os
import platform
import re
import socket
import subprocess
import threading
import logging
from typing import Any

try:
    import cv2
except ImportError:
    cv2 = None

from core.utils.exit import register_exit_callback
from core.utils.network.network import getHostIP
from core.utils.video.camera_streamer import VideoStreamer
from extensions.gui.src.lib.objects.objects import Widget


# Thread-safe port allocation
_port_lock = threading.Lock()
_allocated_ports: set[int] = set()
_PORT_RANGE_START = 8800
_PORT_RANGE_END = 8999


# ======================================================================================================================
def _allocate_camera_port() -> int:
    """Allocate a free port in the 8800-8999 range using a socket bind test."""
    with _port_lock:
        for port in range(_PORT_RANGE_START, _PORT_RANGE_END + 1):
            if port in _allocated_ports:
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(('0.0.0.0', port))
                s.close()
                _allocated_ports.add(port)
                return port
            except OSError:
                continue
        raise RuntimeError(f"No free port available in range {_PORT_RANGE_START}-{_PORT_RANGE_END}")


def _release_port(port: int):
    """Release a previously allocated port."""
    with _port_lock:
        _allocated_ports.discard(port)


# ======================================================================================================================
def _scan_cameras_macos() -> dict:
    """macOS: use system_profiler to get real camera names, then verify with OpenCV."""
    try:
        result = subprocess.run(
            ['system_profiler', 'SPCameraDataType', '-json'],
            capture_output=True, text=True, timeout=10,
        )
        entries = json.loads(result.stdout).get('SPCameraDataType', [])
    except Exception:
        entries = []

    if not entries:
        return _scan_cameras_opencv(10)

    cameras = {}
    for i, entry in enumerate(entries):
        name = entry.get('_name', f'Camera {i}')
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            cameras[str(i)] = {'label': f'{name} ({w}x{h})', 'index': i}

    return cameras if cameras else _scan_cameras_opencv(10)


def _scan_cameras_linux() -> dict:
    """Linux: enumerate /sys/class/video4linux for real device names, deduplicate."""
    cameras = {}
    seen_names = set()

    for name_path in sorted(glob.glob('/sys/class/video4linux/video*/name')):
        device = os.path.basename(os.path.dirname(name_path))
        index = int(device.replace('video', ''))

        with open(name_path) as f:
            hw_name = f.read().strip()

        # Each physical camera often creates multiple /dev/video* nodes.
        # Keep only the first (lowest index) per unique hardware name.
        if hw_name in seen_names:
            continue

        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            if w > 0 and h > 0:
                seen_names.add(hw_name)
                cameras[str(index)] = {'label': f'{hw_name} ({w}x{h})', 'index': index}

    return cameras if cameras else _scan_cameras_opencv(10)


def _scan_cameras_opencv(max_index: int) -> dict:
    """Fallback: brute-force probe indices 0..max_index with OpenCV."""
    cameras = {}
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            cameras[str(i)] = {'label': f'Camera {i} ({w}x{h})', 'index': i}
    return cameras


def scan_cameras(max_index: int = 10) -> dict:
    """
    Discover available cameras using platform-specific enumeration.

    macOS:  system_profiler SPCameraDataType (real camera names, no duplicates)
    Linux:  /sys/class/video4linux (real names, deduplicated per physical device)
    Other:  OpenCV index probing as fallback

    Returns an empty dict if OpenCV is not installed.
    """
    if cv2 is None:
        return {}
    system = platform.system()
    if system == 'Darwin':
        return _scan_cameras_macos()
    elif system == 'Linux':
        return _scan_cameras_linux()
    else:
        return _scan_cameras_opencv(max_index)


# ======================================================================================================================
class CameraWidget(Widget):
    """
    A widget that discovers available cameras, lets the user pick one via a
    dropdown, and streams the selected camera's MJPEG feed to the frontend.

    Usage:
        camera = CameraWidget(widget_id='testbed_camera', auto_start=True)
        page_group.addWidget(camera, row=1, column=1, width=5, height=5)
    """
    type = 'camera'

    def __init__(self, widget_id: str, host: str = None, auto_start: bool = True,
                 width: int = 640, height: int = 480, fps: int = 30,
                 max_scan_index: int = 10,
                 excluded: list[str] = None, priority: list[str] = None,
                 **kwargs):
        super().__init__(widget_id)

        default_config = {
            'fit': 'contain',
            'enable_enlarge': True,
            'enable_fullscreen': True,
            'lock_aspect_ratio': True,
        }
        self.config = {**default_config, **kwargs}

        self._host = host or getHostIP(priorities=['local', 'usb'])
        self._width = width
        self._height = height
        self._fps = fps
        self._max_scan_index = max_scan_index
        self._auto_start = auto_start
        self._excluded = [re.compile(p, re.IGNORECASE) for p in (excluded or [])]
        self._priority = [re.compile(p, re.IGNORECASE) for p in (priority or [])]

        self._streamer: VideoStreamer | None = None
        self._current_port: int | None = None
        self._stream_url: str | None = None
        self._selected_camera: str | None = None
        self._lock = threading.Lock()

        self._enabled = cv2 is not None
        if not self._enabled:
            self.logger.warning(
                f"[CameraWidget:{self.id}] opencv-python not installed — widget disabled. "
                f"Install with `pip install opencv-python` to enable camera streaming."
            )
            self._cameras = {}
        else:
            self._cameras = self._scan_and_filter()
            if self._auto_start and self._cameras:
                default_key = self._pick_default()
                self._start_stream(default_key)

        register_exit_callback(self.close_popout, priority=20)

    # ------------------------------------------------------------------------------------------------------------------
    def _scan_and_filter(self) -> dict:
        """Scan cameras and remove any whose label matches an excluded pattern."""
        cameras = scan_cameras(max_index=self._max_scan_index)
        if not self._excluded:
            return cameras
        return {
            key: cam for key, cam in cameras.items()
            if not any(pat.search(cam['label']) for pat in self._excluded)
        }

    def _pick_default(self) -> str:
        """Pick the best default camera key based on the priority list.

        Returns the key of the first camera whose label matches the earliest
        priority pattern.  Falls back to the first camera if nothing matches.
        """
        if self._priority:
            for pat in self._priority:
                for key, cam in self._cameras.items():
                    if pat.search(cam['label']):
                        return key
        return next(iter(self._cameras))

    # ------------------------------------------------------------------------------------------------------------------
    def _start_stream(self, camera_key: str):
        """Stop any existing stream, start a new one for the given camera key."""
        with self._lock:
            self._stop_stream_internal()

            if camera_key not in self._cameras:
                self.logger.warning(f"[CameraWidget:{self.id}] Camera key '{camera_key}' not found")
                return

            camera_index = self._cameras[camera_key]['index']
            port = _allocate_camera_port()

            try:
                streamer = VideoStreamer(
                    camera_source=camera_index,
                    host='0.0.0.0',
                    port=port,
                    path='/video',
                    stream_type='mjpeg',
                    width=self._width,
                    height=self._height,
                    fps=self._fps,
                )
                streamer.start()
            except Exception as e:
                self.logger.error(f"[CameraWidget:{self.id}] Failed to start stream: {e}")
                _release_port(port)
                return

            self._streamer = streamer
            self._current_port = port
            self._selected_camera = camera_key
            self._stream_url = f"http://{self._host}:{port}/video"
            self.logger.info(f"[CameraWidget:{self.id}] Streaming camera {camera_key} at {self._stream_url}")

    # ------------------------------------------------------------------------------------------------------------------
    def _stop_stream(self):
        """Public stop method (acquires lock)."""
        with self._lock:
            self._stop_stream_internal()

    def _stop_stream_internal(self):
        """Internal stop (must be called with lock held)."""
        if self._streamer is not None:
            try:
                self._streamer.stop()
            except Exception as e:
                self.logger.warning(f"[CameraWidget:{self.id}] Error stopping stream: {e}")
            self._streamer = None

        if self._current_port is not None:
            _release_port(self._current_port)
            self._current_port = None

        self._stream_url = None

    # ------------------------------------------------------------------------------------------------------------------
    def rescan(self):
        """Re-scan cameras and push updated list to the frontend."""
        if not self._enabled:
            return
        self.logger.info(f"[CameraWidget:{self.id}] Rescanning cameras...")
        self._cameras = self._scan_and_filter()
        self.logger.warning(f"[CameraWidget:{self.id}] Found {len(self._cameras)} camera(s): {[c['label'] for c in self._cameras.values()]}")

        # If the currently selected camera is gone, stop the stream
        if self._selected_camera and self._selected_camera not in self._cameras:
            self._stop_stream()
            self._selected_camera = None

        self.function('setCameras', {
            'cameras': self._cameras,
            'selected': self._selected_camera,
        })

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {
            'cameras': self._cameras,
            'selected': self._selected_camera,
            'stream_url': self._stream_url,
            **self.config,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        event = message.get('event')
        # self.logger.info(f"[CameraWidget:{self.id}] handleEvent: event={event}, message={message}")

        if event == 'camera_select_change':
            camera_key = message.get('camera_key')
            self.logger.debug(f"[CameraWidget:{self.id}] Camera select change: key={camera_key}, current={self._selected_camera}")
            if camera_key and camera_key != self._selected_camera:
                self._start_stream(camera_key)
                self.logger.debug(f"[CameraWidget:{self.id}] Stream started, sending URL: {self._stream_url}")
                self.function('setStreamUrl', self._stream_url)

        elif event == 'rescan':
            self.rescan()

        elif event == 'refresh':
            if self._stream_url:
                self.function('setStreamUrl', self._stream_url)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """Clean shutdown."""
        self._stop_stream()

    # ------------------------------------------------------------------------------------------------------------------
    def close_popout(self, *args, **kwargs):
        self.function(function_name='closePopout', args={})
