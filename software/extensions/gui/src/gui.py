from __future__ import annotations

import base64
import copy
import dataclasses
import os
import tempfile
import threading
import time
import uuid
from dataclasses import is_dataclass

# === CUSTOM IMPORTS ===================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.colors import rgb_to_hex
from core.utils.dict_utils import update_dict
from core.utils.events import Event, EventFlag, pred_flag_equals, TIMEOUT
from core.utils.exit import register_exit_callback
from core.utils.files import get_absolute_path
from core.utils.js.vite import run_vite_app
from core.utils.logging_utils import Logger
from core.utils.dataclass_utils import asdict_optimized, from_dict_auto
from core.utils.time import delayed_execution
from core.utils.websockets import WebsocketServer, WebsocketClient, WebsocketServerClient
from extensions.gui.settings import WS_PORT_DESKTOP, PORT_JS_APP, WS_PORT_MOBILE
from extensions.gui.src.lib.cli_terminal.cli_terminal import CLI_Terminal
from extensions.gui.src.lib.messages import RemoveMessage, RemoveMessageData, AddMessage, AddMessageData, \
    HandshakeMessage, RequestMessage, RequestMessageData, ResponseMessage
from extensions.gui.src.lib.objects.objects import Widget_Group, Widget, UpdateMessage, \
    FunctionMessage, ObjectMessage
from extensions.gui.src.lib.objects.python.callout import CalloutHandler
from extensions.gui.src.lib.objects.python.indicators import BatteryIndicatorWidget, NetworkIndicator, \
    JoystickIndicator, ConnectionIndicator
from extensions.gui.src.lib.objects.python.popup import Popup, PopupInstance
from extensions.gui.src.lib.utilities import check_for_spaces, split_path, addIdPrefix, check_id


@dataclasses.dataclass
class InitMessage:
    configuration: GUI_Payload | dict
    type: str = 'init'


@dataclasses.dataclass
class GUI_UpdateMessage:
    messages: dict[str, UpdateMessage | list[UpdateMessage]] = dataclasses.field(default_factory=dict)
    type: str = 'gui_update'


# === CATEGORY =========================================================================================================
class CategoryHeadbar(Widget_Group):

    def __init__(self, group_id, category, **kwargs):
        super(CategoryHeadbar, self).__init__(group_id, **kwargs)

        default_config = {
            'rows': 1,
            'columns': 20,
        }

        self.config = update_dict(self.config, default_config, kwargs)
        self.category = category
        self.parent = self.category


# ----------------------------------------------------------------------------------------------------------------------
@callback_definition
class Category_Callbacks:
    update: CallbackContainer
    add: CallbackContainer
    remove: CallbackContainer


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class Category_Configuration:
    id: str
    type: str = 'category'
    name: str = None
    color: str | None = None
    max_pages: int = 10
    collapsed: bool = False
    icon: str = '📁'  # Default icon for the category


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class Category_Payload:
    id: str
    config: Category_Configuration
    headbar: dict
    pages: dict[str, PagePayload]
    categories: dict[str, Category_Payload]
    bottom_group: dict | None = None
    type: str = 'category'


