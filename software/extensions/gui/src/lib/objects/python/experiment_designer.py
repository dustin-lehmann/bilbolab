import enum
import json
import os
import re
import threading
import time as _time

from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.dict_utils import update_dict
from core.utils.logging_utils import Logger
from extensions.gui.src.lib.objects.objects import Widget, Widget_Callbacks
from extensions.gui.src.lib.objects.python.experiment_graph import ExperimentGraph

# Path to the experiment_designer public/templates directory
_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'experiment_designer', 'public', 'templates')
_TEMPLATES_DIR = os.path.normpath(_TEMPLATES_DIR)

_logger = Logger('TemplateManager')


def _rebuild_robot_manifest(robot_id: str) -> dict:
    """Scan the robot template directory and rebuild manifest.json."""
    robot_dir = os.path.join(_TEMPLATES_DIR, robot_id)
    if not os.path.isdir(robot_dir):
        return {}

    folders = {}
    for folder_name in sorted(os.listdir(robot_dir)):
        folder_path = os.path.join(robot_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
        templates = []
        for fname in sorted(os.listdir(folder_path)):
            if not fname.endswith(('.yaml', '.yml')):
                continue
            file_path = os.path.join(folder_path, fname)
            template_id = fname.rsplit('.', 1)[0]
            # Try to extract description from YAML front matter
            description = ''
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('description:'):
                            description = line.split(':', 1)[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass
            label = template_id.replace('_', ' ').title()
            # Try to extract label from id field
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('id:'):
                            raw_id = line.split(':', 1)[1].strip().strip('"').strip("'")
                            label = raw_id.replace('_', ' ').title()
                            break
            except Exception:
                pass
            templates.append({
                'id': template_id,
                'label': label,
                'file': f'{robot_id}/{folder_name}/{fname}',
                'description': description,
            })
        folders[folder_name] = {
            'label': folder_name.replace('_', ' ').title(),
            'templates': templates,
        }

    manifest = {robot_id: {'label': robot_id.upper(), 'folders': folders}}

    manifest_path = os.path.join(robot_dir, 'manifest.json')
    try:
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        _logger.debug(f"Rebuilt manifest for '{robot_id}'")
    except Exception as e:
        _logger.error(f"Failed to write manifest: {e}")

    return manifest


class ActionLibrary(enum.Enum):
    BILBO = 'bilbo'

_ITER_RE = re.compile(r'^(.+?)_iter(\d+)$')


@callback_definition
class ExperimentDesignerCallbacks(Widget_Callbacks):
    play: CallbackContainer
    stop: CallbackContainer


class ExperimentDesignerWidget(Widget):
    type = 'experiment_designer'

    callbacks: ExperimentDesignerCallbacks

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, on_play=None, on_stop=None, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'dark_mode': True,
            'show_toolbar': True,
            'show_yaml_preview': False,
            'show_experiment_tabs': False,
            'read_only': False,
            'action_library': None,
            'transparent': False,
        }

        self.config = update_dict(default_config, kwargs)
        self.callbacks = ExperimentDesignerCallbacks()

        # Canonical graph model (source of truth)
        self._graph = ExperimentGraph()

        # File tracking for delegated file operations
        self._current_file_path = None

        # Runner connection state
        self._runner = None
        self._runner_action_ids = set()

        if on_play is not None:
            self.callbacks.play.register(on_play)
        if on_stop is not None:
            self.callbacks.stop.register(on_stop)

    # === GRAPH ACCESS =================================================================================================
    @property
    def graph(self) -> ExperimentGraph:
        return self._graph

    # === METHODS ======================================================================================================
    def getConfiguration(self) -> dict:
        config = {**self.config}
        if isinstance(config.get('action_library'), ActionLibrary):
            config['action_library'] = config['action_library'].value
        state = self._graph.serialize()
        if state['nodes']:
            config['full_state'] = state
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        event = message.get('event')
        data = message.get('data', {})

        if event == 'play':
            yaml = data.get('yaml', '')
            for callback in self.callbacks.play:
                callback(widget=self, yaml=yaml)
        elif event == 'stop':
            for callback in self.callbacks.stop:
                callback(widget=self)
        elif event == 'mutation':
            # Apply mutation to canonical model, then broadcast to all frontends
            self._graph.apply_mutation(data)
            self.sendUpdate({'mutation': data}, important=True)
        elif event == 'state_changed':
            # Legacy fallback: full state dump from frontend (e.g. beforeunload)
            state = data.get('state')
            if state:
                try:
                    parsed = json.loads(state) if isinstance(state, str) else state
                    self._graph.load_state(
                        nodes=parsed.get('nodes', []),
                        edges=parsed.get('edges', []),
                        meta=parsed.get('meta', {}),
                        node_counter=parsed.get('nodeCounter', 0),
                    )
                except Exception:
                    pass

        # ── Delegated file operations ──────────────────────────────────────
        elif event == 'file_open':
            threading.Thread(target=self._handle_file_open, daemon=True).start()
        elif event == 'file_save':
            threading.Thread(target=self._handle_file_save, args=(data,), daemon=True).start()
        elif event == 'file_save_as':
            threading.Thread(target=self._handle_file_save_as, args=(data,), daemon=True).start()

        # ── Template management events ──────────────────────────────────────
        elif event == 'save_template':
            self._handle_save_template(data)
        elif event == 'delete_template':
            self._handle_delete_template(data)
        elif event == 'rename_template':
            self._handle_rename_template(data)
        elif event == 'create_folder':
            self._handle_create_folder(data)
        elif event == 'delete_folder':
            self._handle_delete_folder(data)
        elif event == 'rename_folder':
            self._handle_rename_folder(data)

    # === PYTHON EDITING API ===========================================================================================

    def add_node(self, node_type: str, x: float = 0, y: float = 0,
                 node_id: str | None = None, parent_id: str | None = None, **params) -> str:
        """Add a node programmatically. Returns the node ID."""
        if node_id is None:
            self._graph.node_counter += 1
            node_id = f'{node_type}_{self._graph.node_counter}'

        node = {
            'id': node_id,
            'type': node_type,
            'x': x,
            'y': y,
            'parentId': parent_id,
            'params': params if params else {},
        }

        mutation = {'mutation': 'add_node', 'data': {'node': node}, 'source': '__python__'}
        self._graph.apply_mutation(mutation)
        self.sendUpdate({'mutation': mutation}, important=True)
        return node_id

    # ------------------------------------------------------------------------------------------------------------------
    def remove_node(self, node_id: str):
        """Remove a node programmatically."""
        mutation = {'mutation': 'remove_node', 'data': {'id': node_id}, 'source': '__python__'}
        self._graph.apply_mutation(mutation)
        self.sendUpdate({'mutation': mutation}, important=True)

    # ------------------------------------------------------------------------------------------------------------------
    def update_node_params(self, node_id: str, **params):
        """Update parameters of a node."""
        mutation = {'mutation': 'update_node_params', 'data': {'id': node_id, 'params': params}, 'source': '__python__'}
        self._graph.apply_mutation(mutation)
        self.sendUpdate({'mutation': mutation}, important=True)

    # ------------------------------------------------------------------------------------------------------------------
    def add_edge(self, from_id: str, from_port: str, to_id: str) -> str:
        """Add an edge. Returns the edge ID."""
        edge_id = f'edge_{from_id}_{from_port}_{to_id}'
        edge = {'id': edge_id, 'from': from_id, 'fromPort': from_port, 'to': to_id, 'mapping': None}
        mutation = {'mutation': 'add_edge', 'data': {'edge': edge}, 'source': '__python__'}
        self._graph.apply_mutation(mutation)
        self.sendUpdate({'mutation': mutation}, important=True)
        return edge_id

    # ------------------------------------------------------------------------------------------------------------------
    def remove_edge(self, edge_id: str):
        """Remove an edge."""
        mutation = {'mutation': 'remove_edge', 'data': {'id': edge_id}, 'source': '__python__'}
        self._graph.apply_mutation(mutation)
        self.sendUpdate({'mutation': mutation}, important=True)

    # ------------------------------------------------------------------------------------------------------------------
    def set_variable(self, name: str, value):
        """Set an experiment variable."""
        existing = self._graph.meta.get('variables', {})
        mut_type = 'update_variable' if name in existing else 'add_variable'
        mutation = {'mutation': mut_type, 'data': {'name': name, 'value': value}, 'source': '__python__'}
        self._graph.apply_mutation(mutation)
        self.sendUpdate({'mutation': mutation}, important=True)

    # ------------------------------------------------------------------------------------------------------------------
    def set_meta(self, field: str, value):
        """Set an experiment metadata field (id, description, timeout)."""
        mutation = {'mutation': 'update_meta', 'data': {'field': field, 'value': value}, 'source': '__python__'}
        self._graph.apply_mutation(mutation)
        self.sendUpdate({'mutation': mutation}, important=True)

    # ------------------------------------------------------------------------------------------------------------------
    def load_experiment(self, yaml_string: str):
        """Load an experiment YAML into the designer.

        Parses the YAML, updates the canonical model, and broadcasts to all frontends.
        """
        self.function('loadExperiment', [yaml_string])

    # ------------------------------------------------------------------------------------------------------------------
    def get_graph_state(self) -> dict:
        """Get the current graph state as a serializable dict."""
        return self._graph.serialize()

    # ------------------------------------------------------------------------------------------------------------------
    def set_mode(self, mode: str):
        """Switch between 'edit' and 'playback' mode."""
        self.function('setMode', [mode])
        if mode == 'edit':
            self.function('clearActionStates', [])

    # ------------------------------------------------------------------------------------------------------------------
    def set_action_state(self, action_id: str, state: str):
        """Set the visual state of a single action node.

        States: 'normal', 'active', 'highlighted', 'dimmed', 'completed', 'error'
        """
        self.function('setActionState', [action_id, state])

    # ------------------------------------------------------------------------------------------------------------------
    def set_action_states(self, states: dict):
        """Bulk-set visual states for multiple action nodes."""
        self.function('setActionStates', [states])

    # ------------------------------------------------------------------------------------------------------------------
    def clear_action_states(self):
        """Reset all action node visual states to normal."""
        self.function('clearActionStates', [])

    # === RUNNER CONNECTION =============================================================================

    def run(self, runner_or_experiment):
        """Attach a running experiment for playback tracking.

        Accepts an ExperimentRunner or an Experiment wrapper. The widget enters
        playback mode, dims all actions, and tracks progress via the runner's
        events. The caller is responsible for driving the step loop.

        The experiment YAML should already be loaded in the frontend (via
        load_experiment() or designed by the user). This method does NOT
        reload the graph — it only attaches the runner for state tracking.
        """
        # Accept Experiment wrapper — unwrap to get the runner
        runner = getattr(runner_or_experiment, 'runner', runner_or_experiment)
        self.connect_runner(runner)

    # ------------------------------------------------------------------------------------------------------------------
    def connect_runner(self, runner):
        """Connect an ExperimentRunner for automatic playback state tracking.

        Registers directly on the runner's event callbacks (synchronous, inline)
        so that even instant actions (like log) are correctly tracked as 'active'
        before they complete.

        Args:
            runner: An ExperimentRunner instance (initialized or not yet initialized).
        """
        # Disconnect any previous runner
        if self._runner is not None:
            self.disconnect_runner()

        self._runner = runner

        # Collect all action IDs recursively from the definition
        self._runner_action_ids = set(self._collect_definition_ids(runner.definition.actions))

        # Enter playback mode and dim all actions
        self.set_mode('playback')
        self.set_action_states({aid: 'dimmed' for aid in self._runner_action_ids})

        # Register directly on event callbacks (synchronous — fires inline during event.set())
        runner.events.action_started.callbacks.set.register(self._on_runner_action_started)
        runner.events.action_finished.callbacks.set.register(self._on_runner_action_finished)
        runner.events.finished.callbacks.set.register(self._on_runner_finished)

        # Sync any actions that started or finished before we registered callbacks
        # (e.g. when runner.initialize() was called before widget.run())
        from core.utils.experiments import ActionStatus
        for action_id, instance in runner.action_instances.items():
            if instance.status in (ActionStatus.RUNNING, ActionStatus.COMPLETED, ActionStatus.ERROR):
                base_id = self._resolve_base_id(action_id)
                if base_id:
                    self.set_action_state(base_id, self._status_to_state(instance.status))

    # ------------------------------------------------------------------------------------------------------------------
    def disconnect_runner(self):
        """Disconnect the experiment runner and return to edit mode."""
        runner = self._runner
        if runner is not None:
            runner.events.action_started.callbacks.set.remove(self._on_runner_action_started)
            runner.events.action_finished.callbacks.set.remove(self._on_runner_action_finished)
            runner.events.finished.callbacks.set.remove(self._on_runner_finished)
        self._runner = None
        self._runner_action_ids = set()
        self.clear_action_states()
        if not self.config.get('read_only'):
            self.set_mode('edit')

    # ------------------------------------------------------------------------------------------------------------------
    def _resolve_base_id(self, action_id):
        """Map a runner action ID (possibly a loop iteration like 'x_iter0') to a designer node ID."""
        if action_id in self._runner_action_ids:
            return action_id
        m = _ITER_RE.match(action_id)
        if m:
            base_id = m.group(1)
            if base_id in self._runner_action_ids:
                return base_id
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_runner_action_started(self, data=None, flags=None, **kwargs):
        """Called synchronously when an action starts — set it to 'active'."""
        action_id = flags.get('id') if flags else None
        if not action_id:
            return
        base_id = self._resolve_base_id(action_id)
        if base_id:
            self.set_action_state(base_id, 'active')

    # ------------------------------------------------------------------------------------------------------------------
    def _on_runner_action_finished(self, data=None, flags=None, **kwargs):
        """Called synchronously when an action finishes — set it to 'completed'."""
        action_id = flags.get('id') if flags else None
        if not action_id:
            return
        base_id = self._resolve_base_id(action_id)
        if base_id:
            instance = self._runner.action_instances.get(action_id) if self._runner else None
            state = self._status_to_state(instance.status) if instance else 'completed'
            self.set_action_state(base_id, state)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_runner_finished(self, data=None, **kwargs):
        """Called when the experiment finishes."""
        action_ids = list(self._runner_action_ids)
        if action_ids:
            self.set_action_states({a: 'completed' for a in action_ids})

        def _cleanup():
            _time.sleep(1.0)
            self.disconnect_runner()
        threading.Thread(target=_cleanup, daemon=True).start()

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _collect_definition_ids(actions):
        """Recursively collect action IDs from ActionDefinition list."""
        ids = []
        for action in actions:
            if action.id:
                ids.append(action.id)
            if action.sub_actions:
                ids.extend(ExperimentDesignerWidget._collect_definition_ids(action.sub_actions))
            if action.then_actions:
                ids.extend(ExperimentDesignerWidget._collect_definition_ids(action.then_actions))
            if action.else_actions:
                ids.extend(ExperimentDesignerWidget._collect_definition_ids(action.else_actions))
        return ids

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _status_to_state(status):
        """Map ActionStatus to designer widget visual state string."""
        from core.utils.experiments import ActionStatus
        if status == ActionStatus.RUNNING:
            return 'active'
        if status == ActionStatus.COMPLETED:
            return 'completed'
        if status == ActionStatus.ERROR:
            return 'error'
        return 'dimmed'

    # === FILE OPERATIONS (delegated from frontend) ======================================================================

    @property
    def current_file_path(self) -> str | None:
        """The absolute path of the currently open experiment file, or None."""
        return self._current_file_path

    def _handle_file_open(self):
        """Open a native file picker and send the content back to the frontend."""
        from core.utils.filepicker import pick_file

        initial_dir = os.path.dirname(self._current_file_path) if self._current_file_path else None
        path = pick_file(
            title="Open Experiment",
            initial_dir=initial_dir,
            allowed_extensions=['.yaml', '.yml'],
        )
        if path is None:
            return

        try:
            with open(path, 'r') as f:
                yaml_content = f.read()
        except Exception as e:
            self.logger.error(f"Failed to read file: {e}")
            return

        self._current_file_path = os.path.abspath(path)
        filename = os.path.basename(path)
        self.sendUpdate({'file_content': {'yaml': yaml_content, 'filename': filename}})

    def _handle_file_save(self, data: dict):
        """Write YAML to the tracked file path, or fall back to save-as."""
        yaml_content = data.get('yaml', '')

        # Safety: refuse to overwrite an existing file with empty/trivial content.
        # This prevents data loss when the widget is recreated with stale tab state.
        if self._current_file_path and os.path.isfile(self._current_file_path):
            stripped = yaml_content.strip()
            if not stripped or 'actions:' not in stripped:
                self.logger.warning(
                    f"Refusing to save empty experiment to '{self._current_file_path}' — "
                    f"content has no actions. Use Save As to explicitly create a new file."
                )
                return

        if not self._current_file_path:
            self._handle_file_save_as(data)
            return

        try:
            with open(self._current_file_path, 'w') as f:
                f.write(yaml_content)
        except Exception as e:
            self.logger.error(f"Failed to save file: {e}")
            return

        filename = os.path.basename(self._current_file_path)
        self.sendUpdate({'file_saved': {'filename': filename}})

    def _handle_file_save_as(self, data: dict):
        """Open a native save dialog and write the YAML."""
        from core.utils.filepicker import save_file

        yaml_content = data.get('yaml', '')
        suggested_name = data.get('suggestedName', 'experiment.yaml')
        initial_dir = os.path.dirname(self._current_file_path) if self._current_file_path else None

        path = save_file(
            title="Save Experiment",
            initial_dir=initial_dir,
            suggested_name=suggested_name,
            allowed_extensions=['.yaml', '.yml'],
        )
        if path is None:
            return

        # Ensure .yaml extension
        if not path.endswith(('.yaml', '.yml')):
            path += '.yaml'

        try:
            with open(path, 'w') as f:
                f.write(yaml_content)
        except Exception as e:
            self.logger.error(f"Failed to save file: {e}")
            return

        self._current_file_path = os.path.abspath(path)
        filename = os.path.basename(path)
        self.sendUpdate({'file_saved': {'filename': filename}})

    # === TEMPLATE MANAGEMENT ==========================================================================================

    def _get_robot_id(self):
        """Get the configured robot ID for templates."""
        lib = self.config.get('action_library')
        if isinstance(lib, ActionLibrary):
            return lib.value
        return lib or 'bilbo'

    def _send_manifest_update(self, robot_id: str):
        """Rebuild manifest and push to all connected frontends."""
        manifest = _rebuild_robot_manifest(robot_id)
        self.function('updateTemplates', [manifest])

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_save_template(self, data: dict):
        """Save YAML as a template. data: {robot_id, folder, id, yaml, description?}"""
        robot_id = data.get('robot_id', self._get_robot_id())
        folder = data.get('folder', '').strip()
        template_id = data.get('id', '').strip()
        yaml_content = data.get('yaml', '')
        description = data.get('description', '').strip()

        if not folder or not template_id or not yaml_content:
            self.logger.warning("save_template: missing folder, id, or yaml")
            return

        # Replace or insert the experiment id in the YAML to match the template id
        yaml_content = re.sub(
            r'^id:\s*.*$', f'id: {template_id}', yaml_content, count=1, flags=re.MULTILINE
        )
        if not re.search(r'^id:', yaml_content, re.MULTILINE):
            yaml_content = f'id: {template_id}\n' + yaml_content

        # Replace or insert description if provided
        if description:
            if re.search(r'^description:\s*', yaml_content, re.MULTILINE):
                yaml_content = re.sub(
                    r'^description:\s*.*$', f'description: {description}', yaml_content, count=1, flags=re.MULTILINE
                )
            else:
                # Insert after id line
                yaml_content = re.sub(
                    r'^(id:\s*.*)$', rf'\1\ndescription: {description}', yaml_content, count=1, flags=re.MULTILINE
                )

        folder_path = os.path.join(_TEMPLATES_DIR, robot_id, folder)
        os.makedirs(folder_path, exist_ok=True)

        file_path = os.path.join(folder_path, f'{template_id}.yaml')
        try:
            with open(file_path, 'w') as f:
                f.write(yaml_content)
            _logger.info(f"Saved template '{template_id}' to {folder}/")
        except Exception as e:
            _logger.error(f"Failed to save template: {e}")
            return

        self._send_manifest_update(robot_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_delete_template(self, data: dict):
        """Delete a template. data: {robot_id, folder, id}"""
        robot_id = data.get('robot_id', self._get_robot_id())
        folder = data.get('folder')
        template_id = data.get('id')

        if not folder or not template_id:
            return

        file_path = os.path.join(_TEMPLATES_DIR, robot_id, folder, f'{template_id}.yaml')
        if not os.path.isfile(file_path):
            file_path = os.path.join(_TEMPLATES_DIR, robot_id, folder, f'{template_id}.yml')

        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                _logger.info(f"Deleted template '{template_id}' from {folder}/")
        except Exception as e:
            _logger.error(f"Failed to delete template: {e}")
            return

        self._send_manifest_update(robot_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_rename_template(self, data: dict):
        """Rename a template. data: {robot_id, folder, old_id, new_id}"""
        robot_id = data.get('robot_id', self._get_robot_id())
        folder = data.get('folder')
        old_id = data.get('old_id')
        new_id = data.get('new_id', '').strip()

        if not folder or not old_id or not new_id:
            return

        old_path = os.path.join(_TEMPLATES_DIR, robot_id, folder, f'{old_id}.yaml')
        new_path = os.path.join(_TEMPLATES_DIR, robot_id, folder, f'{new_id}.yaml')

        try:
            if os.path.isfile(old_path):
                os.rename(old_path, new_path)
                _logger.info(f"Renamed template '{old_id}' → '{new_id}'")
        except Exception as e:
            _logger.error(f"Failed to rename template: {e}")
            return

        self._send_manifest_update(robot_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_create_folder(self, data: dict):
        """Create a template folder. data: {robot_id, folder}"""
        robot_id = data.get('robot_id', self._get_robot_id())
        folder = data.get('folder', '').strip()

        if not folder:
            return

        folder_path = os.path.join(_TEMPLATES_DIR, robot_id, folder)
        os.makedirs(folder_path, exist_ok=True)
        _logger.info(f"Created template folder '{folder}'")
        self._send_manifest_update(robot_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_delete_folder(self, data: dict):
        """Delete a template folder and all its contents. data: {robot_id, folder}"""
        robot_id = data.get('robot_id', self._get_robot_id())
        folder = data.get('folder')

        if not folder:
            return

        folder_path = os.path.join(_TEMPLATES_DIR, robot_id, folder)
        if not os.path.isdir(folder_path):
            return

        try:
            import shutil
            shutil.rmtree(folder_path)
            _logger.info(f"Deleted template folder '{folder}' and all contents")
        except Exception as e:
            _logger.error(f"Failed to delete folder: {e}")
            return

        self._send_manifest_update(robot_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_rename_folder(self, data: dict):
        """Rename a template folder. data: {robot_id, old_name, new_name}"""
        robot_id = data.get('robot_id', self._get_robot_id())
        old_name = data.get('old_name')
        new_name = data.get('new_name', '').strip()

        if not old_name or not new_name:
            return

        old_path = os.path.join(_TEMPLATES_DIR, robot_id, old_name)
        new_path = os.path.join(_TEMPLATES_DIR, robot_id, new_name)

        try:
            if os.path.isdir(old_path):
                os.rename(old_path, new_path)
                _logger.info(f"Renamed template folder '{old_name}' → '{new_name}'")
        except Exception as e:
            _logger.error(f"Failed to rename folder: {e}")
            return

        self._send_manifest_update(robot_id)
