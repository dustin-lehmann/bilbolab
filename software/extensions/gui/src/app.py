from __future__ import annotations

import dataclasses
import threading
import time

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.colors import random_color_from_palette
from core.utils.dataclass_utils import asdict_optimized
from core.utils.events import Event, event_definition
from core.utils.exit import register_exit_callback
from core.utils.files import get_absolute_path
from core.utils.js.vite import run_vite_app
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP
from core.utils.websockets.aiohttp_websocket_server import AioHttpWebsocketServer, AioHttpWebsocketClient
from extensions.gui.settings import WS_PORT_MOBILE, PORT_JS_APP
from extensions.gui.src.gui import GUI_UpdateMessage, InitMessage
from extensions.gui.src.lib.messages import AddMessage, AddMessageData, RemoveMessage, RemoveMessageData
from extensions.gui.src.lib.objects.objects import Widget, UpdateMessage, Widget_Group, \
    FunctionMessage, ObjectMessage
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.checkbox import CheckboxWidget
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.sliders import SliderWidget
from core.utils.dict_utils import update_dict

from extensions.gui.src.lib.utilities import split_path


class FolderButton(Button):
    folder: Folder | None = None

    def __init__(self, button_id, folder: Folder = None, **kwargs):
        super().__init__(button_id, **kwargs)
        self.folder = folder

        self.config['text'] = folder.id.capitalize() if folder else 'Folder'

        self.callbacks.click.register(lambda *args, **kwargs: self.logger.debug(f"FolderButton {self.id} clicked."))

    def getConfiguration(self) -> dict:
        config = super().getConfiguration()
        config['folder'] = self.folder.uid if self.folder else None
        return config

    def getPayload(self) -> dict:
        payload = super().getPayload()
        payload['type'] = 'folder_button'
        return payload


# ======================================================================================================================
@dataclasses.dataclass
class FolderPageConfig:
    ...


@dataclasses.dataclass
class FolderPagePayload:
    ...


@dataclasses.dataclass
class FolderPageObjectInstance:
    instance: Widget
    row: int
    column: int
    width: int
    height: int


@callback_definition
class FolderPageCallbacks:
    open: CallbackContainer


@event_definition
class FolderPageEvents:
    open: Event


