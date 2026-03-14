import asyncio
import json
import logging
import os
import threading
import time
import queue

import qmt
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.logging_utils import Logger

babylon_path = os.path.join(os.path.dirname(__file__), "babylon_lib")


@callback_definition
class BabylonCallbacks:
    loaded: CallbackContainer


class BabylonVisualization:
    """
    Manages the BabylonJS visualization web application.
    """

    def __init__(self, webapp: str = os.path.join(babylon_path, 'pysim_env.html'),
                 webapp_config=None, world_config=None,
                 object_mappings=os.path.join(babylon_path, 'object_config.json'),
                 show: str = 'chromium'):
        """
        Initialize the BabylonVisualization instance.
        """
        self._config = {
            'objects': {},
            'world': {},
            'object_mappings': {},
            'webapp': {}
        }

        self.callbacks = BabylonCallbacks()
        self.logger = Logger('BABYLON', 'INFO')

        # Load object mapping configuration from file if needed.
        if isinstance(object_mappings, str):
            with open(object_mappings) as f:
                object_mappings = json.load(f)
        self._config['object_mappings'] = object_mappings

        # Set world and webapp configuration.
        self._config['world'] = world_config if world_config is not None else {}
        self._config['webapp'] = webapp_config if webapp_config is not None else {}

        self.webapp_path = webapp
        self.objects = {}  # Stores BabylonObject instances keyed by their ID.
        self._last_sample = {}
        self._run = False
        self._tx_queue = queue.Queue()
        self._pending_updates = {}  # For update messages, keyed by object ID.
        self._last_flush_time = time.time()
        self._webapp = None
        self._webappProcess = None
        self._show = show
        self.loaded = False
        self.Ts = 0.05  # Minimum interval (in seconds) between update messages.

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        """
        Initialize the web app visualization.
        (Any additional initialization code can be added here.)
        """
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        """
        Start the visualization in a separate thread.
        """
        logging.info("Starting Babylon visualization")
        self._thread = threading.Thread(target=self._threadFunction, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, obj):
        """
        Add a BabylonObject instance to the scene.
        """
        self.objects[obj.object_id] = obj
        # Set the visualization reference so the object can send updates automatically.
        obj.vis = self
        message = obj.to_message()
        message['type'] = 'addObject'
        self.sendData(message)

        obj.callbacks.updateConfig.register(self._updateObject_callback)

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, object_id):
        """
        Remove an object from the scene by its ID.
        """
        if object_id in self.objects:
            self.objects[object_id].on_remove()
            del self.objects[object_id]
        data = {
            'type': 'removeObject',
            'data': {'id': object_id}
        }
        self.sendData(data)

    # ------------------------------------------------------------------------------------------------------------------
    def updateObject(self, object_id, data: dict):
        """
        Update an object in the scene.
        """
        if object_id in self.objects:
            self.objects[object_id].update_from_data(data)
        data = {
            'type': 'update',
            'data': {'id': object_id, 'data': data}
        }
        self.sendData(data)

    # ------------------------------------------------------------------------------------------------------------------
    def _updateObject_callback(self, obj):
        data = {
            'type': 'update',
            'data': {'id': obj.object_id, 'data': obj.data}
        }
        self.sendData(data)

    # ------------------------------------------------------------------------------------------------------------------
    def set(self, object_id, parameter, value):
        """
        Set a parameter of an object in the scene.
        """
        data = {
            'type': 'set',
            'data': {'id': object_id, 'parameter': parameter, 'value': value}
        }
        self.sendData(data)

    # ------------------------------------------------------------------------------------------------------------------
    def function(self, object_id, function_name, arguments: list):
        """
        Call a function on an object in the scene.
        """
        data = {
            'type': 'function',
            'data': {'id': object_id, 'function': function_name, 'arguments': arguments}
        }
        self.sendData(data)

    # ------------------------------------------------------------------------------------------------------------------
    def sendSample(self, sample_dict: dict):
        """
        Send a sample update to the web app.
        """
        data = {'type': 'sample', 'data': sample_dict}
        self.sendData(data)

    # ------------------------------------------------------------------------------------------------------------------
    def sendData(self, data):
        """
        Queue data to be sent to the web app.
        For update messages, only the latest update per object is kept.
        """
        if data.get('type') == 'update':
            object_id = data['data']['id']
            self._pending_updates[object_id] = data
        else:
            self._tx_queue.put(data)

    # ------------------------------------------------------------------------------------------------------------------
    def setWorldConfig(self, world_config):
        """
        Set the world configuration.
        """
        self._config['world'] = world_config

    # === PRIVATE METHODS ==============================================================================================
    def _sendTxQueue(self):
        """
        Send all queued messages to the web app if the update interval has passed.
        """
        if not self.loaded:
            return
        now = time.time()
        if now - self._last_flush_time < self.Ts:
            return
        # Send non-update messages.
        while not self._tx_queue.empty():
            data = self._tx_queue.get()
            self._sendData(data)
        # Send the latest update message per object.
        for data in self._pending_updates.values():
            self._sendData(data)
        self._pending_updates.clear()
        self._last_flush_time = now

    # ------------------------------------------------------------------------------------------------------------------
    def _sendData(self, data):
        """
        Send a single message to the web app.
        """
        if self._webappProcess is not None:
            try:
                self._webappProcess.sendSample(data)
            except Exception as e:
                print("Webapp not reachable:", e)
                exit()

    # ------------------------------------------------------------------------------------------------------------------
    def _pollEvents(self):
        """
        Poll for events from the web app.
        """
        try:
            params = self._webappProcess.getParams(clear=True)
        except Exception:
            return

        if params:
            self._checkEvents(params)

    # ------------------------------------------------------------------------------------------------------------------
    def _checkEvents(self, params: dict = None):
        """
        Check for specific events in the parameters.
        """
        if params and 'loaded' in params:
            self.logger.info("Webapp loaded")
            self.loaded = True
            self.callbacks.loaded.call()

    # ------------------------------------------------------------------------------------------------------------------
    def _threadFunction(self):
        """
        Thread function for handling communication with the web app.
        """
        asyncio.set_event_loop(asyncio.new_event_loop())
        self._webapp = qmt.Webapp(self.webapp_path, config=self._config, show=self._show)
        self._webappProcess = self._webapp.runInProcess()

        while True:
            self._sendTxQueue()
            self._pollEvents()
            time.sleep(0.01)
