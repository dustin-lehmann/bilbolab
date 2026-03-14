import logging

from flask import Flask, send_from_directory, request
from flask_cors import CORS
from flask_socketio import SocketIO
import os
import pty
import select
import threading

from core.utils.dict_utils import update_dict
from core.utils.exit import register_exit_callback
from extensions.gui.src.lib.objects.objects import Widget

# ───────── disable Flask/Werkzeug access logs ─────────
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)  # only ERROR+ will be printed
werkzeug_logger.propagate = False  # don’t bubble up


class TerminalWidget(Widget):
    type = "terminal"
    port: int = 5555
    initial_path: str = "~"

    def __init__(self, widget_id, host, **kwargs):
        super(TerminalWidget, self).__init__(widget_id, **kwargs)

        default_config = {
            # you can add 'static_folder' or other options here if needed
        }

        self.config = update_dict(default_config, self.config, kwargs)
        self.host = host

        self._initialized = False
        self._stop_event = threading.Event()
        self._fd = None
        self._server_thread = None

        self.app = None
        self.socketio = None

        self.start()

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def initializeServer(self):
        if self._initialized:
            return
        self._initialized = True

        # Create Flask app
        static_folder = self.config.get('../../assets', None)
        self.app = Flask(__name__,
                         static_folder=static_folder,
                         static_url_path='/')
        CORS(self.app, origins="*")

        # Create SocketIO
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")

        # # Serve index.html
        # @self.app.route('/')
        # def index():
        #     return send_from_directory(self.app.static_folder, 'index.html')

        # Optional shutdown endpoint
        @self.app.route('/shutdown')
        def shutdown():
            func = request.environ.get('werkzeug.server.shutdown')
            if func:
                func()
            return 'Shutting down...', 200

        # Handle terminal input from client
        @self.socketio.on('input')
        def _handle_input(data):
            if self._fd is not None:
                os.write(self._fd, data.encode())

        # On client connect: fork a PTY, launch shell, and start reader thread
        # @self.socketio.on('connect')
        # def _handle_connect():
        #     self._stop_event.clear()
        #     def read_and_emit(fd):
        #         max_read_bytes = 1024 * 20
        #         while not self._stop_event.is_set():
        #             # give other greenlets/threads some time
        #             self.socketio.sleep(0.01)
        #             if select.select([fd], [], [], 0)[0]:
        #                 output = os.read(fd, max_read_bytes).decode(errors='ignore')
        #                 self.socketio.emit('output', output)
        #
        #     pid, fd = pty.fork()
        #     if pid == 0:
        #         # child process: launch shell
        #         os.chdir(os.path.expanduser(self.initial_path))
        #         shell = os.environ.get('SHELL', '/bin/bash')
        #         os.execvpe(shell, [shell], {**os.environ, "TERM": "xterm-256color"})
        #     else:
        #         # parent: save fd and start reader thread
        #         self._fd = fd
        #         reader = threading.Thread(target=read_and_emit, args=(fd,))
        #         reader.daemon = True
        #         reader.start()

        @self.socketio.on('connect')
        def _handle_connect():
            self._stop_event.clear()

            def read_and_emit(fd):
                max_read_bytes = 1024 * 20
                while not self._stop_event.is_set():
                    # yield to the Socket.IO event loop
                    self.socketio.sleep(0.01)
                    try:
                        rlist, _, _ = select.select([fd], [], [], 0)
                        if rlist:
                            output = os.read(fd, max_read_bytes).decode(errors='ignore')
                            self.socketio.emit('output', output)
                    except (OSError, ValueError):
                        # pty was closed or invalid, stop reading
                        break

            pid, fd = pty.fork()
            if pid == 0:
                os.chdir(os.path.expanduser(self.initial_path))
                shell = os.environ.get('SHELL', '/bin/bash')
                os.execvpe(shell, [shell], {**os.environ, "TERM": "xterm-256color"})
            else:
                self._fd = fd
                # schedule the reader as a Socket.IO background task
                self.socketio.start_background_task(read_and_emit, fd)

        @self.socketio.on('disconnect')
        def _handle_disconnect(sid):
            # only tear down the PTY for this client,
            # but keep the Flask/SocketIO server running
            self._stop_event.set()
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None

    # ------------------------------------------------------------------------------------------------------------------
    def startServer(self):
        if self._server_thread is not None:
            return
        # Ensure server is initialized
        self.initializeServer()

        def _run():
            # Note: allow_unsafe_werkzeug=True needed for Flask 2.x inside threads
            self.socketio.run(self.app,
                              host=self.host,
                              port=self.port,
                              allow_unsafe_werkzeug=True)

        self._server_thread = threading.Thread(target=_run)
        self._server_thread.daemon = True
        self._server_thread.start()

    # alias to match user expectation
    def start(self):
        self.startServer()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        # signal reader threads to stop
        self._stop_event.set()

        # attempt to close PTY
        try:
            if self._fd is not None:
                os.close(self._fd)
        except Exception:
            pass

        # shut down Flask server
        try:
            import requests
            requests.get(f'http://{self.host}:{self.port}/shutdown')
        except Exception:
            pass

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {
            'id': self.id,
            'type': self.type,
            'host': self.host,
            'port': self.port,
            **self.config
        }

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        ...
