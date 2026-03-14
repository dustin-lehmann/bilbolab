import os, re

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dict_utils import update_dict
from core.utils.events import event_definition, Event
from core.utils.files import get_absolute_path
from core.utils.time import delayed_execution, Timer
from extensions.gui.src.lib.objects.objects import Widget


@callback_definition
class DirectoryWidgetCallbacks:
    selected: CallbackContainer
    unselected: CallbackContainer
    file_double_clicked: CallbackContainer


@event_definition
class DirectoryWidgetEvents:
    selected: Event
    unselected: Event
    double_clicked: Event


class DirectoryWidget(Widget):
    type = 'directory'
    callbacks: DirectoryWidgetCallbacks
    events: DirectoryWidgetEvents

    selected_file: str | None
    directory: str

    tree: dict
    included_extensions: list[str]
    excluded_extensions: list[str]
    excludes_regex: list[str]
    relative_path: bool = True
    exclude_hidden: bool = True

    refresh_interval: int = 3  # seconds

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, widget_id: str, directory=None, included_extensions=None, excluded_extensions=None,
                 config: dict = None, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'persistent_highlights': []
        }

        self.config = update_dict(default_config, kwargs)

        self.callbacks = DirectoryWidgetCallbacks()
        self.events = DirectoryWidgetEvents()
        self.selected_file = None
        self.tree = {}
        self.included_extensions = included_extensions if included_extensions else []
        self.excluded_extensions = excluded_extensions if excluded_extensions else []
        self.excludes_regex = []
        self.directory = directory

        if self.refresh_interval is not None and self.refresh_interval > 0:
            # Schedule the first update after the specified interval
            self.timer = Timer(timeout=self.refresh_interval,
                               callback=self.update,
                               repeat=True)
            self.timer.start()

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def directory(self):
        return self._directory

    # ------------------------------------------------------------------------------------------------------------------
    @directory.setter
    def directory(self, new_directory: str):
        self._directory = new_directory
        self.updateDirectory()

    # ------------------------------------------------------------------------------------------------------------------
    def updateDirectory(self):
        """
        Rebuild self.tree by walking self._directory (relative or absolute),
        excluding:
          - any files whose extension is in self.excluded_extensions,
          - any files whose extension is NOT in self.included_extensions when that list is non-empty,
          - any file/dir whose path matches any regex in self.excludes_regex,
          - or (if exclude_hidden) any path segments that start with a dot.
        """

        if not self._directory:
            self.tree = {}
            return

        # Determine the actual root path on disk
        root = (get_absolute_path(self._directory)
                if self.relative_path
                else self._directory)

        def is_excluded(rel_path: str, is_dir: bool) -> bool:
            # 0) hidden‐file/folder exclusion
            if self.exclude_hidden:
                # check every path segment for leading dot
                for part in rel_path.split(os.sep):
                    if part.startswith('.'):
                        return True

            # 1) regex‐based exclusions (files or dirs)
            for pattern in self.excludes_regex:
                if re.search(pattern, rel_path):
                    return True

            # 2) extension rules (only for files)
            if not is_dir:
                ext = os.path.splitext(rel_path)[1].lower().lstrip('.')

                # 2a) inclusion filter: if provided, only allow these extensions
                if self.included_extensions:
                    if not ext or ext not in (e.lower() for e in self.included_extensions):
                        return True

                # 2b) exclusion filter: always exclude listed extensions
                if ext and ext in (e.lower() for e in self.excluded_extensions):
                    return True

            return False

        def scan_dir(abs_path: str) -> dict:
            node = {'dirs': [], 'files': []}
            try:
                for entry in os.scandir(abs_path):
                    # skip hidden based on name
                    if self.exclude_hidden and entry.name.startswith('.'):
                        continue

                    # compute a path relative to the widget root if needed
                    rel = (os.path.relpath(entry.path, root)
                           if self.relative_path else entry.path)

                    if entry.is_dir(follow_symlinks=False):
                        if is_excluded(rel, is_dir=True):
                            continue
                        subtree = scan_dir(entry.path)
                        node['dirs'].append({
                            'name': entry.name,
                            'path': rel,
                            'type': None,
                            'dirs': subtree['dirs'],
                            'files': subtree['files']
                        })
                    elif entry.is_file(follow_symlinks=False):
                        if is_excluded(rel, is_dir=False):
                            continue
                        node['files'].append({
                            'name': entry.name,
                            'path': rel,
                            'type': None
                        })
            except PermissionError:
                # skip directories we can't read
                pass
            return node

        # actually build the tree
        self.tree = scan_dir(root)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        """
        Returns a dictionary describing this widget’s state for front-end rendering.
        """
        config = {
            'tree': self.tree,
            **self.config,
        }

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message: dict, sender=None) -> None:

        match message['event']:

            case 'directory_select':
                self.logger.debug(f"Selected Directory: {message['data']['path']}")
            case 'directory_double_click':
                self.logger.debug(f"Double-clicked Directory: {message['data']['path']}")
            case 'file_select':
                self.logger.debug(f"Selected File: {message['data']['path']}")
            case 'file_double_click':
                self.logger.debug(f"Double-clicked File: {message['data']['path']}")
                self.callbacks.file_double_clicked.call(file=message['data']['path'])
            case _:
                self.logger.warning(f"Unknown event message received: {message}")

    # ------------------------------------------------------------------------------------------------------------------
    def toggleHighlight(self, path: str):
        for persistent_highlight in self.config['persistent_highlights']:
            if persistent_highlight['path'] == path:
                self.config['persistent_highlights'].remove(persistent_highlight)
                self.updateConfig()
                return
        self.highlight(path)

    # ------------------------------------------------------------------------------------------------------------------
    def highlight(self, path: str, highlight: bool = True, color=None, ):

        # Check if the path is already highlighted
        for persistent_highlight in self.config['persistent_highlights']:
            if persistent_highlight['path'] == path:
                return

        if color is None:
            color = 'yellow'
        self.config['persistent_highlights'].append({'path': path, 'color': color})
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def removeAllHighlights(self):
        self.config['persistent_highlights'] = []
        self.updateConfig()

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        self.updateDirectory()
        self.sendUpdate(self.tree)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        if self.timer is not None:
            self.timer.stop()
