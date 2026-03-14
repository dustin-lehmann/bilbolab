from __future__ import annotations

import abc
import copy
import dataclasses
from typing import Any
import re

# === CUSTOM MODULES ===================================================================================================
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dict_utils import replaceField, update_dict, ObservableDict, replaceStringInDict
from core.utils.logging_utils import Logger
from core.utils.uuid_utils import generate_uuid
from extensions.gui.src.lib.messages import AddMessage, AddMessageData, RemoveMessage, RemoveMessageData
from extensions.gui.src.lib.utilities import check_for_spaces, split_path, check_id


@dataclasses.dataclass
class ObjectMessage:
    id: str
    data: dict  # Data to send to the widget
    type: str = 'object_message'  # Type of message


@dataclasses.dataclass
class UpdateMessage:
    id: str  # Object ID
    important: bool  # Whether this update is important and needs to be sent
    data: dict  # Data to update the object with
    type: str = 'update'  # Type of message


@dataclasses.dataclass
class UpdateConfigMessage:
    id: str  # Object ID
    config: dict  # Configuration to update the object with
    type: str = 'update_config'  # Type of message


@dataclasses.dataclass
class FunctionMessage:
    function_name: str  # Name of the function to call
    args: dict  # Arguments to pass to the function
    spread_args: bool = True  # Whether to spread the args or not
    type: str = 'function'  # Type of message


