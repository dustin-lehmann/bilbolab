<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  nodes: { type: Array, required: true },
  selectedPaths: { type: Set, required: true },
  depth: { type: Number, default: 0 },
})

const emit = defineEmits(['toggle', 'new-plot', 'context-menu'])

const expanded = ref(new Set())

// Auto-expand the first two levels
function isExpanded(path) {
  if (props.depth < 1) return true
  return expanded.value.has(path)
}

function toggleExpand(path) {
  if (expanded.value.has(path)) {
    expanded.value.delete(path)
  } else {
    expanded.value.add(path)
  }
}

function toggleField(path) {
  emit('toggle', path)
}

// ── Context menu ──────────────────────────────────────────────────────────────
const contextMenu = ref(null) // only used at depth 0

function collectLeafPaths(node) {
  if (!node.children) return [node.path]
  const paths = []
  for (const child of node.children) paths.push(...collectLeafPaths(child))
  return paths
}

function onContextMenu(e, node) {
  e.preventDefault()
  e.stopPropagation()
  const paths = collectLeafPaths(node)
  if (paths.length === 0) return
  const detail = { x: e.clientX, y: e.clientY, paths, label: node.label }
  if (props.depth === 0) {
    // Root instance — show menu directly
    contextMenu.value = detail
  } else {
    // Nested instance — bubble up to root
    emit('context-menu', detail)
  }
}

function onChildContextMenu(detail) {
  if (props.depth === 0) {
    contextMenu.value = detail
  } else {
    emit('context-menu', detail)
  }
}

function onNewPlot() {
  if (!contextMenu.value) return
  emit('new-plot', contextMenu.value.paths)
  contextMenu.value = null
}

function onDocClick() {
  contextMenu.value = null
}

onMounted(() => {
  if (props.depth === 0) document.addEventListener('click', onDocClick)
})
onUnmounted(() => {
  if (props.depth === 0) document.removeEventListener('click', onDocClick)
})
</script>

<template>
  <div class="field-tree" :style="{ paddingLeft: depth > 0 ? '12px' : '0' }">
    <div v-for="node in nodes" :key="node.path" class="tree-node">
      <!-- Branch node -->
      <div v-if="node.children" class="branch">
        <div class="branch-header" @click="toggleExpand(node.path)" @contextmenu="onContextMenu($event, node)">
          <span class="expand-icon">{{ isExpanded(node.path) ? '▾' : '▸' }}</span>
          <span class="branch-label">{{ node.label }}</span>
        </div>
        <FieldTree
          v-if="isExpanded(node.path)"
          :nodes="node.children"
          :selected-paths="selectedPaths"
          :depth="depth + 1"
          @toggle="(p) => emit('toggle', p)"
          @new-plot="(p) => emit('new-plot', p)"
          @context-menu="onChildContextMenu"
        />
      </div>

      <!-- Leaf node (numeric field) -->
      <div
        v-else
        class="leaf"
        :class="{ selected: selectedPaths.has(node.path) }"
        draggable="true"
        @click="toggleField(node.path)"
        @contextmenu="onContextMenu($event, node)"
        @dragstart="(e) => { e.dataTransfer.setData('text/field-path', node.path); e.dataTransfer.effectAllowed = 'copy' }"
      >
        <span class="leaf-check">{{ selectedPaths.has(node.path) ? '●' : '○' }}</span>
        <span class="leaf-label">{{ node.label }}</span>
      </div>
    </div>

    <!-- Context menu (only at root depth) -->
    <Teleport to="body">
      <div
        v-if="depth === 0 && contextMenu"
        class="field-context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <button class="ctx-item" @click="onNewPlot">
          New plot with <strong>{{ contextMenu.label }}</strong>
          <span v-if="contextMenu.paths.length > 1" class="ctx-count">({{ contextMenu.paths.length }} fields)</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.field-tree {
  font-size: 11px;
}

.tree-node + .tree-node { margin-top: 1px; }

.branch-header {
  display: flex;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  color: var(--text-dim);
  user-select: none;
}
.branch-header:hover { background: var(--bg-hover); color: var(--text); }

.expand-icon { font-size: 9px; width: 10px; text-align: center; flex-shrink: 0; }
.branch-label { font-weight: 500; }

.leaf {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 4px;
  border-radius: 3px;
  cursor: pointer;
  user-select: none;
}
.leaf:hover { background: var(--bg-hover); }
.leaf.selected { color: var(--accent); }

.leaf-check {
  font-size: 8px;
  width: 10px;
  text-align: center;
  flex-shrink: 0;
}

.leaf-label { font-size: 11px; }
</style>

<style>
/* Context menu — global (not scoped) since it's teleported to body */
.field-context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--bg-surface, #1e1e2e);
  border: 1px solid var(--border, #333);
  border-radius: 5px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.5);
  padding: 3px 0;
  min-width: 160px;
}

.ctx-item {
  font-family: inherit;
  font-size: 11px;
  width: 100%;
  padding: 5px 12px;
  border: none;
  background: transparent;
  color: var(--text, #ccc);
  cursor: pointer;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.ctx-item:hover { background: var(--bg-hover, #2a2a3e); }
.ctx-item strong { color: var(--accent, #7c6bff); font-weight: 600; }
.ctx-count { font-size: 9px; color: var(--text-dim, #888); }
</style>