class FolderPage:
    folder: Folder | None = None
    objects: dict[str, FolderPageObjectInstance]
    position: int | None = None

    def __init__(self, page_id=None, **kwargs):
        self.id = page_id if page_id is not None else str(id(self))

        default_config = {
            'rows': 2,
            'columns': 6,
            'gap': 5,  # px
            'name': self.id,
            'fill_empty_cells': True
        }

        self.config = update_dict(default_config, kwargs)

        self.objects = {}

        self.callbacks = FolderPageCallbacks()
        self.events = FolderPageEvents()
        self.logger = Logger(f"Page {self.id}", level="DEBUG")

        self._rows = self.config.get('rows')
        self._cols = self.config.get('columns')
        self._occupied = [[False for _ in range(self._cols)] for _ in range(self._rows)]

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, obj: Widget, row=None, column=None, width=1, height=1, **kwargs) -> Widget:

        if not isinstance(obj, Widget):
            raise TypeError(f"Expected GUI_Object, got {type(obj)}")

        if isinstance(obj, FolderButton):
            # TODO: I need to check if the folder already has an app
            ...

        instance = obj

        if instance.id in self.objects:
            raise ValueError(f"Object with id {instance.id} already exists in page {self.id}.")

        if row is None or column is None:
            row, column = self._placeObject(row, column, width, height)
        else:
            self._checkSpace(row, column, width, height)

        # Mark the space as occupied
        self._markSpace(row, column, width, height)

        self.objects[instance.id] = FolderPageObjectInstance(
            instance=instance,
            row=row,
            column=column,
            width=width,
            height=height
        )

        instance.parent = self

        message = AddMessage(
            data=AddMessageData(
                type='object',
                parent=self.uid,
                id=instance.uid,
                config={
                    'row': row,
                    'column': column,
                    'width': width,
                    'height': height,
                    **instance.getPayload(),
                })
        )

        self.sendMessage(message)

        return instance

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, obj: Widget | str) -> None:
        if isinstance(obj, Widget):
            instance = self.objects.get(obj.id).instance
            if instance is None:
                raise ValueError(f"No object with id {obj.id} found in page {self.id}.")
        elif isinstance(obj, str):
            folder_object_instance = self.objects.get(obj)
            if folder_object_instance is None:
                raise ValueError(f"No object with id {obj} found in page {self.id}.")
            instance = folder_object_instance.instance  # Get the instance from the FolderPageObjectInstance
        else:
            raise TypeError(f"Expected GUI_Object or GUI_Object_Instance, got {type(obj)}")

        if instance.id not in self.objects:
            raise ValueError(f"Object with id {instance.id} does not exist in page {self.id}.")

        # Free the occupied space
        row = self.objects[instance.id].row
        column = self.objects[instance.id].column
        width = self.objects[instance.id].width
        height = self.objects[instance.id].height

        for r in range(row - 1, row - 1 + height):
            for c in range(column - 1, column - 1 + width):
                self._occupied[r][c] = False

        message = RemoveMessage(
            data=RemoveMessageData(
                type='object',
                parent=self.uid,
                id=instance.uid,
            )
        )

        self.sendMessage(message)
        instance.parent = None
        del self.objects[instance.id]

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self) -> str:
        if isinstance(self.folder, Folder):
            return f"{self.folder.uid}/{self.id}"
        else:
            return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def getApp(self):
        return self.folder.getApp() if self.folder else None

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        return self.getApp()

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, message):
        app = self.getApp()
        if app is not None:
            try:
                app.broadcast(message)
            except Exception as e:
                self.logger.error(f"Failed to send message: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def _placeObject(self, row, column, width, height):
        """
        Finds the first available position for an object of given size.
        If one coordinate is fixed, searches along the other.
        """

        # Helper to test a candidate position
        def fits(r, c):
            if r < 1 or c < 1 or r + height - 1 > self._rows or c + width - 1 > self._cols:
                return False
            for rr in range(r - 1, r - 1 + height):
                for cc in range(c - 1, c - 1 + width):
                    if self._occupied[rr][cc]:
                        return False
            return True

        # Neither fixed: scan rows then cols
        if row is None and column is None:
            for r in range(1, self._rows - height + 2):
                for c in range(1, self._cols - width + 2):
                    if fits(r, c):
                        return r, c
        # Row fixed: scan columns
        elif row is not None and column is None:
            for c in range(1, self._cols - width + 2):
                if fits(row, c):
                    return row, c
        # Column fixed: scan rows
        elif column is not None and row is None:
            for r in range(1, self._rows - height + 2):
                if fits(r, column):
                    return r, column

        raise ValueError("No available space to place object")

    # ------------------------------------------------------------------------------------------------------------------
    def _checkSpace(self, row, column, width, height):
        # Validate bounds
        if row < 1 or column < 1 or row + height - 1 > self._rows or column + width - 1 > self._cols:
            raise ValueError("Object does not fit within grid bounds")
        # Check occupancy
        for r in range(row - 1, row - 1 + height):
            for c in range(column - 1, column - 1 + width):
                if self._occupied[r][c]:
                    raise ValueError("Grid cells already occupied")

    # ------------------------------------------------------------------------------------------------------------------
    def _markSpace(self, row, column, width, height):
        # Mark the grid cells as occupied
        for r in range(row - 1, row - 1 + height):
            for c in range(column - 1, column - 1 + width):
                self._occupied[r][c] = True

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'id': self.uid,
            'type': 'page',
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:

        objs = {}

        for uid, info in self.objects.items():
            obj = info.instance
            payload = obj.getPayload()
            payload.update({
                'row': info.row,
                'column': info.column,
                'width': info.width,
                'height': info.height,
            })
            objs[uid] = payload

        page_payload = {
            'id': self.uid,
            'type': 'page',
            'position': self.position,
            'config': self.getConfiguration(),
            'objects': objs,
        }

        return page_payload

    def getObjectByPath(self, path: str):
        """
        Given a path within this page (e.g. "button1" or
        "group1/subobj2"), find the direct child whose .id
        matches the first segment, and either return it or
        recurse into it if it’s a GUI_Object_Group.
        """
        # 1) normalize slashes
        trimmed = path.strip("/")

        # 3) split first id vs. remainder
        first_segment, remainder = split_path(trimmed)
        if not first_segment:
            return None

        # 4) search our objects (keyed by full uid, but match on obj.id)
        for full_uid, info in self.objects.items():
            obj = info.instance
            if obj.id == first_segment:
                if not remainder:
                    return obj
                # must be a group to descend further
                if isinstance(obj, Widget_Group):
                    return obj.getObjectByPath(remainder)
                return None

        return None


# ======================================================================================================================
class Folder:
    pages: dict[str, FolderPage]
    button: FolderButton
    back_button: FolderButton | None = None
    folders: dict[str, Folder]

    parent: Folder | App | None = None  # The parent folder or app, if any

    def __init__(self, folder_id, **kwargs):
        self.id = folder_id
        self.button = self._createButton(**kwargs)

        self.config = {}
        self.pages = {}
        self.folders = {}

        self.addPage(FolderPage(page_id='page1', **kwargs))

        self.logger = Logger(f"Folder {self.uid}", level="DEBUG")

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self) -> str:
        if isinstance(self.parent, Folder):
            return f"{self.parent.uid}/{self.id}"
        elif isinstance(self.parent, App):
            return f"{self.parent.uid}/folders/{self.id}"
        else:
            return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def getApp(self) -> App | None:
        if not self.parent:
            return None
        if isinstance(self.parent, App):
            return self.parent
        elif isinstance(self.parent, Folder):
            return self.parent.getApp()
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def addPage(self, page: FolderPage) -> FolderPage:
        if page.id in self.pages:
            raise ValueError(f"Page with id {page.id} already exists in folder {self.id}.")
        self.pages[page.id] = page
        page.folder = self
        page.position = len(self.pages) - 1

        message = AddMessage(
            data=AddMessageData(
                type='page',
                parent=self.uid,
                id=page.uid,
                position=page.position,
                config=page.getPayload(),
            )
        )
        self.sendMessage(message)

        return page

    # ------------------------------------------------------------------------------------------------------------------
    def removePage(self, page: FolderPage | str) -> None:
        if isinstance(page, FolderPage):
            pass
        elif isinstance(page, str):
            if not page in self.pages:
                raise ValueError(f"No page with id {page} found in folder {self.id}.")
            page = self.pages[page]
        else:
            raise TypeError(f"Expected FolderPage or str, got {type(page)}")

        message = RemoveMessage(
            data=RemoveMessageData(
                type='page',
                parent=self.uid,
                id=page.uid,
            )
        )
        self.sendMessage(message)
        page.folder = None
        page.position = None
        del self.pages[page.id]

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, message):
        app = self.getApp()
        if app is not None:
            try:
                app.broadcast(message)
            except Exception as e:
                self.logger.error(f"Failed to send message {message}. Error: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def addObject(self, obj: Widget, page: str | int | FolderPage = None, row=None, column=None, width=1, height=1,
                  **kwargs) -> Widget:
        if isinstance(page, str):
            page = self.pages.get(page)
            if page is None:
                raise ValueError(f"No page with id {page} found in folder {self.id}.")
        elif isinstance(page, int):
            if page < 0 or page >= len(self.pages):
                raise IndexError(f"Page index {page} out of range in folder {self.id}.")
            page = list(self.pages.values())[page]
        elif isinstance(page, FolderPage):
            if page.id not in self.pages:
                raise ValueError(f"Page with id {page.id} does not exist in folder {self.id}.")
        elif page is None:
            page = self.getPageByPosition(0)  # Default to the first page if no page is specified
        else:
            raise TypeError(f"Expected str or int for page, got {type(page)}")

        return page.addObject(obj, row=row, column=column, width=width, height=height, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def removeObject(self, page: str | int | FolderPage, obj: Widget | str) -> None:
        if isinstance(page, str):
            page = self.pages.get(page)
            if page is None:
                raise ValueError(f"No page with id {page} found in folder {self.id}.")
        elif isinstance(page, int):
            if page < 0 or page >= len(self.pages):
                raise IndexError(f"Page index {page} out of range in folder {self.id}.")
            page = list(self.pages.values())[page]
        elif isinstance(page, FolderPage):
            if page.id not in self.pages:
                raise ValueError(f"Page with id {page.id} does not exist in folder {self.id}.")
        else:
            raise TypeError(f"Expected str or int for page, got {type(page)}")

        page.removeObject(obj)

    # ------------------------------------------------------------------------------------------------------------------
    def addFolder(self, folder: Folder, page: str | int | FolderPage, row, column, **kwargs) -> None:
        if isinstance(page, str):
            page = self.pages.get(page)
            if page is None:
                raise ValueError(f"No page with id {page} found in folder {self.id}.")
        elif isinstance(page, int):
            if page < 0 or page >= len(self.pages):
                raise IndexError(f"Page index {page} out of range in folder {self.id}.")
            page = list(self.pages.values())[page]
        elif isinstance(page, FolderPage):
            if page.id not in self.pages:
                raise ValueError(f"Page with id {page.id} does not exist in folder {self.id}.")
        elif page is None:
            page = self.getPageByPosition(0)  # Default to the first page if no page is specified
        else:
            raise TypeError(f"Expected str or int for page, got {type(page)}")

        if not isinstance(folder, Folder):
            raise TypeError(f"Expected Folder, got {type(folder)}")

        # Check if the folder already exists in this folder
        if folder.id in self.folders:
            raise ValueError(f"Folder with id {folder.id} already exists in folder {self.id}.")

        # Add the folder to the dict
        self.folders[folder.id] = folder
        folder.parent = self

        # Send an add message to the frontend
        message = AddMessage(
            data=AddMessageData(
                type='folder',
                parent=self.uid,
                id=folder.uid,
                config=folder.getPayload(),
            )
        )
        self.sendMessage(message)

        # Add the folder button to the page
        page.addObject(folder.button, row=row, column=column)

    # ------------------------------------------------------------------------------------------------------------------
    def removeFolder(self, folder: Folder | str):
        if isinstance(folder, Folder):
            folder_id = folder.id
        elif isinstance(folder, str):
            # Check if it is a normal id
            if folder in self.folders:
                folder_id = folder
                folder = self.folders[folder_id]
            else:
                folder = self.getApp().getObjectByUID(folder)
                if folder is not None and isinstance(folder, Folder):
                    folder_id = folder.id
                    if folder_id not in self.folders:
                        self.logger.warning(f"Folder with id {folder_id} does not exist in folder {self.id}.")
                        return
                    folder = self.folders[folder_id]
                else:
                    return  # No folder found with that id
        else:
            return  # Invalid type

        # A valid folder id is found, now remove it
        if folder_id not in self.folders:
            self.logger.warning(f"Folder with id {folder_id} does not exist in folder {self.id}.")

        # Remove it from the dict
        del self.folders[folder_id]

        # Remove the button from all pages
        folder.onRemove()

        # Send a remove message to the server
        message = RemoveMessage(
            data=RemoveMessageData(
                type='folder',
                parent=self.uid,
                id=folder.uid,
            )
        )
        self.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def onRemove(self):
        self.button.parent.removeObject(self.button)

    # ------------------------------------------------------------------------------------------------------------------
    def _createButton(self, **kwargs) -> FolderButton:
        return FolderButton(button_id=f"button_{self.id}", folder=self, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'id': self.uid,
            'type': 'folder',
            **self.config,
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'config': self.getConfiguration(),
            'pages': {k: v.getPayload() for k, v in self.pages.items()},
            'folders': {k: v.getPayload() for k, v in self.folders.items()},
            'header': {},
        }

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path: str) -> Widget | FolderPage | Folder | None:
        """
        Given a relative (or even absolute) path such as
          "page1/button1/subgroup/obj2"
        or
          "myGui::category1/page1/button1",
        this will strip off any gui_id:: prefix, then
        split off the page‐ID and delegate the rest.
        """
        # 1) normalize slashes
        trimmed = path.strip("/")

        # 3) now trimmed should be “pageID[/rest]”
        first_segment, remainder = split_path(trimmed)
        if not first_segment:
            return None

        if first_segment in self.folders:
            folder = self.folders[first_segment]
            if not remainder:
                return folder
            return folder.getObjectByPath(remainder)

        elif first_segment in self.pages:
            page = self.pages[first_segment]
            if not remainder:
                return page
            return page.getObjectByPath(remainder)
        return None

    def getPageByPosition(self, position: int) -> FolderPage | None:
        """
        Returns the page at the given position.
        If the position is out of range, returns None.
        """
        if position < 0 or position >= len(self.pages):
            return None
        return list(self.pages.values())[position]