# ======================================================================================================================
class GUI_Object(abc.ABC):
    type: str
    id: str
    parent: GUI_Object | None | Any = None
    config: dict
    payload: dict
    parent_config: dict  # A place for the parent to store data in

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, id, **kwargs):
        self.id = id

        self.parent_config = {}

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if self.parent:
            return f"{self.parent.uid}/{self.id}"
        else:
            return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        if self.parent:
            return self.parent.getGUI()
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, message, client=None):
        gui = self.getGUI()
        if gui is None:
            return
        gui.send(message, client=client)

    # ------------------------------------------------------------------------------------------------------------------
    def sendObjectMessage(self, message, client=None):
        message = ObjectMessage(
            id=self.uid,
            data=message,
        )
        self.sendMessage(message, client=client)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self):
        config = {
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = {
            'id': self.uid,
            'type': self.type,
            'config': self.getConfiguration(),
        }
        return payload


# # ======================================================================================================================
# class WidgetInstance(GUI_Object):
#     id: str
#     widget: Widget
#     parent: Any
#     override_configuration: dict
#
#     parent_config: dict
#
#     # === INIT =========================================================================================================
#     def __init__(self, id: str, widget: Widget, **kwargs):
#         super().__init__(id, **kwargs)
#         self.id = id
#         self.widget = widget
#         if kwargs is None:
#             kwargs = {}
#
#         self.override_configuration = kwargs
#         self.parent_config = {}
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def getPayload(self) -> dict:
#         payload = self.widget.getPayload()
#         payload['config'].update(self.override_configuration or {})
#         # replaceField(payload, str, 'id', self.uid)
#         replaceStringInDict(data=payload,
#                             key='id',
#                             new_value=self.uid,
#                             regex=fr"^{re.escape(self.id)}$")
#         return payload
#

# ======================================================================================================================
@callback_definition
class Widget_Callbacks:
    first_built: CallbackContainer


class Widget(GUI_Object):
    id: str
    type: str

    config: dict
    data: dict

    context_menu: WidgetContextMenu

    callbacks: Widget_Callbacks

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, widget_id: str | None = None, **kwargs):

        if widget_id is None:
            widget_id = generate_uuid(prefix='widget_')

        check_id(widget_id)

        super().__init__(widget_id)
        default_config = {
            'padding_left': 0,
            'padding_right': 0,
            'padding_top': 0,
            'padding_bottom': 0,
            'tooltip': '',
            'border_width': 1,
            'border_style'
            'border': True,
            'disabled': False,
            'dim': False
        }

        self.config = ObservableDict()

        self.config = update_dict(default_config, kwargs)

        self.id = widget_id
        self.logger = Logger(self.id, 'DEBUG')

        self.callbacks = Widget_Callbacks()

        if 'context_menu' in kwargs and isinstance(kwargs['context_menu'], dict):
            context_menu_data = kwargs['context_menu']
        else:
            context_menu_data = {}

        self.context_menu = WidgetContextMenu(id=f"{self.id}_context_menu", object=self, **context_menu_data)

    # ------------------------------------------------------------------------------------------------------------------
    def function(self, function_name, args, spread_args=True, client=None):

        message = FunctionMessage(
            function_name=function_name,
            args=args,
            spread_args=spread_args,
        )
        self.sendObjectMessage(message, client=client)

    # ------------------------------------------------------------------------------------------------------------------
    def sendConfigUpdate(self, config: dict):
        message = UpdateConfigMessage(
            id=self.uid,
            config=self.getConfiguration(),
        )
        self.sendObjectMessage(message)

    # ------------------------------------------------------------------------------------------------------------------
    def sendUpdate(self, data, important=False):
        gui = self.getGUI()
        if gui is None:
            return

        message = UpdateMessage(
            id=self.uid,
            important=important,  # Assuming updates are important by default
            data=data)

        try:
            gui.sendUpdate(self.uid, message)
        except Exception as e:
            self.logger.error(f"Error sending update: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def getConfiguration(self) -> dict:
        config = super().getConfiguration()
        config['context_menu'] = self.context_menu.getPayload()
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def onEvent(self, message, sender=None):
        if 'event' not in message:
            self.logger.warning(f"Message {message} has no event type")
            return

        # Catch general messages
        match message.get('event'):
            case 'context_menu':
                self.context_menu.handleEvent(message, sender)
            case 'first_built':
                self.onFirstBuilt()
                return

        self.handleEvent(message, sender)

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def handleEvent(self, message, sender=None) -> None:
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, **kwargs):
        # Go through all kwargs and update the config if the key is in the config
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value
            elif hasattr(self, key):
                setattr(self, key, value)

        self.sendConfigUpdate(self.getConfiguration())

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self):
        payload = super().getPayload()
        payload['context_menu'] = self.context_menu.getPayload()
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def accept(self, accept=True, client=None):
        self.function(
            function_name='accept',
            args=accept,
            client=client,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def enable(self, enable=True, disable_opacity=None):
        self.function(
            function_name='enable',
            args={'enable': enable, 'disable_opacity': disable_opacity},
            spread_args=True
        )
        self.config['disabled'] = not enable

    # ------------------------------------------------------------------------------------------------------------------
    def disable(self):
        self.enable(False)

    # ------------------------------------------------------------------------------------------------------------------
    def dim(self, dim: bool = True):
        self.function(
            function_name='dim',
            args=dim,
            spread_args=True
        )

        self.config['dim'] = dim

    # ------------------------------------------------------------------------------------------------------------------
    def onFirstBuilt(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def onDelete(self):
        ...
    # === PRIVATE METHODS ==============================================================================================


# ======================================================================================================================
class Widget_Group(Widget):
    type: str = 'group'
    parent: Any | Widget_Group = None  # Parent can be another GUI_Object_Group or None

    parent_config: dict

    def __init__(self, group_id: str | None = None, **kwargs):
        """
        :param group_id: unique ID of this group (no spaces, slashes or colons)
        :param config: any of the JS defaults for ObjectGroup
        """
        # --- base checks + setup ---

        if group_id is None:
            group_id = generate_uuid(prefix='group_')

        super().__init__(group_id)
        defaults = {
            'rows': 10,
            'columns': 10,
            'fit': True,
            'show_scrollbar': False,
            'scrollbar_handle_color': '#888',
            'title': '',
            'title_font_size': 10,
            'title_color': [1, 1, 1, 0.8],
            'title_position': 'center',
            'show_title': False,
            'background_color': 'transparent',
            'border_color': '#444',
            'border_width': 1,
            'fill_empty': True,
        }
        # merge in any overrides
        self.config = {**defaults, **kwargs}

        self.parent_config = {}

        self.objects: dict[str, Widget] = {}

        # logger
        self.logger = Logger(f"Group {self.id}", 'DEBUG')

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def widget(self):
        return self

    # ------------------------------------------------------------------------------------------------------------------
    def addWidget(
            self,
            widget: Widget,
            row: int | None = None,
            column: int | None = None,
            width: int = 1,
            height: int = 1,
            **kwargs
    ) -> Widget:
        """
        Place a child widget into this group at the given grid cell.
        If row or column is None, auto‐find the first spot that fits.
        """
        # 2) find or check placement
        if row is None or column is None:
            row, column = self._placeObject(row, column, width, height)
        else:
            self._checkSpace(row, column, width, height)

        # 3) remember its layout
        self.objects[widget.id] = widget
        widget.parent_config['row'] = row
        widget.parent_config['column'] = column
        widget.parent_config['width'] = width
        widget.parent_config['height'] = height

        widget.parent = self

        # 4) send the AddMessage to front‐end
        payload = {
            'row': row,
            'column': column,
            'width': width,
            'height': height,
            **widget.getPayload()
        }
        message = AddMessage(
            data=AddMessageData(
                type=widget.type,
                id=widget.uid,
                config=payload,
                parent=self.uid,
            )
        )
        self.sendObjectMessage(message)
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

        self.sendObjectMessage(message)

        widget.parent = None
        del self.objects[widget.id]

    # ------------------------------------------------------------------------------------------------------------------
    def _checkSpace(self, row: int, column: int, width: int, height: int):
        """Raise if the specified rect is out of bounds or overlaps existing children."""
        rows = self.config['rows']
        cols = self.config['columns']
        if row < 1 or column < 1 or row + height - 1 > rows or column + width - 1 > cols:
            raise ValueError("Object does not fit within group bounds")

        # build occupancy grid
        occ = [[False] * cols for _ in range(rows)]
        for e in self.objects.values():
            for r in range(e.parent_config['row'] - 1, e.parent_config['row'] - 1 + e.parent_config['height']):
                for c in range(e.parent_config['column'] - 1, e.parent_config['column'] - 1 + e.parent_config['width']):
                    occ[r][c] = True

        for r in range(row - 1, row - 1 + height):
            for c in range(column - 1, column - 1 + width):
                if occ[r][c]:
                    raise ValueError("Grid cells already occupied")

    # ------------------------------------------------------------------------------------------------------------------
    def _placeObject(
            self,
            row: int | None,
            column: int | None,
            width: int,
            height: int
    ) -> tuple[int, int]:
        """
        Finds the first available position for an object of given size.
        If one coordinate is fixed, searches along the other.
        """
        rows = self.config['rows']
        cols = self.config['columns']

        # build occupancy grid
        occ = [[False] * cols for _ in range(rows)]
        for e in self.objects.values():
            for r in range(e.parent_config['row'] - 1, e.parent_config['row'] - 1 + e.parent_config['height']):
                for c in range(e.parent_config['column'] - 1, e.parent_config['column'] - 1 + e.parent_config['width']):
                    occ[r][c] = True

        def fits(r: int, c: int) -> bool:
            if r < 1 or c < 1 or r + height - 1 > rows or c + width - 1 > cols:
                return False
            for rr in range(r - 1, r - 1 + height):
                for cc in range(c - 1, c - 1 + width):
                    if occ[rr][cc]:
                        return False
            return True

        # Neither fixed: scan rows then cols
        if row is None and column is None:
            for r in range(1, rows - height + 2):
                for c in range(1, cols - width + 2):
                    if fits(r, c):
                        return r, c

        # Row fixed: scan columns
        if row is not None and column is None:
            for c in range(1, cols - width + 2):
                if fits(row, c):
                    return row, c

        # Column fixed: scan rows
        if column is not None and row is None:
            for r in range(1, rows - height + 2):
                if fits(r, column):
                    return r, column

        raise ValueError("No available space to place object")

    def _markSpace(self, row: int, column: int, width: int, height: int):
        """
        (Optionally) record occupancy. Since we rebuild occupancy
        on each placement from self.objects, this can be a no-op.
        """
        pass

    # -------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path: str) -> Widget | Widget_Group | None:
        """
        Recursively look up a child inside this group via "sub1/sub2/widget".
        """
        # same as your stub, unchanged
        first, rest = split_path(path)
        if not first:
            return None

        if first not in self.objects:
            return None

        child = self.objects[first]

        if not rest:
            return child
        if isinstance(child, Widget_Group):
            return child.getObjectByPath(rest)
        return None

    # -------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'id': self.uid,
            'type': self.type,
            **self.config
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        """
        For a full‐front‐end refresh you might send the layout of every child:
        { uid: { row, column, width, height, id, type, config }, … }
        """

        objs = {}
        for uid, obj in self.objects.items():
            inst = obj
            object_payload = inst.getPayload()
            object_payload.update({
                'row': obj.parent_config['row'],
                'column': obj.parent_config['column'],
                'width': obj.parent_config['width'],
                'height': obj.parent_config['height'],
            })
            objs[inst.uid] = object_payload

        payload = {
            'id': self.uid,
            'type': self.type,
            'config': self.getConfiguration(),
            'objects': objs,
        }

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        """
        Called once, after this group is added to a page, to push
        its initial configuration and children to the front‐end.
        """
        # 1) send our own config
        self.sendConfigUpdate(self.getConfiguration())

        # 2) send all of our children in one shot
        #    so front‐end will re-populate its gridDiv
        self.sendUpdate(self.getPayload(), important=True)

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        """
        Handle a message coming *from* the front‐end.
        If it names a sub-path, forward it there; otherwise log it.
        """
        # if it's a config‐update or function‐call, let the base handle it
        mtype = message.get('type')
        if mtype in ('update_config', 'function'):
            # e.g. update_config → calls our updateConfig
            #       function → calls GUI_Object.function()
            return super().handleEvent(message)

        # if it's a straight data‐update for us:
        if mtype == 'update':
            return super().handleEvent(message)

        # anything else we'll try to forward by path:
        target = message.get('id', '')
        rest = message.get('data', {})
        child = self.getObjectByPath(target)
        if child is not None:
            return child.handleEvent(rest)

        self.logger.warning(f"Group {self.id} got an unhandled message: {message}")
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, **kwargs):
        """
        Merge in new config‐values (e.g. cols=3, fillEmpty=False),
        then tell the front‐end to re-layout both us and our children.
        """
        # 1) merge into our local dict
        for k, v in kwargs.items():
            if k in self.config:
                self.config[k] = v

        # 2) broadcast just our config change
        self.sendConfigUpdate(self.getConfiguration())

        # 3) broadcast a full children‐layout update
        self.sendUpdate(self.getPayload(), important=True)

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        if self.parent:
            return self.parent.getGUI()
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self):
        payload = super().getPayload()
        payload['id'] = self.uid
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def onDelete(self):
        for obj in self.objects.values():
            obj.onDelete()