# ----------------------------------------------------------------------------------------------------------------------
class Category:
    id: str
    pages: dict[str, Page]
    categories: dict[str, Category]

    name: str
    icon: str
    headbar: CategoryHeadbar

    configuration: dict

    parent: GUI | Category | None

    # === INIT =========================================================================================================
    def __init__(self, id: str, name: str = None, **kwargs):

        check_id(id, allowed_special_characters=[':'])

        default_config = {
            'color': None,
            'max_pages': 10,
            'collapsed': False,
            'icon': '📁',
        }

        self.configuration = {**default_config, **kwargs}
        self.id = id

        self.name = name if name is not None else id

        self.pages = {}
        self.categories = {}

        self.parent = None

        self.callbacks = Category_Callbacks()
        self.headbar = CategoryHeadbar('headbar', self, **kwargs)
        self.headbar.parent = self

        # Optional per-category bottom group
        bottom_group_size = self.configuration.pop('bottom_group_size', None)
        if bottom_group_size:
            self.bottom_group = Widget_Group(
                'bottom_group', rows=bottom_group_size[0], columns=bottom_group_size[1],
                border=False, border_width=0, title='')
            self.bottom_group.parent = self
        else:
            self.bottom_group = None

        self.logger = Logger(f"Category {self.id}", 'DEBUG')

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if isinstance(self.parent, GUI):
            return f"{self.parent.id}/categories/{self.id}"
        elif isinstance(self.parent, Category):
            return f"{self.parent.uid}/{self.id}"
        else:
            return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        if isinstance(self.parent, GUI):
            return self.parent
        elif isinstance(self.parent, Category):
            return self.parent.getGUI()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path: str):
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

        if first_segment == 'headbar':
            if not remainder:
                return self.headbar
            return self.headbar.getObjectByPath(remainder)

        if first_segment == 'bottom_group':
            if self.bottom_group is None:
                return None
            if not remainder:
                return self.bottom_group
            return self.bottom_group.getObjectByPath(remainder)

        if first_segment in self.pages:
            page = self.pages[first_segment]
            if not remainder:
                return page
            return page.getObjectByPath(remainder)

        elif first_segment in self.categories:
            category = self.categories[first_segment]
            if not remainder:
                return category
            return category.getObjectByPath(remainder)
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByUID(self, uid):
        gui = self.getGUI()

        if gui is not None:
            return gui.getObjectByUID(uid)
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def addPage(self, page: Page, position=None):

        # Fist check if the position is valid if given
        if position is not None and position > self.configuration['max_pages']:
            raise ValueError(f"Position {position} is out of range")

        if page.uid in self.pages:
            raise ValueError(f"Page with id {page.id} already exists")
        self.pages[page.id] = page
        page.category = self
        page.position = position

        message = AddMessage(
            data=AddMessageData(
                type='page',
                parent=self.uid,
                id=page.uid,
                position=position,
                config=page.getPayload(),
            )
        )

        self.sendMessage(message)
        return page

    # ------------------------------------------------------------------------------------------------------------------
    def removePage(self, page: Page):
        if page.id not in self.pages:
            raise ValueError(f"Page with id {page.id} does not exist")
        del self.pages[page.id]

        message = RemoveMessage(
            data=RemoveMessageData(
                type='page',
                parent=self.uid,
                id=page.uid,
            )
        )
        self.sendMessage(message)
        page.onDelete()

    # ------------------------------------------------------------------------------------------------------------------
    def addCategory(self, category: Category):
        if category.id in self.categories:
            raise ValueError(f"Category with id {category.id} already exists")
        category.parent = self
        self.categories[category.id] = category

        message = AddMessage(
            data=AddMessageData(
                type='category',
                parent=self.uid,
                id=category.uid,
                config=category.getPayload(),
            )
        )
        self.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def removeCategory(self, category: Category):
        if category.id not in self.categories:
            raise ValueError(f"Category with id {category.id} does not exist")
        del self.categories[category.id]

        message = RemoveMessage(
            data=RemoveMessageData(
                type='category',
                parent=self.uid,
                id=category.uid,
            )
        )
        self.sendMessage(message)
        category.onDelete()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        message = {
            'type': 'update',
            'id': self.uid,
            'data': self.getPayload()
        }
        self.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> Category_Configuration:

        configuration = Category_Configuration(
            id=self.uid,
            name=self.name,
            icon=self.configuration.get('icon', '📁'),
            color=rgb_to_hex(self.configuration.get('color', [60, 60, 60, 1])),
            max_pages=self.configuration.get('max_pages', 10),
            collapsed=self.configuration.get('collapsed', False),
        )
        return configuration

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> Category_Payload:

        payload = Category_Payload(
            id=self.uid,
            config=self.getConfiguration(),
            headbar=self.headbar.getPayload(),
            pages={k: v.getPayload() for k, v in self.pages.items()},
            categories={k: v.getPayload() for k, v in self.categories.items()},
            bottom_group=self.bottom_group.getPayload() if self.bottom_group else None,
        )
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def onMessage(self, message, sender=None):
        self.logger.debug(f"Received message: {message}")
        object_path = message['id']

    # ------------------------------------------------------------------------------------------------------------------
    def onDelete(self):
        """Clean up all pages and subcategories when this category is deleted."""
        # Clean up all pages
        for page in self.pages.values():
            page.onDelete()
        # Clean up all subcategories
        for category in self.categories.values():
            category.onDelete()

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, message):
        gui = self.getGUI()
        if gui is not None:
            try:
                gui.broadcast(message)
            except Exception as e:
                self.logger.error(f"Error sending message: {e}")


# === PAGE =============================================================================================================
@dataclasses.dataclass
class PageObjectData:
    row: int
    column: int
    width: int
    height: int
    config: dict


@dataclasses.dataclass
class PageConfiguration:
    id: str
    name: str
    icon: str


@dataclasses.dataclass
class PagePayload:
    id: str
    position: int | None
    config: PageConfiguration
    objects: dict
    type: str = 'page'


@callback_definition
class Page_Callbacks:
    update: CallbackContainer
    add: CallbackContainer
    remove: CallbackContainer