# ======================================================================================================================
class App:
    root_folder: Folder | None

    server: AioHttpWebsocketServer

    frontends: list[AioHttpWebsocketClient]

    popups: dict[str, Popup]

    allow_multiple_instances: bool = True  # Whether to allow multiple instances of the app

    _task: threading.Thread | None = None
    _exit: bool = False

    def __init__(self, app_id,
                 host,  # This is the host where the app is running, e.g., 'localhost' or an IP address
                 run_js_app: bool = False,  # Whether to run the JS app
                 run_update_task: bool = True,  # Whether to run the update task
                 update_task_interval: float = 0.1,  # Interval for the update task in seconds
                 **kwargs):

        self.id = app_id

        self.host = host
        self.ws_port = WS_PORT_MOBILE
        self.run_js_app = run_js_app
        self.js_port = PORT_JS_APP
        self.run_update_task = run_update_task
        self.update_task_interval = update_task_interval

        default_options = {
            'name': self.id,
            'icon': None,
            'logo_path': '',
            'color': [31 / 255, 32 / 255, 35 / 255, 1],
        }

        self.options = update_dict(default_options, kwargs)

        self.frontends = []
        self.popups = {}

        self.server = AioHttpWebsocketServer(host=self.host, port=self.ws_port, heartbeats=False)
        self.server.callbacks.new_client.register(self._new_client_callback)
        self.server.callbacks.client_disconnected.register(self._client_disconnected_callback)
        self.server.callbacks.message.register(self._serverMessageCallback)
        self.server.logger.switchLoggingLevel('INFO', 'DEBUG')

        self._task = threading.Thread(target=self._task_function, daemon=True)
        self.js_process = None

        self.logger = Logger(f"App {self.id}", level="DEBUG")

        self.root_folder = self._createRootFolder(**kwargs)

        self.update_message = GUI_UpdateMessage()

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):

        self.server.start()

        if self.run_js_app:
            self.runJSApp()

        if self.run_update_task:
            self._exit = False
            self._task.start()

        self.logger.info(f"App {self.id} started.")
        self.logger.info(f"Websocket server running on {self.host}:{self.ws_port}")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.server.stop()
        self._exit = True
        if self._task is not None and self._task.is_alive():
            self._task.join()

        self.logger.info(f"App {self.id} closed.")

    # ------------------------------------------------------------------------------------------------------------------
    def runJSApp(self):
        js_app_path = get_absolute_path("../")

        self.js_process = run_vite_app(js_app_path, host=self.server.host, port=self.js_port, env_vars={
            'WS_PORT': str(self.server.port),
            'WS_HOST': self.server.host,
        }, print_link=False, )
        self.logger.info(f"JS app running on http://{self.host}:{self.js_port}/app")

    # ------------------------------------------------------------------------------------------------------------------
    def _task_function(self):
        while not self._exit:
            self._sendUpdateMessage()
            time.sleep(self.update_task_interval)

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self) -> str:
        return f":{self.id}:"

    # ------------------------------------------------------------------------------------------------------------------
    def addFolder(self, folder: Folder, page: FolderPage | None = None, row=None, column=None, **kwargs) -> None:
        """
        Adds a folder to the root folder of the app
        Args:
            column:
            row:
            page:
            folder:

        Returns:

        """
        if not isinstance(folder, Folder):
            raise TypeError(f"Expected Folder, got {type(folder)}")

        self.root_folder.addFolder(folder, page=page, row=row, column=column, **kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def removeFolder(self, folder: Folder | str) -> None:
        self.root_folder.removeFolder(folder)

    # ------------------------------------------------------------------------------------------------------------------
    def sendUpdate(self, uid: str, message: UpdateMessage):

        # Check if this object already has a message in the update message
        if uid in self.update_message.messages:
            # If it does, update the existing message
            if message.important:
                if not isinstance(self.update_message.messages[uid], list):
                    # If the existing message is not a list, convert it to a list
                    self.update_message.messages[uid] = [self.update_message.messages[uid]]
                # Append the new message to the list
                self.update_message.messages[uid].append(message)
            else:
                self.update_message.messages[uid] = message

        else:
            # If it does not, add it to the update message
            self.update_message.messages[uid] = message

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message, client=None):
        if client is None:
            self.broadcast(message)
            return None

        if client in self.frontends:
            if dataclasses.is_dataclass(message):
                message = asdict_optimized(message)
            self.server.sendToClient(client, message)
            return None
        else:
            raise NotImplementedError("Client seems to be a parent. I need to implement this")

    # ------------------------------------------------------------------------------------------------------------------
    def broadcast(self, message):
        self.sendToAllFrontends(message)
        self.sendToParents(message)

    # ------------------------------------------------------------------------------------------------------------------
    def sendToAllFrontends(self, message):

        if dataclasses.is_dataclass(message):
            message = asdict_optimized(message)

        for frontend in self.frontends:
            self.server.sendToClient(frontend, message)

    # ------------------------------------------------------------------------------------------------------------------
    def sendToParents(self, message):

        return

        if dataclasses.is_dataclass(message):
            message = asdict_optimized(message)

        for parent in self.parent_guis.values():
            parent.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _createRootFolder(self, **kwargs) -> Folder:
        root_folder = Folder(folder_id='root', **kwargs)
        root_folder.parent = self

        return root_folder

    # ------------------------------------------------------------------------------------------------------------------
    def print(self, text, color='white'):
        self.function(function_name='print',
                      args=[text, color],
                      spread_args=True)

    # ------------------------------------------------------------------------------------------------------------------
    def function(self, function_name, args, spread_args=True, client=None):

        data = FunctionMessage(
            function_name=function_name,
            args=args,
            spread_args=spread_args,
        )

        message = ObjectMessage(
            id=self.uid,
            data=data,  # type: ignore
        )

        self.send(message, client=client)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {

        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'type': 'app',
            'name': self.name if hasattr(self, 'name') else self.id,
            'options': self.options,
            'popups': {},
            'folder': self.root_folder.getPayload() if self.root_folder else None,
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def _new_client_callback(self, client):
        self.logger.debug(f"New client connected: {client}")

    # ------------------------------------------------------------------------------------------------------------------
    def _client_disconnected_callback(self, client: AioHttpWebsocketClient):
        self.logger.debug(f"Client disconnected: {client.address}:{client.port}")

        if client in self.frontends:
            self.frontends.remove(client)
            self.logger.info(f"Frontend disconnected: {client.address}:{client.port} ({len(self.frontends)})")
        # elif client in self.child_guis:
        #     self.logger.warning(f"TODO: Child GUI disconnected: {client.address}:{client.port}")

    # ------------------------------------------------------------------------------------------------------------------
    def _serverMessageCallback(self, client, message, *args, **kwargs):

        match message['type']:
            case 'handshake':
                self._handleHandshakeMessage(client, message)
            case 'event':
                self._handleEventMessage(message, sender=client)
            case 'request':
                # These are handled by the parent objects, so no need to do something here
                pass
            case _:
                self.logger.warning(f"Unknown message type: {message['type']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleHandshakeMessage(self, client: AioHttpWebsocketClient, message):
        self.logger.debug(f"Received handshake message from {client}: {message}")

        data = message.get('data')
        if data is None:
            self.logger.warning(f"Handshake message from {client} did not contain data")
            return

        match data['client_type']:
            case 'app_frontend':
                self._handleFrontendHandshake(client, data)
            case 'child_gui':
                self.logger.info(f"New child GUI connected: {client.address}:{client.port}")
                raise NotImplementedError(
                    f"Child GUI handling not implemented yet for {client.address}:{client.port}")
            case 'parent_gui':
                self.logger.info(f"New parent GUI connected: {client.address}:{client.port}")
                raise NotImplementedError(
                    f"Parent GUI handling not implemented yet for {client.address}:{client.port}")
                self._initializeParent(client)
            case _:
                self.logger.warning(f"Unknown client type: {data['client_type']}")
                return

    # ------------------------------------------------------------------------------------------------------------------
    def _handleEventMessage(self, message, sender: AioHttpWebsocketClient = None):
        # 1) must have an id for use with other objects
        msg_id = message.get('id')

        if not msg_id or msg_id == self.uid:
            self._handleGuiEvent(message, sender=sender)
            return

        # Check if the message is meant for a child GUI
        child, child_obj_id = self._checkPathForChildGUI(msg_id)

        if child is not None:
            # child GUI matched → forward the event to the child

            # rebuild the event for the child
            child_event = {
                'type': 'event',
                'event': message.get('event'),
                'id': child_obj_id,
                'data': message.get('data'),
            }

            self.logger.debug(
                f"Forwarding event to child GUI {child.address}:{child.port}: {child_event}"
            )
            child.send(child_event)
            return

        # 3) no child matched → handle locally
        element = self.getObjectByUID(msg_id)
        if element is None:
            self.logger.warning(f"Event for unknown element {msg_id}: {message}")
            return

        element.onEvent(message.get('data'), sender=sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleFrontendHandshake(self, client: AioHttpWebsocketClient, data):
        address = client.address
        #
        # # Check if the frontend address is already in use
        if any(f.address == address for f in self.frontends):
            if not self.allow_multiple_instances:
                self.logger.warning(f"Frontend {address} already connected. Asking user how to proceed.")
                choose_msg = {'type': 'choose', 'data': {}}
                self.server.sendToClient(client, choose_msg)
                # self._closeFrontend(client)
                return

        self._connectFrontend(client)

    # ------------------------------------------------------------------------------------------------------------------
    def _connectFrontend(self, client: AioHttpWebsocketClient):
        self.frontends.append(client)
        self._initializeFrontend(client)
        self.logger.info(f"New frontend connected: {client.address}:{client.port} ({len(self.frontends)})")

    # ------------------------------------------------------------------------------------------------------------------
    def _initializeFrontend(self, frontend):
        # Send Initialize Message
        message = InitMessage(
            configuration=self.getPayload(),
        )
        self.server.sendToClient(frontend, asdict_optimized(message))
        #
        # # Check if there are open popups and send them
        # for popup in self.popups.values():
        #     popup_message = AddMessage(
        #         data=AddMessageData(
        #             type='popup',
        #             parent=self.uid,
        #             id=popup.uid,
        #             config=popup.getPayload(),
        #         )
        #     )
        #     self.server.sendToClient(frontend, asdict_optimized(popup_message))

    def getObjectByUID(self, uid: str):
        """
        Given a full UID, e.g.
           "myGui::category1/page1/button1"
        or even
           "/myGui::category1/page1/button1",
        this will strip slashes and the gui_id:: prefix,
        then split off the category id and delegate to
        that category’s getObjectByPath.
        """
        if not uid:
            return None

        # 1) drop any leading slash
        trimmed = uid.lstrip("/")

        # 2) Split off the GUI ID
        gui_id, remainder = split_path(trimmed)
        if not gui_id or gui_id != self.uid:
            self.logger.warning(f"UID '{uid}' does not match this GUI's ID '{self.uid}'")
            return None

        # If the remainder is empty, we are looking for the GUI itself
        if not remainder:
            return self

        # 4) Split off the first ID. This should be the type of object we are looking for
        object_type, remainder = split_path(remainder)

        if object_type not in ('folders', 'popups', 'callouts'):
            self.logger.warning(f"UID '{uid}' does not start with a valid object type (categories/popups/callouts)")
            return None

        # 5) Switch based on the object type
        match object_type:
            case 'folders':
                folder_id, remainder = split_path(remainder)
                if not folder_id:
                    self.logger.warning(f"UID '{uid}' does not contain a valid category ID")
                    return None

                # Check if the folder_id is the one of the root folder
                if folder_id != self.root_folder.id:
                    self.logger.warning(
                        f"Folder ID '{folder_id}' does not match the root folder ID '{self.root_folder.id}'")
                    return

                if not remainder:
                    return self.root_folder

                # If there is a remainder, delegate to the category's getObjectByPath
                return self.root_folder.getObjectByPath(remainder)

            case 'popups':
                raise NotImplementedError("Popups are not yet implemented in getObjectByUID")
                popup_id, remainder = split_path(remainder)
                if not popup_id:
                    self.logger.warning(f"UID '{uid}' does not contain a valid popup ID")
                    return None
                # Check if the popup ID is a valid popup
                if popup_id not in self.popups:
                    self.logger.warning(f"Popup ID '{popup_id}' not found in GUI '{self.id}'")
                    return None
                popup = self.popups[popup_id]

                if not remainder:
                    return popup

                # If there is a remainder, delegate to the popup's getObjectByPath
                return popup.getObjectByPath(remainder)

            case 'callouts':
                raise NotImplementedError("Callouts are not yet implemented in getObjectByUID")
                callout_id, remainder = split_path(remainder)
                if not callout_id:
                    self.logger.warning(f"UID '{uid}' does not contain a valid callout ID")
                    return None
                # Check if the callout ID is a valid callout
                if callout_id not in self.callout_handler.callouts:
                    self.logger.warning(f"Callout ID '{callout_id}' not found in GUI '{self.id}'")
                    return None
                callout = self.callout_handler.callouts[callout_id]

                return callout
        return None

    # -------------------------------------------------------------------------------------------------------------------
    def _checkPathForChildGUI(self, path):
        return None, None  # Placeholder for child GUI handling logic

    # ------------------------------------------------------------------------------------------------------------------
    def _sendUpdateMessage(self):
        # Check if there are any messages to send
        if not self.update_message.messages or len(self.update_message.messages) == 0:
            return

        message = asdict_optimized(self.update_message)
        self.broadcast(message)
        # Prepare a new empty message
        self.update_message = GUI_UpdateMessage()


# ======================================================================================================================
def main():  # Example usage
    host = getHostIP()
    app = App(app_id='my_app', host=host, run_js_app=True)
    folder_buttons = Folder(folder_id='buttons', rows=3)
    folder_sliders = Folder(folder_id='sliders')
    folder_plots = Folder(folder_id='plots', rows=6, gap=1)
    folder_groups = Folder(folder_id='groups', rows=4)
    folder_pages = Folder(folder_id='pages')
    folder_checkboxes = Folder(folder_id='checkbox', rows=5, fill_empty_cells=False)

    app.addFolder(folder_buttons)
    app.addFolder(folder_sliders)
    app.addFolder(folder_plots)
    app.addFolder(folder_groups)
    app.addFolder(folder_pages)
    app.addFolder(folder_checkboxes)

    # ----------------------------------------------------------------------
    # BUTTONS
    button1 = Button(widget_id='button1', text='Single Click')
    folder_buttons.addObject(button1, row=1, column=1, width=1, height=1)
    button1.callbacks.click.register(
        lambda *args, **kwargs: button1.accept())

    button2 = Button(widget_id='button2', text='Long Click')
    folder_buttons.addObject(button2, row=1, column=2, width=1, height=1)
    button2.callbacks.longClick.register(lambda *args, **kwargs: button2.accept())

    button3 = Button(widget_id='button3', text='Double Click')
    folder_buttons.addObject(button3, row=1, column=3, width=1, height=1)
    button3.callbacks.doubleClick.register(lambda *args, **kwargs: button3.accept())
    button3.callbacks.click.register(lambda *args, **kwargs: button3.accept(False))

    # ----------------------------------------------------------------------
    # Sliders
    slider1 = SliderWidget(widget_id='slider1', min_value=0, max_value=100, value=50, increment=5, color=[1, 0, 0, 0.7],
                           disabled=False)
    folder_sliders.addObject(slider1, row=1, column=1, width=3, height=1)

    # ----------------------------------------------------------------------
    # Checkboxes
    checkbox_1 = CheckboxWidget(widget_id='checkbox_1', value=False, title='Checkbox', border_width=0)
    folder_checkboxes.addObject(checkbox_1, row=1, column=1, width=2, height=1)
    # ----------------------------------------------------------------------
    # PAGES
    folder_pages.addPage(FolderPage(page_id='page2', title='Page 2', rows=5, columns=10))
    folder_pages.addPage(FolderPage(page_id='page3', title='Page 3', columns=3, rows=1))
    folder_pages.addPage(FolderPage(page_id='page4', title='Page 4', columns=1, rows=1))
    # ----------------------------------------------------------------------
    # GROUPS
    group1 = Widget_Group(group_id='group1',
                          border_width=1,
                          border_color=random_color_from_palette('pastel'),
                          rows=30,
                          fit=False,
                          show_scrollbar=True,
                          )

    folder_groups.addObject(group1, width=3, height=4, row=1)
    group_button_1 = Button(widget_id='group_button_1', text='GP 1',
                            config={'color': random_color_from_palette('dark')})
    group1.addWidget(group_button_1, width=2, height=2, row=1, column=1)
    group_checkbox = CheckboxWidget(widget_id='group_checkbox', value=False, title='Checkbox')
    group1.addWidget(group_checkbox, width=5, height=1, row=4, column=1)
    # ----------------------------------------------------------------------
    # PLOTS
    plot_widget_1 = PlotWidget(widget_id='plot_widget_1', title='Plot 1',
                               server_mode=ServerMode.EXTERNAL,
                               update_mode=UpdateMode.CONTINUOUS)

    # Create dataseries
    dataseries_1 = JSPlotTimeSeries(timeseries_id='ds1',
                                    name='Data 1',
                                    unit='V',
                                    min=-10,
                                    max=10,
                                    color=random_color_from_palette('pastel'), )
    dataseries_1.setValue(1)
    plot_widget_1.plot.addTimeseries(dataseries_1)
    folder_plots.addObject(plot_widget_1, width=2, height=5)
    # ----------------------------------------------------------------------

    app.start()

    while True:
        # dataseries_1.setValue(random.randint(-9,9))
        time.sleep(0.1)

    # folder2 = Folder(folder_id='folder2')
    #
    # app.addFolder(folder1)
    #
    # page1 = folder1.getPageByPosition(0)
    # page1.config['rows'] = 3
    # page2 = folder1.addPage(FolderPage(page_id='page2'))
    # page3 = folder1.addPage(FolderPage(page_id='page3'))
    #
    # folder1.addObject(SliderWidget(widget_id='slider1',
    #                                title='Slider 1',
    #                                min_value=0,
    #                                max_value=100,
    #                                value=50,
    #                                increment=1), row=1, column=1,
    #                   width=3)
    #
    # folder1.addFolder(folder2, page='page1', row=2, column=1)
    #
    # app.root_folder.addObject(page=0, obj=SliderWidget(widget_id='slider2',
    #                                                    title='Slider 2',
    #                                                    min_value=0,
    #                                                    max_value=100,
    #                                                    value=75,
    #                                                    increment=5,
    #                                                    direction='vertical',
    #                                                    continuousUpdates=True,
    #                                                    ),
    #                           width=1,
    #                           height=2
    #                           )
    #
    # # Add button to root folder
    # button1: Button = app.root_folder.addObject(page=0, obj=Button(id='button1', text='Click Me', color=[0.4, 0, 0, 1]),
    #                                             row=2, column=3).obj
    #
    # def button1_callback(*args, **kwargs):
    #     button1.updateConfig(color=random_color_from_palette('dark'))
    #
    # button1.callbacks.click.register(button1_callback)
    #
    # plot_widget_1 = PlotWidget(widget_id='plot_widget_1', title='Plot 1',
    #                            server_mode=ServerMode.EXTERNAL,
    #                            update_mode=UpdateMode.CONTINUOUS)
    #
    # # Create dataseries
    # dataseries_1 = JSPlotTimeSeries(timeseries_id='ds1',
    #                                 name='Data 1',
    #                                 unit='V',
    #                                 min=-10,
    #                                 max=10,
    #                                 color=random_color_from_palette('pastel'), )
    # dataseries_1.setValue(1)
    # plot_widget_1.plot.addTimeseries(dataseries_1)
    # page1.addObject(plot_widget_1, width=2, height=2)
    #
    # app.start()
    #
    # folder1.removeFolder(folder2)
    # print("Removed folder2 from folder1")
    # while True:
    #     dataseries_1.setValue(random.random() * 10 - 5)
    #     time.sleep(0.1)


if __name__ == '__main__':
    main()