# ----------------------------------------------------------------------------------------------------------------------
class PagedWidgetGroup(Widget_Group):
    position = None
    hidden = False
    type: str = 'group'

    def __init__(self, group_id, hidden: bool = False, **kwargs):
        super().__init__(group_id, **kwargs)
        self.hidden = hidden

    def getConfiguration(self) -> dict:
        config = super().getConfiguration()
        config['hidden'] = self.hidden
        return config


# ----------------------------------------------------------------------------------------------------------------------
class GroupPageWidget(Widget):
    type: str = 'group_container'
    groups: dict[str, PagedWidgetGroup]
    parent: Widget_Group | Any = None
    start_group: PagedWidgetGroup | None = None

    # === INIT =========================================================================================================
    def __init__(self, group_id, **kwargs):
        super().__init__(group_id, **kwargs)

        default_config = {
            'show_group_bar': True,
            'group_bar_position': 'top',
            'group_bar_style': 'buttons',  # Can be 'buttons', 'icons' or 'dots'
            'background_color': [0, 0, 0, 0],
            'border_color': '#444',
            'border_width': 1,
        }

        self.config = update_dict(default_config, kwargs)

        self.groups = {}

    # === METHODS ======================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            'id': self.uid,
            'type': self.type,
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'type': self.type,
            'config': self.getConfiguration(),
            'groups': {k: v.getPayload() for k, v in self.groups.items()},
            'start_group': self.start_group.uid if self.start_group else None,
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def getGroup(self, group_id: str) -> PagedWidgetGroup | None:
        if group_id in self.groups:
            return self.groups[group_id]
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def getGroupByPosition(self, position: int) -> PagedWidgetGroup | None:
        for page_id, page in self.groups.items():
            if page.position == position:
                return page

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def addGroup(self, group: PagedWidgetGroup) -> PagedWidgetGroup:

        # 1. Check if the page with this ID already exists
        if group.id in self.groups:
            raise ValueError(f"Group with ID '{group.id}' already exists")

        # 2. Add the page to the pages dict
        self.groups[group.id] = group
        group.parent = self

        # 3. Set the page's position if the page is user-selectable
        if not group.hidden:
            group.position = self._getNextFreePosition()

        # If the page is user-selectable and we do not have a start page, set the first page as the start page
        if not group.hidden and self.start_group is None:
            self.start_group = group

        # 4. Send a message to the front-end to add the page
        message = AddMessage(
            data=AddMessageData(
                type='group_page',
                parent=self.uid,
                id=group.uid,
                config=group.getPayload()
            )
        )

        self.sendObjectMessage(message)
        return group

    # ------------------------------------------------------------------------------------------------------------------
    def removeGroup(self, group: str | PagedWidgetGroup):
        if isinstance(group, str):
            group = self.getGroup(group)

        if group is None or group.id not in self.groups:
            raise ValueError(f"Page with ID '{getattr(group, 'page_id', group)}' does not exist")

        # Notify front-end first (so it can animate/clean DOM)
        message = RemoveMessage(
            data=RemoveMessageData(
                type='group_page',
                parent=self.uid,
                id=group.uid
            )
        )
        self.sendObjectMessage(message)

        # Local removal
        del self.groups[group.id]

        # Repack positions for visible pages to keep them dense and sorted (optional but nice)
        pos = 0
        for p in sorted([p for p in self.groups.values() if not p.hidden], key=lambda x: (x.position or 0)):
            p.position = pos
            pos += 1

        # Adjust start_page if needed
        if self.start_group == group:
            self.start_group = None
            # pick next visible page as start page (if any)
            for p in sorted([p for p in self.groups.values() if not p.hidden], key=lambda x: (x.position or 0)):
                self.start_group = p
                break

    # ------------------------------------------------------------------------------------------------------------------
    def setGroup(self, group: str | PagedWidgetGroup):

        if isinstance(group, str):
            group = self.getGroup(group)

        if group is None:
            raise ValueError(f"Page {group} does not exist")

        if group.id not in self.groups:
            raise ValueError(f"Page with ID '{group.id}' does not exist")

        self.start_group = group

        # Send a function message
        self.function(
            function_name='showGroup',
            args=group.uid,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def showGroupBar(self, show=True):
        self.config['show_group_bar'] = show
        if show:
            self.function(
                function_name='showGroupBar',
                args=None,
            )
        else:
            self.function(
                function_name='hideGroupBar',
                args=None,
            )

    # ------------------------------------------------------------------------------------------------------------------
    def hideGroupBar(self):
        self.showGroupBar(False)

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        self.logger.important(f"Group {self.id} got an event: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path: str) -> Any:
        # same as your stub, unchanged
        first, rest = split_path(path)
        if not first:
            return None

        if first not in self.groups:
            self.logger.warning(f"{first} not in self.pages")
            return None

        return self.groups[first].getObjectByPath(rest)

    # ------------------------------------------------------------------------------------------------------------------
    def getGUI(self):
        if self.parent:
            return self.parent.getGUI()
        return None

    # === PRIVATE METHODS ==============================================================================================
    def _getNextFreePosition(self):
        current_position = 0

        while True:
            page = self.getGroupByPosition(current_position)
            if page is None:
                return current_position
            else:
                current_position += 1


# === GUI CONTAINER ====================================================================================================
class GUI_Container(GUI_Object):
    id: str
    parent: Any
    object: Widget | GUI_Container | None = None

    type = 'container'

    # === INIT =========================================================================================================
    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            # sizing
            "width_mode": "fill",  # 'fill' | 'fixed' | 'auto'
            "width": 100,
            "height_mode": "fill",  # 'fill' | 'fixed' | 'auto'
            "height": 100,
            "min_height": 0,
            "max_height": None,
            "min_width": 0,
            "max_width": None,

            # inner alignment & overflow
            "vertical_align": "top",  # 'top' | 'center' | 'bottom'
            "horizontal_align": "center",  # 'left' | 'center' | 'right'
            "overflow_y": "auto",
            "overflow_x": "auto",
            "padding": 4,

            # visuals
            "background_color": [0, 0, 0, 0],  # transparent by default
            "border_color": [255, 255, 255, 0.12],
            "border_width": 1,
            "border_style": "solid",
            "border_radius": 6,

            # optional role/class
            "className": "",
            "role": "",
            "ariaLabel": "",
        }

        self.config = update_dict(default_config, kwargs)

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        if self.parent:
            return f"{self.parent.uid}/{self.id}"
        else:
            return self.id

    # === METHODS ======================================================================================================
    def addObject(self, obj: Widget | Widget_Group | GUI_Container | GUI_Container_Stack):
        if self.object is not None:
            raise ValueError(f"Container {self.id} already has an object")

        self.object = obj
        obj.parent = self

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path):
        first, remainder = split_path(path)

        if self.object is None:
            return None

        if first != self.object.id:
            return None

        if not remainder:
            return self.object
        return self.object.getObjectByPath(remainder)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'id': self.uid,
            'type': self.type,
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'type': self.type,
            'config': self.getConfiguration(),
            'object': self.object.getPayload() if self.object else None,
        }
        return payload
    # === PRIVATE METHODS ==============================================================================================