# ----------------------------------------------------------------------------------------------------------------------
class Page:
    """
    Represents a page in the Control GUI that holds GUI_Object instances
    in a fixed grid layout. Tracks occupied cells and supports manual
    or automatic placement of objects.
    """
    id: str
    objects: dict[str, Widget]
    category: Category | None
    config: dict

    name: str
    icon: str
    position: int | None = None

    def __init__(self, id: str,
                 icon: str = None,
                 name: str = None,
                 **kwargs):

        check_id(id)

        default_config = {
            'color': None,
            'pageColor': [60, 60, 60, 1],
            'grid_size': (18, 50),  # (rows, columns)
            'text_color': [1, 1, 1]
        }

        self.config = {**default_config, **kwargs}

        self.id = f"{id}"
        self.icon = icon
        self.name = name if name is not None else id

        # Grid dimensions
        self._rows, self._cols = self.config['grid_size']
        # Occupancy grid: False = free, True = occupied
        self._occupied = [[False for _ in range(self._cols)] for _ in range(self._rows)]

        self.objects = {}
        self.category = None
        self.callbacks = Page_Callbacks()
        self.logger = Logger(f"Page {self.id}", 'DEBUG')

    @property
    def uid(self):
        category_id = self.category.uid if self.category is not None else ''
        return f"{category_id}/{self.id}"

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        for obj in list(self.objects.values()):
            self.removeWidget(obj)

        self._occupied = [[False for _ in range(self._cols)] for _ in range(self._rows)]
    # ------------------------------------------------------------------------------------------------------------------
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
        for full_uid, instance in self.objects.items():
            if instance.id == first_segment:
                if not remainder:
                    return instance
                # must be a group to descend further
                if hasattr(instance, 'getObjectByPath'):
                    return instance.getObjectByPath(remainder)
                return None

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByUID(self, uid):
        gui = self.getGUI()

        if gui is not None:
            return gui.getObjectByUID(uid)
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):

        message = {
            'type': 'update',
            'id': self.uid,
            'data': self.getPayload()
        }

        self.sendMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def addWidget(self, widget: Widget, row=None, column=None, width=2, height=2, **kwargs) -> Widget:
        """
        Adds an object to the page at a given grid position.
        If the row or column is None, we automatically find the first available
        position for the object's size.
        """

        if widget.id in self.objects:
            raise ValueError(f"Object with id {widget.id} already exists on page {self.id}")

        # Determine placement
        if row is None or column is None:
            row, column = self._placeObject(row, column, width, height)
        else:
            self._checkSpace(row, column, width, height)

        # Mark cells occupied
        self._markSpace(row, column, width, height)

        widget.parent_config = {
            'row': row,
            'column': column,
            'width': width,
            'height': height,
        }
        self.objects[widget.id] = widget

        widget.parent = self

        message = AddMessage(
            data=AddMessageData(
                type='object',
                parent=self.uid,
                id=widget.uid,
                config={
                    'row': row,
                    'column': column,
                    'width': width,
                    'height': height,
                    **widget.getPayload(),
                })
        )

        self.sendMessage(message)

        return widget

    # ------------------------------------------------------------------------------------------------------------------
    def removeWidget(self, widget: Widget):
        if widget.id not in self.objects:
            raise ValueError(f"Object with id {widget.id} does not exist on page {self.id}")

        message = RemoveMessage(
            data=RemoveMessageData(
                type='object',
                parent=self.uid,
                id=widget.uid,
            )
        )

        self.sendMessage(message)
        # Free the cells before we drop the reference
        cfg = widget.parent_config  # row/column/width/height are stored here
        self._unmarkSpace(cfg['row'], cfg['column'], cfg['width'], cfg['height'])

        widget.parent = None
        widget.onDelete()
        if widget.id in self.objects:
            del self.objects[widget.id]

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        if self.category is not None:
            return self.category.getGUI()
        return None

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
    def _unmarkSpace(self, row, column, width, height):
        # Free the grid cells (note: row/column are 1-based)
        for r in range(row - 1, row - 1 + height):
            for c in range(column - 1, column - 1 + width):
                self._occupied[r][c] = False

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
    def getConfiguration(self) -> PageConfiguration:
        config = PageConfiguration(
            id=self.uid,
            name=self.name,
            icon=self.icon
        )
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> PagePayload:
        # Build payload for each object
        objs = {}
        for uid, instance in self.objects.items():
            payload = instance.getPayload()
            payload.update({
                'row': instance.parent_config['row'],
                'column': instance.parent_config['column'],
                'width': instance.parent_config['width'],
                'height': instance.parent_config['height'],
            })
            objs[uid] = payload

        payload = PagePayload(
            id=self.uid,
            position=self.position,
            config=self.getConfiguration(),
            objects=objs,
        )

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def onMessage(self, message, sender=None):
        self.logger.debug(f"Received message: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def onDelete(self):
        """Clean up all widgets when this page is deleted."""
        for widget in self.objects.values():
            widget.onDelete()

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, message):
        gui = self.getGUI()
        if gui is not None:
            try:
                gui.broadcast(message)
            except Exception as e:
                self.logger.error(f"Error sending message: {e}")


# === CHILD GUI ========================================================================================================


class Child_Category(Category):
    child: Child

    def __init__(self, id, name, child, **kwargs):
        super(Child_Category, self).__init__(id, name, **kwargs)
        self.child = child

    def getPayload(self):
        # ask the child GUI for its full GUI payload (includes export + categories)
        gui_payload = self.child.requestPayloadForCategory(self.id)
        if gui_payload is None:
            self.child.gui.logger.warning(
                f"Could not get payload for GUI {self.child.id}"
            )
            return super().getPayload()

        # extract export subtree (should be a dict)
        export_payload = gui_payload.get('export', {})
        # extract all its other categories
        gui_categories = gui_payload.get('categories', {})

        # deepcopy so we don’t mutate the child’s own data
        export_copy = copy.deepcopy(export_payload)
        # merge in the child's categories under the export node
        export_copy.setdefault('categories', {}).update(copy.deepcopy(gui_categories))
        return export_copy


@callback_definition
class Child_Callbacks:
    connect: CallbackContainer
    disconnect: CallbackContainer
    message: CallbackContainer


