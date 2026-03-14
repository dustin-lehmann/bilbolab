"""
Canonical Python model for experiment designer graph state.

This is the authoritative source of truth for the experiment graph.
Frontends send granular mutation events; this model applies them and
broadcasts to all connected views.
"""

import copy


class ExperimentGraph:
    def __init__(self):
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.meta: dict = {
            'id': 'experiment_1',
            'description': '',
            'timeout': None,
            'variables': {},
            'events': [],
        }
        self.node_counter: int = 0

    # ── Query ────────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> dict | None:
        for n in self.nodes:
            if n['id'] == node_id:
                return n
        return None

    def get_edge(self, edge_id: str) -> dict | None:
        for e in self.edges:
            if e['id'] == edge_id:
                return e
        return None

    def get_descendants(self, container_id: str) -> list[dict]:
        result = []
        children = [n for n in self.nodes if n.get('parentId') == container_id]
        for child in children:
            result.append(child)
            if child.get('width') is not None:
                result.extend(self.get_descendants(child['id']))
        return result

    # ── Mutation application ─────────────────────────────────────────────────

    def apply_mutation(self, mutation: dict) -> bool:
        """Apply an incoming mutation event. Returns True if applied."""
        mut_type = mutation.get('mutation')
        data = mutation.get('data', {})

        handler = getattr(self, f'_apply_{mut_type}', None)
        if handler is None:
            return False
        handler(data)
        return True

    def _apply_add_node(self, data):
        node = data.get('node')
        if node is None:
            return
        # Update node counter based on incoming node
        self._track_node_counter(node)
        # Prevent duplicates
        if self.get_node(node['id']) is None:
            self.nodes.append(copy.deepcopy(node))

    def _apply_remove_node(self, data):
        node_id = data.get('id')
        if node_id is None:
            return
        # Remove descendants first
        descendants = self.get_descendants(node_id)
        all_ids = {node_id} | {d['id'] for d in descendants}
        self.edges = [e for e in self.edges if e['from'] not in all_ids and e['to'] not in all_ids]
        self.nodes = [n for n in self.nodes if n['id'] not in all_ids]

    def _apply_move_nodes(self, data):
        positions = data.get('positions', {})
        for node_id, pos in positions.items():
            node = self.get_node(node_id)
            if node:
                node['x'] = pos['x']
                node['y'] = pos['y']

    def _apply_update_node_params(self, data):
        node = self.get_node(data.get('id'))
        if node:
            node['params'] = copy.deepcopy(data.get('params', {}))

    def _apply_update_node_field(self, data):
        node = self.get_node(data.get('id'))
        if node and 'field' in data:
            node[data['field']] = copy.deepcopy(data['value'])

    def _apply_rename_node(self, data):
        old_id = data.get('oldId')
        new_id = data.get('newId')
        if not old_id or not new_id:
            return
        node = self.get_node(old_id)
        if not node:
            return
        node['id'] = new_id
        # Update edges referencing this node
        for edge in self.edges:
            if edge['from'] == old_id:
                edge['from'] = new_id
            if edge['to'] == old_id:
                edge['to'] = new_id
            edge['id'] = f"edge_{edge['from']}_{edge['fromPort']}_{edge['to']}"
        # Update parentId references
        for n in self.nodes:
            if n.get('parentId') == old_id:
                n['parentId'] = new_id

    def _apply_move_node_to_container(self, data):
        node = self.get_node(data.get('id'))
        if node:
            node['parentId'] = data.get('containerId')

    def _apply_remove_node_from_container(self, data):
        node = self.get_node(data.get('id'))
        if node:
            node['parentId'] = None

    def _apply_add_edge(self, data):
        edge = data.get('edge')
        if edge is None:
            return
        if self.get_edge(edge['id']) is None:
            self.edges.append(copy.deepcopy(edge))

    def _apply_remove_edge(self, data):
        edge_id = data.get('id')
        if edge_id is not None:
            self.edges = [e for e in self.edges if e['id'] != edge_id]

    def _apply_update_edge_mapping(self, data):
        edge = self.get_edge(data.get('id'))
        if edge:
            edge['mapping'] = copy.deepcopy(data.get('mapping'))

    def _apply_update_meta(self, data):
        field = data.get('field')
        if field:
            self.meta[field] = copy.deepcopy(data.get('value'))

    def _apply_add_variable(self, data):
        name = data.get('name')
        if name is not None:
            self.meta.setdefault('variables', {})[name] = data.get('value')

    def _apply_remove_variable(self, data):
        name = data.get('name')
        if name is not None:
            self.meta.get('variables', {}).pop(name, None)

    def _apply_update_variable(self, data):
        name = data.get('name')
        if name is not None:
            self.meta.setdefault('variables', {})[name] = data.get('value')

    def _apply_add_event(self, data):
        name = data.get('name')
        if name and name not in self.meta.get('events', []):
            self.meta.setdefault('events', []).append(name)

    def _apply_remove_event(self, data):
        name = data.get('name')
        events = self.meta.get('events', [])
        if name in events:
            events.remove(name)

    def _apply_load_state(self, data):
        self.nodes = copy.deepcopy(data.get('nodes', []))
        self.edges = copy.deepcopy(data.get('edges', []))
        meta = data.get('meta')
        if meta:
            self.meta = copy.deepcopy(meta)
        if 'nodeCounter' in data:
            self.node_counter = data['nodeCounter']

    # ── Serialization ────────────────────────────────────────────────────────

    def serialize(self) -> dict:
        return {
            'nodes': copy.deepcopy(self.nodes),
            'edges': copy.deepcopy(self.edges),
            'meta': copy.deepcopy(self.meta),
            'nodeCounter': self.node_counter,
        }

    def load_state(self, nodes: list, edges: list, meta: dict, node_counter: int = 0):
        self.nodes = copy.deepcopy(nodes)
        self.edges = copy.deepcopy(edges)
        self.meta = copy.deepcopy(meta)
        self.node_counter = node_counter

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _track_node_counter(self, node: dict):
        """Keep node_counter at least as high as any numeric suffix in node IDs."""
        node_id = node.get('id', '')
        parts = node_id.rsplit('_', 1)
        if len(parts) == 2:
            try:
                num = int(parts[1])
                if num > self.node_counter:
                    self.node_counter = num
            except ValueError:
                pass