# === GUI COLLAPSIBLE CONTAINER ========================================================================================
class GUI_CollapsibleContainer(GUI_Container):
    type = 'collapsible_container'

    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)

        default_config = {
            "title": self.id,
            "start_collapsed": False,
            "headbar_height": 28,
            "headbar_background_color": [1, 1, 1, 0.1],
            "headbar_border_width": 1,
            "headbar_border_color": [255, 255, 255, 0.12],
            "headbar_radius": 6,
            "transition_ms": 160,
        }

        self.config = update_dict(self.config, default_config, kwargs, allow_add=True)


# === GUI CONTAINER STACK ==============================================================================================
class GUI_Container_Stack(GUI_Object):
    type = 'container_stack'
    id: str
    containers: dict[str, GUI_Container]

    # === INIT =========================================================================================================
    def __init__(self, id, **kwargs):
        super().__init__(id, **kwargs)
        self.id = id

        default_config = {

        }

        self.config = update_dict(default_config, kwargs)

        self.containers = {}

    # === METHODS ======================================================================================================
    def addContainer(self, container: GUI_Container):
        if container.id in self.containers:
            raise ValueError(f"Container with ID '{container.id}' already exists")
        self.containers[container.id] = container
        container.parent = self

        message = AddMessage(
            data=AddMessageData(
                type='container',
                parent=self.uid,
                id=container.id,
                config=container.getPayload()
            )
        )

        # self.

    # ------------------------------------------------------------------------------------------------------------------
    def removeContainer(self, container: str | GUI_Container):
        if isinstance(container, str):
            container = self.containers.get(container)

        if container is None:
            raise ValueError(f"Container {container} does not exist")

        del self.containers[container.id]
        container.parent = None

        message = RemoveMessage(
            data=RemoveMessageData(
                type='container',
                parent=self.uid,
                id=container.id
            )
        )

    # ------------------------------------------------------------------------------------------------------------------
    def getObjectByPath(self, path: str) -> Any:

        first, remainder = split_path(path)
        if not first:
            return None

        if first not in self.containers:
            return None

        if not remainder:
            return self.containers[first]

        return self.containers[first].getObjectByPath(remainder)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'id': self.uid,
            'type': 'container_stack',
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'type': 'container_stack',
            'config': self.getConfiguration(),
            'containers': {k: v.getPayload() for k, v in self.containers.items()},
        }
        return payload
    # === PRIVATE METHODS ==============================================================================================