class Child:
    gui: GUI
    category: Child_Category | None

    id: str
    name: str | None
    path_in_gui: str
    request_event: Event

    child_object_id: str | None

    def __init__(self,
                 address,
                 port,
                 parent_object_uid,
                 name: str = None,
                 client: WebsocketClient = None,
                 gui: GUI = None,
                 child_object_id=None,
                 ):

        self.address = address
        self.port = port
        self.name = name

        self.client = client
        self.gui = gui

        self.callbacks = Child_Callbacks()

        self.client.events.message.on(self._onMessage)
        self.client.callbacks.connected.register(self._onConnect)
        self.client.callbacks.disconnected.register(self._onDisconnect)

        self.client.connect()

        self.category = None
        self.path_in_gui = parent_object_uid

        # self.request_event = Event(flags=[("request_id", str)])
        self.request_event = Event(flags=EventFlag('request_id', str))

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message):
        if is_dataclass(message):
            message = asdict_optimized(message)

        self.client.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _onConnect(self, *args, **kwargs):

        self.callbacks.connect.call()

        message = HandshakeMessage(
            data={
                'client_type': 'parent_gui',
            }
        )

        self.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _onDisconnect(self, *args, **kwargs):
        self.gui.logger.warning(f"Child GUI {self.address}:{self.port} disconnected!")

        # Remove the category
        if self.category is not None:
            self.gui.logger.debug(f"Removing category {self.category.uid} from GUI {self.gui.uid}")
            parent = self.gui.getObjectByUID(self.path_in_gui)
            parent.removeCategory(self.category)

        self.callbacks.disconnect.call()

    # ------------------------------------------------------------------------------------------------------------------
    def requestPayloadForCategory(self, category_id):
        # 1) clear any previous answer

        # 2) send the request to the child GUI
        request_id = str(uuid.uuid4())

        message = RequestMessage(
            request_id=request_id,
            data=RequestMessageData(
                type='category_payload',
                id=category_id,
            )
        )

        self.send(message)

        # 3) wait for the answer
        success = self.request_event.wait(predicate=pred_flag_equals('request_id', request_id), timeout=5)
        if not success:
            self.gui.logger.warning(
                f"Timeout waiting for payload for category {category_id} from child GUI {self.id}"
            )
            return None

        payload = self.request_event.get_data()

        # 4) now recursively prefix every 'id' (and matching config['id']) in the payload
        prefix = self.path_in_gui.rstrip('/') + '/'

        addIdPrefix(payload, prefix, ['id', 'parent'])

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def _onMessage(self, message):
        self.callbacks.message.call(message)
        match message['type']:
            case 'init':
                self._handleInit(message)
            case 'response':
                self._handleAnswer(message)
            case 'update':
                self._handleUpdate(message)
            case 'widget_message':
                self._handleWidgetMessage(message)
            case 'add':
                self._handleAdd(message)
            case 'remove':
                self._handleRemove(message)
            case 'gui_update':
                self._handleGuiUpdate(message)
            case _:
                self.gui.logger.warning(f"Unhandled message from child GUI {self.id}: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleInit(self, message):

        # Extract the data from the message
        config = message.get('configuration')

        if not config:
            self.gui.logger.warning(f"Init message from child GUI {self.address}:{self.port} has no data")
            return

        # Get the GUIs ID:
        self.id = config.get('id')
        if not self.id:
            self.gui.logger.warning(f"Init message from child GUI {self.address}:{self.port} has no id")
            return

        # If the name is currently unset, use the ID:
        if self.name is None:
            self.name = self.id

        # Now let's add a category for the child
        self.category = Child_Category(id=self.id,
                                       name=self.name,
                                       child=self,
                                       icon='🌐')

        # Get the intended parent category
        parent_object = self.gui.getObjectByUID(self.path_in_gui)

        if parent_object is None:
            self.gui.logger.warning(
                f"Could not find parent category for child GUI {self.id} with path {self.path_in_gui}")
            return

        # Check if the parent is either a category or the gui itself
        if not isinstance(parent_object, Category) and not isinstance(parent_object, GUI):
            self.gui.logger.warning(f"Parent object for child GUI {self.id} is not a category or the gui itself")
            return

        # Add the child to the parent
        parent_object.addCategory(self.category)
        self.callbacks.connect.call()

    # ------------------------------------------------------------------------------------------------------------------
    def _handleAnswer(self, message):
        self.request_event.set(data=message['data'], flags={'request_id': message['request_id']})

    # ------------------------------------------------------------------------------------------------------------------
    def _handleUpdate(self, message):
        message['id'] = self.path_in_gui + '/' + message['id']
        message['data']['id'] = self.path_in_gui + '/' + message['data']['id']

        self.gui.broadcast(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleGuiUpdate(self, message):
        """
        Handle a GUI update message from the child GUI.
        This message contains updates for multiple objects in the GUI.
        """
        self.gui.logger.debug(f"Handling GUI update message from child GUI {self.id}: {message}")
        # loop through the messages
        for obj_id, updates in message['messages'].items():
            obj_id_adjusted = self.path_in_gui + '/' + obj_id
            if isinstance(updates, list):
                # If the updates are a list, loop through them
                for update in updates:
                    self.gui.sendUpdate(uid=obj_id_adjusted, message=update)
            else:
                self.gui.sendUpdate(uid=obj_id_adjusted, message=updates)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleWidgetMessage(self, message):
        # Forward the message to the parent GUI
        message['id'] = self.path_in_gui + '/' + message['id']
        self.gui.broadcast(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleAdd(self, message):
        self.gui.logger.important(f"Handling add message from child GUI {self.id}: {message}")

        addIdPrefix(node=message,
                    prefix=self.path_in_gui.rstrip('/') + '/',
                    field_names=['id', 'parent'])

        self.gui.logger.debug(f"Broadcasting add message: {message}")
        self.gui.broadcast(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleRemove(self, message):
        addIdPrefix(node=message,
                    prefix=self.path_in_gui.rstrip('/') + '/',
                    field_names=['id', 'parent'])
        self.gui.broadcast(message)


# === PARENT ===========================================================================================================
@callback_definition
class Parent_Callbacks:
    disconnect: CallbackContainer
    message: CallbackContainer


class Parent:

    def __init__(self, id, gui, client: WebsocketServerClient):
        self.id = id
        self.gui = gui
        self.client = client
        self.callbacks = Parent_Callbacks()

        self.client.callbacks.disconnected.register(self._onDisconnect)
        self.client.callbacks.message.register(self._onMessage)

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, message):
        if is_dataclass(message):
            message = asdict_optimized(message)

        self.client.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _onMessage(self, message):

        match message.get('type'):
            case 'request':
                self._handleRequest(message)

        self.callbacks.message.call(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _onDisconnect(self):
        self.callbacks.disconnect.call()

    # ------------------------------------------------------------------------------------------------------------------
    def _handleRequest(self, message):
        self.gui.logger.debug(f"Handling request message from parent GUI {self.id}: {message}")

        data = message.get('data')

        if data:
            match data.get('type'):
                case 'category_payload':
                    obj = self.gui.getObjectByUID(data.get('id'))
                    if obj is None:
                        self.gui.logger.warning(f"Could not find object with UID {data.get('id')} for request")
                        return
                    payload = obj.getPayload() if isinstance(obj, Category | GUI) else None

                    if payload is None:
                        self.gui.logger.warning(f"Object with UID {data.get('id')} is not a category or GUI")
                        return

                    response = ResponseMessage(
                        request_id=message.get('request_id'),
                        data=payload,
                    )
                    self.send(response)

                case _:
                    self.gui.logger.warning(f"Unhandled request type {data.get('type')} in message {message}")


@dataclasses.dataclass
class GUISettings:
    color: list = dataclasses.field(default_factory=lambda: [31 / 255, 32 / 255, 35 / 255, 1])
    rows: int = 18
    columns: int = 50
    max_pages: int = 10
    logo_path: str = ''
    name: str = None
    enable_emergency_stop: bool = True
    enable_terminal: bool = True
    bottom_group_size: list = dataclasses.field(default_factory=lambda: [3, 3])
    enable_top_bar: bool = True
    allow_multiple_instances: bool = False
    show_message_rate: bool = True
    message_rate_warning: int = 200
    category_bottom_group_size: list | None = None
    category_bottom_width: float = 0.4


@dataclasses.dataclass
class GUI_Payload:
    id: str
    name: str
    options: dict
    export: Category_Payload
    categories: dict[str, Category_Payload]
    bottom_group: dict
    cli_terminal: dict
    type: str = 'gui'


@callback_definition
class GUI_Callbacks:
    emergency_stop: CallbackContainer


@dataclasses.dataclass
class PopupInstanceData:
    popup_instance: PopupInstance
    frontends: list[WebsocketServerClient]


# === GUI ==============================================================================================================
class GUI:
    id: str
    server: WebsocketServer
    client: WebsocketClient | None
    categories: dict[str, Category]

    frontends: list
    child_guis: dict[str, Child]
    parent_guis: dict[str, Parent]

    export_category: Category
    export_page: Page

    callout_handler: CalloutHandler

    popups: dict[str, Popup]

    bottom_group: Widget_Group

    cli_terminal: CLI_Terminal

    _exit: bool = False

    update_message_lock: threading.Lock

    callbacks: GUI_Callbacks

    # === INIT =========================================================================================================
    def __init__(self, id,
                 host,
                 run_js: bool = False,
                 options=None,
                 task: bool = True,
                 Ts: float = 0.05):

        self.id = self._prepareID(id)

        self.settings = from_dict_auto(GUISettings, options or {})
        if self.settings.name is None:
            self.settings.name = self.id
        self.options = dataclasses.asdict(self.settings)

        self.run_task = task
        self._thread = threading.Thread(target=self._task, daemon=True)  # But only start it if run_task is True

        self.run_js = run_js
        self.Ts = Ts

        self.update_message = GUI_UpdateMessage()

        self.categories = {}
        self.export_category, self.export_page = self._prepareExportCategory()

        self.callbacks = GUI_Callbacks()

        self.server = WebsocketServer(host=host, port=WS_PORT_DESKTOP, heartbeats=False)
        self.server.callbacks.new_client.register(self._new_client_callback)
        self.server.callbacks.client_disconnected.register(self._client_disconnected_callback)
        self.server.callbacks.message.register(self._serverMessageCallback)
        self.server.logger.switchLoggingLevel('INFO', 'DEBUG')

        self.client = None

        self.logger = Logger(f'GUI: {self.id}', 'INFO')

        self.frontends = []
        self.child_guis = {}
        self.parent_guis = {}

        self.cli_terminal = CLI_Terminal(id='cli', cli=None)
        self.cli_terminal.parent = self

        self.js_app_port = PORT_JS_APP
        self.js_process = None

        self.callout_handler = CalloutHandler(gui=self)
        self.callout_handler.callbacks.send_message.register(self._sendCalloutMessage)

        self.popups = {}

        # Event for file picker responses (request-response pattern)
        self.file_picker_event = Event(flags=EventFlag('request_id', str))

        bottom_size = self.options.get('bottom_group_size', [3, 3])
        self.bottom_group = Widget_Group('bottom_group',
                                        rows=bottom_size[0],
                                        columns=bottom_size[1],
                                        border=False,
                                        border_width=0,
                                        title_bottom_border=False,
                                        title='')
        self.bottom_group.parent = self

        self.allow_multiple_instances = self.settings.allow_multiple_instances

        self.update_message_lock = threading.Lock()

        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        return f"{self.id}"

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        return self

    # === METHODS ======================================================================================================
    def start(self):

        # Start the websocket server
        self.server.start()

        # Start the JS Vite GUI
        if self.run_js:
            self.runJSApp()

        # Start the thread
        if self.run_task:
            self.logger.debug("Starting GUI task thread")
            self._thread.start()

        self.logger.info(f"Started GUI \"{self.id}\" on websocket {self.server.host}:{self.server.port}")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.logger.debug("Closing GUI")
        self.server.stop()
        if self.js_process is not None:
            self.js_process.terminate()

        if self.run_task and self._thread.is_alive():
            self._exit = True
            self._thread.join(timeout=5)

        self.logger.info("GUI closed")

    # ------------------------------------------------------------------------------------------------------------------
    def print(self, text, color='white'):
        self.function(function_name='print',
                      args=[text, color],
                      spread_args=True)

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        while not self._exit:
            self._sendUpdateMessage()
            time.sleep(self.Ts)

    # ------------------------------------------------------------------------------------------------------------------
    def _sendUpdateMessage(self):

        # Check if there are any messages to send
        if not self.update_message.messages or len(self.update_message.messages) == 0:
            return

        try:
            # Add a semaphore/mutex to prevent concurrent access
            self.update_message_lock.acquire()
            message = asdict_optimized(self.update_message)
            self.update_message_lock.release()
        except RuntimeError as e:
            self.logger.error(f"Error converting update message to dict: {e}")
            self.update_message = GUI_UpdateMessage()
            return
        self.broadcast(message)
        # Prepare a new empty message
        self.update_message = GUI_UpdateMessage()

    # ------------------------------------------------------------------------------------------------------------------
    def runJSApp(self):
        app_path = get_absolute_path("../")

        self.js_process = run_vite_app(app_path, host=self.server.host, port=self.js_app_port, env_vars={
            'WS_PORT': str(self.server.port),
            'WS_PORT_APP': str(WS_PORT_MOBILE),
            'WS_HOST': self.server.host,
        }, print_link=False, )

        self.logger.important(f"Access GUI at http://{self.server.host}:{self.js_app_port}/gui")

    # ------------------------------------------------------------------------------------------------------------------
    def addCategory(self, category: Category):
        if category.id in self.categories:
            raise ValueError(f"Category with id {category.id} already exists")
        category.parent = self
        self.categories[category.id] = category

        message = AddMessage(
            data=AddMessageData(
                type='category',
                parent=self.uid,
                id=category.uid,
                config=category.getPayload(),
            )
        )
        self.broadcast(message)
        return category

    # ------------------------------------------------------------------------------------------------------------------
    def removeCategory(self, category: Category | str):

        if isinstance(category, str):
            if category in self.categories:
                category = self.categories[category]
            else:
                category = self.getObjectByUID(category)
            if category is None or not isinstance(category, Category):
                self.logger.warning(f"Category with id {category} does not exist")
                return

        if category.id not in self.categories:
            raise ValueError(f"Category with id {category.id} does not exist")
        del self.categories[category.id]

        message = RemoveMessage(
            data=RemoveMessageData(
                type='category',
                parent=self.uid,
                id=category.uid,
            )
        )
        self.broadcast(message)
        category.onDelete()

    # ------------------------------------------------------------------------------------------------------------------
    def openPopup(self, popup: Popup, client=None):
        """
        Adds a popup to the GUI.
        """
        if popup.id in self.popups:
            raise ValueError(f"Popup with id {popup.id} already exists")

        # Get a popup instance
        # popup_instance = popup.getInstance()

        popup.parent = self
        self.popups[popup.id] = popup

        message = AddMessage(
            data=AddMessageData(
                type='popup',
                parent=self.uid,
                id=popup.uid,
                config=popup.getPayload(),
            )
        )
        self.send(message, client=client)

        popup.callbacks.closed.register(lambda *args, **kwargs: self.popups.pop(popup.id, None))
        popup.callbacks.message_send.register(lambda msg: self.broadcast(msg))

        self.logger.info(f"Added popup {popup.id} to GUI {self.id}")
        return popup

    # ------------------------------------------------------------------------------------------------------------------
    def addApplicationButton(self, button):
        self.bottom_group.addWidget(button)

    # ------------------------------------------------------------------------------------------------------------------
    def sendUpdate(self, uid: str, message: UpdateMessage):

        self.update_message_lock.acquire()
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

        self.update_message_lock.release()

    # ------------------------------------------------------------------------------------------------------------------
    def sendToFrontend(self, frontend, message):
        """
        Sends a message to a specific frontend.
        If the message is a dataclass, it will be converted to a dict.
        """
        if is_dataclass(message):
            message = asdict_optimized(message)

        try:
            self.server.sendToClient(frontend, message)
        except Exception as e:
            self.logger.error(f"Error sending message to frontend {frontend}: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def sendToAllFrontends(self, message):

        if is_dataclass(message):
            message = asdict_optimized(message)

        for frontend in self.frontends:
            self.server.sendToClient(frontend, message)

    # ------------------------------------------------------------------------------------------------------------------
    def sendToParents(self, message):
        if is_dataclass(message):
            message = asdict_optimized(message)

        for parent in self.parent_guis.values():
            parent.send(message)

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
    def addChildGUI(self,
                    child_address,
                    child_port,
                    parent_object: Category | GUI | str = '',
                    name: str = None,
                    child_object_id=None):

        self.logger.debug(f"Connecting to child GUI at {child_address}:{child_port}")

        if isinstance(parent_object, GUI | Category):
            # If the parent is a GUI or Category, use its UID
            parent_object = parent_object.uid

        child = Child(name=name,
                      address=child_address,
                      port=child_port,
                      client=WebsocketClient(child_address, child_port),
                      parent_object_uid=parent_object,
                      gui=self,
                      child_object_id=child_object_id)

        self.child_guis[f"{child_address}:{child_port}"] = child
        child.callbacks.connect.register(lambda *args, **kwargs:
                                         self.logger.info(f"Connected to child GUI at {child_address}:{child_port}"))

    # === PRIVATE METHODS ==============================================================================================
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
        if not gui_id or gui_id != self.id:
            self.logger.warning(f"UID '{uid}' does not match this GUI's ID '{self.id}'")
            return None

        # If the remainder is empty, we are looking for the GUI itself
        if not remainder:
            return self

        # 4) Split off the first ID. This should be the type of object we are looking for
        object_type, remainder = split_path(remainder)

        if object_type not in ('categories', 'popups', 'callouts', 'bottom_group'):
            self.logger.warning(f"UID '{uid}' does not start with a valid object type (categories/popups/callouts)")
            return None

        # 5) Switch based on the object type
        match object_type:
            case 'categories':
                category_id, remainder = split_path(remainder)
                if not category_id:
                    self.logger.warning(f"UID '{uid}' does not contain a valid category ID")
                    return None

                # Check if the category ID is a valid category
                if category_id not in self.categories:
                    self.logger.warning(f"Category ID '{category_id}' not found in GUI '{self.id}'")
                    return None

                category = self.categories[category_id]

                if not remainder:
                    return category

                # If there is a remainder, delegate to the category's getObjectByPath
                return category.getObjectByPath(remainder)

            case 'popups':

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

            case 'bottom_group':
                widget_id, remainder = split_path(remainder)
                if not widget_id:
                    self.logger.warning(f"UID '{uid}' does not contain a valid bottom_group widget ID")
                    return None

                return self.bottom_group.getObjectByPath(widget_id)

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):

        payload = GUI_Payload(
            id=self.uid,
            name=self.options['name'],
            options=self.options,
            export=self.export_category.getPayload(),
            categories={k: v.getPayload() for k, v in self.categories.items()},
            bottom_group=self.bottom_group.getPayload(),
            cli_terminal=self.cli_terminal.getPayload() if self.settings.enable_terminal else None,
        )

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def _initializeFrontend(self, frontend):
        # Send Initialize Message
        message = InitMessage(
            configuration=self.getPayload(),
        )
        self.server.sendToClient(frontend, asdict_optimized(message))

        # Check if there are open popups and send them
        for popup in self.popups.values():
            popup_message = AddMessage(
                data=AddMessageData(
                    type='popup',
                    parent=self.uid,
                    id=popup.uid,
                    config=popup.getPayload(),
                )
            )
            self.server.sendToClient(frontend, asdict_optimized(popup_message))

    # ------------------------------------------------------------------------------------------------------------------
    def _closeFrontend(self, client):
        message = {
            'type': 'close',
            'data': {},
        }
        self.server.sendToClient(client, message)

    # ------------------------------------------------------------------------------------------------------------------
    def _initializeParent(self, parent_client):

        parent = Parent(id='', gui=self, client=parent_client)
        self.parent_guis[parent_client] = parent

        message = InitMessage(
            configuration=self.getPayload(),
        )

        parent.send(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _new_client_callback(self, client):
        self.logger.debug(f"New client connected: {client}")

    # ------------------------------------------------------------------------------------------------------------------
    def _client_disconnected_callback(self, client: WebsocketServerClient):
        self.logger.debug(f"Client disconnected: {client.address}:{client.port}")

        if client in self.frontends:
            self.frontends.remove(client)
            self.logger.debug(f"Frontend disconnected: {client.address}:{client.port} ({len(self.frontends)})")
        elif client in self.child_guis:
            self.logger.warning(f"TODO: Child GUI disconnected: {client.address}:{client.port}")

    # ------------------------------------------------------------------------------------------------------------------
    def _serverMessageCallback(self, client, message, *args, **kwargs):
        self.logger.debug(f"Message received: {message}")

        match message['type']:
            case 'handshake':
                self._handleHandshakeMessage(client, message)
            case 'event':
                self._handleEventMessage(message, sender=client)
            case 'request':
                ...
                # These are handled by the parent objects, so no need to do something here
            case 'cli_command':
                # this comes from the terminal or a direct command and must be redirected to the cli
                self._handleCliCommandMessage(message, sender=client)
                pass
            case _:
                self.logger.warning(f"Unknown message type: {message['type']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleHandshakeMessage(self, client: WebsocketServerClient, message):
        self.logger.debug(f"Received handshake message from {client}: {message}")

        data = message.get('data')
        if data is None:
            self.logger.warning(f"Handshake message from {client} did not contain data")
            return

        match data['client_type']:
            case 'frontend':
                self._handleFrontendHandshake(client, data)
            case 'child_gui':
                self.logger.info(f"New child GUI connected: {client.address}:{client.port}")
                raise NotImplementedError(f"Child GUI handling not implemented yet for {client.address}:{client.port}")
            case 'parent_gui':
                self.logger.info(f"New parent GUI connected: {client.address}:{client.port}")
                self._initializeParent(client)
            case _:
                self.logger.warning(f"Unknown client type: {data['client_type']}")
                return

    # ------------------------------------------------------------------------------------------------------------------
    def _handleFrontendHandshake(self, client: WebsocketServerClient, data):
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
    def _connectFrontend(self, client: WebsocketServerClient):
        self.frontends.append(client)
        self._initializeFrontend(client)
        self.logger.debug(f"New frontend connected: {client.address}:{client.port} ({len(self.frontends)})")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleEventMessage(self, message, sender=None):
        """
        Handle an 'event' from a frontend. If the event's id belongs to
        a child GUI (i.e. starts with `<parent_mount>/<child.id>`), strip
        off the parent and child prefixes, re-prepend the child.id, and
        forward it; otherwise route it to a local element.
        """
        # 1) must have an id for use with other objects
        msg_id = message.get('id')

        if not msg_id or msg_id == self.id:
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
        else:
            element.onEvent(message.get('data'), sender=sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleCliCommandMessage(self, message, sender=None):
        self.cli_terminal.handleMessage(message, sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _handleGuiEvent(self, message, sender=None):
        data = message.get('data', {})

        match data.get('event'):
            case 'disconnect_other':
                # close every other frontend
                for f in list(self.frontends):
                    if f is not sender:
                        self._closeFrontend(f)

                # Initialize the frontend that sent the message
                self._connectFrontend(sender)

            case 'emergency_stop':
                self.callbacks.emergency_stop.call()

            case 'file_picker_response':
                # Handle file picker response from frontend
                request_id = data.get('request_id')
                if request_id:
                    self.file_picker_event.set(data=data, flags={'request_id': request_id})

            case _:
                self.logger.warning(f"Unhandled GUI event: {data.get('event')} in message {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def _sendCalloutMessage(self, message):
        self.broadcast(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _checkPathForChildGUI(self, path) -> tuple[Child, str] | tuple[None, str]:
        for child in self.child_guis.values():
            parent_mount = child.path_in_gui.rstrip('/')  # e.g. ":myGui:/categoryX"
            full_mount = f"{parent_mount}/{child.id}"  # e.g. ":myGui:/categoryX/childGuiID"

            # Does the event target live at or under this full_mount?
            if path == full_mount or path.startswith(full_mount + '/'):
                # strip off the full_mount prefix
                suffix = path[len(full_mount):]  # e.g. "" or "/page1/button1"
                if suffix.startswith('/'):
                    suffix = suffix[1:]  # e.g. "page1/button1"

                # build the ID the child expects: always start with its own id
                child_obj_id = child.id + (f"/{suffix}" if suffix else "")
                return child, child_obj_id

        # No child GUI matched
        return None, ''

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _prepareID(gui_id: str) -> str:
        """
        Prepare an ID for use in the GUI by removing spaces and slashes.
        """
        if check_for_spaces(gui_id):
            raise ValueError(f"ID '{gui_id}' contains spaces")
        if '/' in gui_id:
            raise ValueError(f"ID '{gui_id}' contains slashes")
        if ':' in gui_id:
            raise ValueError(f"ID '{gui_id}' contains colons")

        gui_id = f":{gui_id}:"

        return gui_id

    # ------------------------------------------------------------------------------------------------------------------
    def _prepareExportCategory(self):
        category = Category(id=self.id,
                            name=f"{self.id}_exp",
                            icon='🌐',
                            max_pages=1,
                            top_icon='🌐'
                            )

        export_page = Page(id=f"{self.id}_exp_page1",
                           name=f"{self.id}_exp_page1",
                           )

        category.addPage(export_page)

        return category, export_page

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
    def open_file_picker(self,
                         accept: str = '.yaml,.yml,.json',
                         timeout: float = 60.0,
                         max_size: int = 0,
                         save_dir: str | None = None,
                         client=None) -> str | None:
        """
        Opens a file picker dialog on the connected frontend client and waits for the user to select a file.
        The selected file is uploaded and saved to a temporary directory on the host.

        Args:
            accept: File type filter (e.g., '.yaml,.yml,.json')
            timeout: Maximum time to wait for user to select a file (seconds)
            max_size: Maximum file size in bytes (0 = no limit)
            save_dir: Directory to save the uploaded file. If None, uses a temp directory.
            client: Specific client to send the request to. If None, broadcasts to all.

        Returns:
            Path to the saved file on the host, or None if cancelled/timeout/error
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Send function call to frontend to open file picker
        self.function(
            function_name='openFilePicker',
            args={
                'request_id': request_id,
                'accept': accept,
                'max_size': max_size,
                'title': 'Select File'
            },
            spread_args=False,
            client=client
        )

        # Wait for response
        data, trace = self.file_picker_event.wait(
            predicate=pred_flag_equals('request_id', request_id),
            timeout=timeout
        )

        if data is TIMEOUT:
            self.logger.warning("File picker timed out")
            return None

        if not data:
            self.logger.warning("File picker timed out or no response received")
            return None

        # Get the response data
        response = self.file_picker_event.get_data()

        if not response.get('success'):
            error = response.get('error', 'User cancelled or unknown error')
            self.logger.debug(f"File picker cancelled or failed: {error}")
            return None

        file_data = response.get('file')
        if not file_data:
            self.logger.warning("File picker response missing file data")
            return None

        # Decode and save the file
        try:
            file_name = file_data.get('name', 'uploaded_file')
            file_content_b64 = file_data.get('content', '')

            # Decode base64 content
            file_content = base64.b64decode(file_content_b64)

            # Determine save directory
            if save_dir is None:
                save_dir = tempfile.gettempdir()

            # Ensure the save directory exists
            os.makedirs(save_dir, exist_ok=True)

            # Create full path
            file_path = os.path.join(save_dir, file_name)

            # Write the file
            with open(file_path, 'wb') as f:
                f.write(file_content)

            self.logger.info(f"File saved: {file_path}")
            return file_path

        except Exception as e:
            self.logger.error(f"Failed to save uploaded file: {e}")
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def send_file_for_download(
            self,
            file_path: str,
            filename: str | None = None,
            client=None
    ) -> bool:
        """
        Sends a file to the connected client(s) for download.
        The browser will automatically prompt the user to save the file.

        Args:
            file_path: Path to the file on the host to send
            filename: Optional filename for download (defaults to original filename)
            client: Specific client to send to, or None for all connected clients

        Returns:
            True if file was sent successfully, False otherwise
        """
        try:
            import os

            if not os.path.exists(file_path):
                self.logger.error(f"File not found: {file_path}")
                return False

            # Read and encode file
            with open(file_path, 'rb') as f:
                file_content = f.read()

            file_content_b64 = base64.b64encode(file_content).decode('utf-8')

            # Determine filename
            if filename is None:
                filename = os.path.basename(file_path)

            # Determine MIME type based on extension
            ext = os.path.splitext(filename)[1].lower()
            mime_types = {
                '.json': 'application/json',
                '.yaml': 'application/x-yaml',
                '.yml': 'application/x-yaml',
                '.txt': 'text/plain',
                '.csv': 'text/csv',
                '.pdf': 'application/pdf',
                '.html': 'text/html',
                '.h5': 'application/x-hdf5',
                '.hdf5': 'application/x-hdf5',
            }
            mime_type = mime_types.get(ext, 'application/octet-stream')

            # Send to client via function call
            self.function(
                function_name='downloadFile',
                args={
                    'filename': filename,
                    'content': file_content_b64,
                    'mimeType': mime_type
                },
                spread_args=False,
                client=client
            )

            self.logger.info(f"Sent file for download: {filename}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send file for download: {e}")
            return False