# === CONTAINER WRAPPER ================================================================================================
class ContainerWrapper(Widget):
    type: str = 'ContainerWrapper'

    container: GUI_Container | None = None

    # === INIT =========================================================================================================
    def __init__(self, widget_id, **kwargs):
        super().__init__(widget_id, **kwargs)

        self.container = GUI_Container(f"{widget_id}_container", **kwargs)
        self.container.parent = self

    # === METHODS ======================================================================================================

    # === PRIVATE METHODS ==============================================================================================
    def getObjectByPath(self, path: str) -> Any:
        first, remainder = split_path(path)
        if not first:
            return None

        if first == self.container.id:
            if not remainder:
                return self.container
            return self.container.getObjectByPath(remainder)

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = super().getPayload()
        payload['container'] = self.container.getPayload()
        return payload

    def getConfiguration(self) -> dict:
        return self.config

    def handleEvent(self, message, sender=None) -> None:
        pass


# ======================================================================================================================
# Context Menu
# ======================================================================================================================
@callback_definition
class ContextMenuItem_Callbacks:
    click: CallbackContainer


class ContextMenuItem:
    id: str

    parent: ContextMenuGroup | WidgetContextMenu | None = None

    # === INIT =========================================================================================================
    def __init__(self, id: str, **kwargs):
        self.id = id

        default_config = {
            'name': '',
            'text_color': [1, 1, 1, 0.8],
            'background_color': [0, 0, 0, 0],
            'font_weight': 'normal',
            'border': False,
            'border_color': [0.5, 0.5, 0.5],
            'front_icon': '',
            'back_icon': '',
        }

        self.config = update_dict(default_config, kwargs)
        self.callbacks = ContextMenuItem_Callbacks()

        if self.config['name'] == '':
            self.config['name'] = self.id

        self.logger = Logger(f"ContextMenuItem {self.id}", 'DEBUG')

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if self.parent:
            uid = f"{self.parent.uid}/{self.id}"
        else:
            uid = self.id
        return uid

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def name(self):
        return self.config['name']

    @name.setter
    def name(self, value):
        self.config['name'] = value
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def getContextMenu(self) -> WidgetContextMenu | None:
        if self.parent:
            if isinstance(self.parent, WidgetContextMenu):
                return self.parent
            else:
                return self.parent.getContextMenu()
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'item_id': self.uid,
            'type': 'item',
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'item_id': self.uid,
            'type': 'item',
            'config': self.getConfiguration(),
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:

        if message['data']['event'] == 'click':
            self.callbacks.click.call()
        else:
            self.logger.warning(f"ContextMenuItem {self.id} got an unhandled message: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, **kwargs):
        self.config.update(kwargs)

        menu = self.getContextMenu()
        if menu:
            menu.update()


# === CONTEXT MENU GROUP ===============================================================================================
class ContextMenuGroup:
    id: str
    items: dict[str, ContextMenuItem | ContextMenuGroup]
    type: str  # Can be 'inline' or 'open'

    parent: WidgetContextMenu | ContextMenuGroup | None = None

    # === INIT =========================================================================================================
    def __init__(self, id: str, type: str = 'inline', **kwargs):
        self.id = id

        default_config = {
            'background_color': 'inherit',
            'name': '',
            'text_color': [1, 1, 1, 0.8],
            'show_inline_title': True,
        }

        self.type = type
        self.config = update_dict(default_config, kwargs)

        if self.config['name'] == '':
            self.config['name'] = self.id

        self.items = {}

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        if self.parent:
            uid = f"{self.parent.uid}/{self.id}"
        else:
            uid = self.id
        return uid

    # ------------------------------------------------------------------------------------------------------------------
    def getContextMenu(self) -> WidgetContextMenu | None:
        if self.parent:
            if isinstance(self.parent, WidgetContextMenu):
                return self.parent
            else:
                return self.parent.getContextMenu()

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'item_id': self.uid,
            'type': self.type,
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def addItem(self, item: ContextMenuItem | ContextMenuGroup):
        if item.uid in self.items:
            raise ValueError(f"Item with id {item.uid} already exists")
        self.items[item.uid] = item
        item.parent = self

        menu = self.getContextMenu()
        if menu:
            menu.update()

    # ------------------------------------------------------------------------------------------------------------------
    def removeItem(self, item: ContextMenuItem | ContextMenuGroup | str):
        if isinstance(item, str):
            item = self.items[item]

        if not (isinstance(item, ContextMenuItem) or isinstance(item, ContextMenuGroup)):
            raise ValueError(f"Item {item} is not a ContextMenuItem or ContextMenuGroup")

        if item.id in self.items:
            self.items.pop(item.id)

        menu = self.getContextMenu()
        if menu:
            menu.update()

    # ------------------------------------------------------------------------------------------------------------------
    def getItemByID(self, item_id: str) -> ContextMenuItem | ContextMenuGroup | None:

        item_id, remainder = split_path(item_id)

        if not item_id in self.items:
            return None

        if not remainder:
            return self.items[item_id]
        else:
            return self.items[item_id].getItemByID(remainder)

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'item_id': self.uid,
            'type': 'group',
            'config': self.getConfiguration(),
            'items': {k: v.getPayload() for k, v in self.items.items()}
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, **kwargs):
        self.config.update(kwargs)
        menu = self.getContextMenu()
        if menu:
            menu.update()

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------


@callback_definition
class ContextMenuCallbacks:
    ...


class WidgetContextMenu:
    type: str = 'context_menu'
    id: str
    config: dict

    items: dict[str, ContextMenuItem | ContextMenuGroup]

    object: Widget

    # === INIT =========================================================================================================
    def __init__(self, id: str, object: Widget, **kwargs):
        self.id = id
        self.object = object

        default_config = {
            'background_color': [0.1, 0.1, 0.1, 0.9],
            'text_color': [1, 1, 1, 0.8],
        }

        self.config = update_dict(default_config, kwargs)
        self.logger = Logger(f"ContextMenu of {self.object.id}", 'DEBUG')

        self.items = {}

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def uid(self):
        return self.id

    # ------------------------------------------------------------------------------------------------------------------
    def addItem(self, item: ContextMenuItem | ContextMenuGroup):
        if item.id in self.items:
            raise ValueError(f"Item with id {item.id} already exists")
        item.parent = self
        self.items[item.id] = item

        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def removeItem(self, item: ContextMenuItem | ContextMenuGroup | str):

        # If item is a string, check if it is items
        if isinstance(item, str):
            print(self.items)
            if item in self.items:
                item = self.items[item]

        if not (isinstance(item, ContextMenuItem) or isinstance(item, ContextMenuGroup)):
            raise ValueError(f"Item {item} is not a ContextMenuItem or ContextMenuGroup")

        # Check if item is in this.items
        if item.id not in self.items:
            self.logger.error(f"Item {item.id} not found in this context menu")
            return

        # Remove item from this.items
        self.items.pop(item.id)

        self.update()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        if self.object:
            self.object.function(
                function_name='update_context_menu',
                args=self.getPayload()
            )

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        config = {
            'menu_id': self.uid,
            'type': 'context_menu',
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'menu_id': self.uid,
            'type': 'context_menu',
            'config': self.getConfiguration(),
            'items': {k: v.getPayload() for k, v in self.items.items()}
        }

        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def getItemByID(self, item_id: str) -> ContextMenuItem | ContextMenuGroup | None:

        menu_id, remainder = split_path(item_id)

        if menu_id != self.uid:
            self.logger.warning(f"Item {item_id} not found in this context menu")
            return None

        item_id, remainder = split_path(remainder)

        if not item_id in self.items:
            self.logger.warning(f"Item {item_id} not found in this context menu")
            return None

        if not remainder:
            return self.items[item_id]
        else:
            return self.items[item_id].getItemByID(remainder)

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        item_id = message['data']['item_id']

        item = self.getItemByID(item_id)
        if item:
            item.handleEvent(message)
        else:
            self.logger.warning(f"Item {item_id} not found in this context menu")
