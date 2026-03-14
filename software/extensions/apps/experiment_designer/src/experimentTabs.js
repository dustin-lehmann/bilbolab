/**
 * Multi-experiment tab management.
 *
 * Each tab stores a serialized snapshot of the full graph state.
 * Tab switching saves the current state and restores the target.
 * The existing module-level graphState refs remain the "active" state —
 * components don't need changes.
 *
 * Each tab also caches containerTabs/activeContainerTab so the unified
 * tab bar can display container tabs for inactive experiments.
 */
import { ref, computed, watch } from 'vue'
import {
  serializeFullState, loadFullState, initDefaultGraph,
  openTabs, activeTab, closeContainerTab, switchTab, meta, nodes, edges,
  snapshot, autoLayoutAll,
} from './graphState.js'
import { fromYaml } from './serializer.js'
import { openDB, idbGetAll, idbClear, idbPut } from './recentFiles.js'

const TABS_STORAGE_KEY = 'experiment-designer-tabs'
const TAB_HANDLES_STORE = 'tab-handles'

let tabIdCounter = 0

// ── Tab state ──────────────────────────────────────────────────────────────
// Each tab: { id, label, stateSnapshot, dirty, containerTabs, activeContainerTab }
export const experimentTabs = ref([])
export const activeExperimentTabId = ref(null)

// ── File handle storage (not serializable, kept separate) ────────────────
// Maps tab id → FileSystemFileHandle (from File System Access API)
const fileHandles = new Map()

/** Get the file handle for the current tab (or null). */
export function getCurrentFileHandle() {
  return fileHandles.get(activeExperimentTabId.value) || null
}

/** Set the file handle for the current tab. Also stores the filename. */
export function setCurrentFileHandle(handle) {
  if (activeExperimentTabId.value) {
    fileHandles.set(activeExperimentTabId.value, handle)
    if (handle?.name) {
      const tab = experimentTabs.value.find(t => t.id === activeExperimentTabId.value)
      if (tab) tab.fileName = handle.name
    }
  }
}

/** Set just the filename for the current tab (when no file handle is available). */
export function setCurrentFileName(name) {
  if (activeExperimentTabId.value && name) {
    const tab = experimentTabs.value.find(t => t.id === activeExperimentTabId.value)
    if (tab) tab.fileName = name
  }
}

/** Get the filename for the current tab (from handle or manually set). */
export function getCurrentFileName() {
  const handle = getCurrentFileHandle()
  if (handle?.name) return handle.name
  const tab = experimentTabs.value.find(t => t.id === activeExperimentTabId.value)
  return tab?.fileName || null
}

/**
 * Check if a file handle is already open in a tab.
 * If found, switches to that tab and returns true.
 * Uses isSameEntry() for reliable comparison.
 */
export async function switchToExistingFile(handle) {
  if (!handle || !handle.isSameEntry) return false
  for (const [tabId, existing] of fileHandles.entries()) {
    try {
      if (await handle.isSameEntry(existing)) {
        switchExperimentTab(tabId)
        return true
      }
    } catch { /* ignore comparison errors */ }
  }
  return false
}

// ── Functions ──────────────────────────────────────────────────────────────

/**
 * Initialize the tab system. Call once on mount after loadState/initDefaultGraph.
 * Creates the first tab from the current graph state.
 */
export function initTabs() {
  if (experimentTabs.value.length > 0) return
  tabIdCounter++
  const tab = {
    id: `tab_${tabIdCounter}`,
    label: 'Experiment 1',
    stateSnapshot: serializeFullState(),
    dirty: false,
    containerTabs: [...openTabs.value],
    activeContainerTab: activeTab.value,
  }
  experimentTabs.value = [tab]
  activeExperimentTabId.value = tab.id
}

/**
 * Open a template as a new experiment tab.
 * Parses the YAML, creates a new tab, loads the parsed graph into it.
 */
export function openTemplateTab(yamlString, templateLabel) {
  // Save current tab's state first
  saveCurrentTab()

  // Parse the template YAML into graph state
  let result
  try {
    result = fromYaml(yamlString)
  } catch (e) {
    alert('Failed to parse template: ' + e.message)
    return
  }

  // Load the parsed state into the live graph (suppress dirty marking)
  withSuppressedDirty(() => {
    snapshot()
    nodes.value = result.nodes
    edges.value = result.edges
    Object.assign(meta, result.meta)
    // Restore container tabs (may have been cleared if no experiments were open)
    openTabs.value = [{ id: 'root', label: 'Experiment' }]
    activeTab.value = 'root'
    autoLayoutAll()

    tabIdCounter++
    const tab = {
      id: `tab_${tabIdCounter}`,
      label: templateLabel || meta.id || `Experiment ${tabIdCounter}`,
      stateSnapshot: serializeFullState(),
      dirty: false,
      containerTabs: [{ id: 'root', label: 'Experiment' }],
      activeContainerTab: 'root',
    }
    experimentTabs.value = [...experimentTabs.value, tab]
    activeExperimentTabId.value = tab.id
  })
}

/**
 * Create a new blank experiment tab and switch to it.
 */
export function newExperimentTab() {
  saveCurrentTab()

  withSuppressedDirty(() => {
    initDefaultGraph()
    const nextNum = getNextExperimentNumber()
    meta.id = `experiment_${nextNum}`

    tabIdCounter++
    const tab = {
      id: `tab_${tabIdCounter}`,
      label: `Experiment ${tabIdCounter}`,
      stateSnapshot: serializeFullState(),
      dirty: false,
      containerTabs: [{ id: 'root', label: 'Experiment' }],
      activeContainerTab: 'root',
    }
    experimentTabs.value = [...experimentTabs.value, tab]
    activeExperimentTabId.value = tab.id
  })
}

/**
 * Switch to a different experiment tab.
 */
export function switchExperimentTab(tabId) {
  if (tabId === activeExperimentTabId.value) return
  const target = experimentTabs.value.find(t => t.id === tabId)
  if (!target) return

  saveCurrentTab()

  withSuppressedDirty(() => {
    loadFullState(target.stateSnapshot)
    if (target.containerTabs) {
      openTabs.value = [...target.containerTabs]
      activeTab.value = target.activeContainerTab || 'root'
    }
    activeExperimentTabId.value = tabId
  })
}

/**
 * Close an experiment tab. Prompts if dirty (and non-empty).
 * Allows closing the last tab — results in an empty state.
 */
export function closeExperimentTab(tabId) {
  const tab = experimentTabs.value.find(t => t.id === tabId)
  if (!tab) return

  if (tab.dirty) {
    if (!confirm(`"${tab.label}" has unsaved changes. Close anyway?`)) return
  }

  const idx = experimentTabs.value.findIndex(t => t.id === tabId)
  experimentTabs.value = experimentTabs.value.filter(t => t.id !== tabId)
  fileHandles.delete(tabId)

  if (activeExperimentTabId.value === tabId) {
    withSuppressedDirty(() => {
      if (experimentTabs.value.length === 0) {
        // Last tab closed — clear to empty state
        activeExperimentTabId.value = null
        nodes.value = []
        edges.value = []
        meta.id = ''
        meta.description = ''
        meta.timeout = null
        meta.variables = {}
        meta.events = []
        openTabs.value = []
        activeTab.value = 'root'
        localStorage.removeItem(TABS_STORAGE_KEY)
      } else {
        // Switch to an adjacent tab
        const newIdx = Math.min(idx, experimentTabs.value.length - 1)
        const newTab = experimentTabs.value[newIdx]
        loadFullState(newTab.stateSnapshot)
        if (newTab.containerTabs) {
          openTabs.value = [...newTab.containerTabs]
          activeTab.value = newTab.activeContainerTab || 'root'
        }
        activeExperimentTabId.value = newTab.id
      }
    })
  }
}

/** Whether any experiment tab is open. */
export const hasOpenExperiment = computed(() => experimentTabs.value.length > 0)

// Suppresses dirty marking during tab loads/switches
let suppressDirty = false

/** Temporarily suppress dirty marking (e.g. during file open / tab switch). */
export function withSuppressedDirty(fn) {
  suppressDirty = true
  try { fn() } finally {
    // Release on next tick so the deep watcher doesn't re-dirty
    setTimeout(() => { suppressDirty = false }, 0)
  }
}

/**
 * Mark the current tab as dirty (unsaved changes).
 * Skips marking if the graph only contains start and stop nodes (empty experiment).
 */
export function markCurrentTabDirty() {
  if (suppressDirty) return
  const tab = experimentTabs.value.find(t => t.id === activeExperimentTabId.value)
  if (!tab) return
  const real = nodes.value.filter(n => n.type !== '__start__' && n.type !== '__stop__')
  if (real.length === 0 && !tab.fileName) return
  tab.dirty = true
}

/**
 * Mark the current tab as clean (saved).
 */
export function markCurrentTabClean() {
  const tab = experimentTabs.value.find(t => t.id === activeExperimentTabId.value)
  if (tab) {
    tab.dirty = false
    tab.fileNotFound = false
  }
}

/**
 * Rename the current tab.
 */
export function renameExperimentTab(tabId, newLabel) {
  const tab = experimentTabs.value.find(t => t.id === tabId)
  if (tab) tab.label = newLabel
}

// ── Unified tab bar support ──────────────────────────────────────────────

/**
 * Switch to a specific container tab within an experiment.
 * If the experiment is not active, switch to it first.
 */
export function switchToExperimentContainer(expTabId, containerTabId) {
  if (expTabId !== activeExperimentTabId.value) {
    switchExperimentTab(expTabId)
  }
  switchTab(containerTabId)

  // Also update the cache for the now-active experiment
  const tab = experimentTabs.value.find(t => t.id === expTabId)
  if (tab) {
    tab.containerTabs = [...openTabs.value]
    tab.activeContainerTab = containerTabId
  }
}

/**
 * Close a container tab for any experiment (active or inactive).
 */
export function closeContainerTabForExperiment(expTabId, containerTabId) {
  if (containerTabId === 'root') return

  const tab = experimentTabs.value.find(t => t.id === expTabId)
  if (!tab) return

  if (expTabId === activeExperimentTabId.value) {
    // Active experiment: delegate to graphState + update cache
    closeContainerTab(containerTabId)
    tab.containerTabs = [...openTabs.value]
    tab.activeContainerTab = activeTab.value
  } else {
    // Inactive experiment: modify cache + patch stateSnapshot JSON
    tab.containerTabs = tab.containerTabs.filter(t => t.id !== containerTabId)
    if (tab.activeContainerTab === containerTabId) {
      tab.activeContainerTab = 'root'
    }
    // Patch the stateSnapshot so switching to this experiment is consistent
    try {
      const state = JSON.parse(tab.stateSnapshot)
      state.openTabs = tab.containerTabs
      state.activeTab = tab.activeContainerTab
      tab.stateSnapshot = JSON.stringify(state)
    } catch { /* ignore parse errors */ }
  }
}

/**
 * Flat list of all tabs from all experiments for the unified tab bar.
 * Each entry: { expTabId, containerTabId, label, isRoot, isActive, dirty }
 */
export const unifiedTabList = computed(() => {
  const result = []
  for (const expTab of experimentTabs.value) {
    const isActiveExp = expTab.id === activeExperimentTabId.value

    // Get container tabs: from live state for active experiment, from cache otherwise
    const containers = isActiveExp ? openTabs.value : (expTab.containerTabs || [{ id: 'root', label: 'Experiment' }])
    const activeContainer = isActiveExp ? activeTab.value : (expTab.activeContainerTab || 'root')

    // Get experiment label from meta.id for active experiment, from snapshot for inactive
    let expLabel = expTab.label
    if (isActiveExp) {
      expLabel = meta.id || expTab.label
    } else {
      try {
        const state = JSON.parse(expTab.stateSnapshot)
        expLabel = state.meta?.id || expTab.label
      } catch { /* use tab label as fallback */ }
    }
    // Append filename if the tab is associated with a file
    if (expTab.fileName) {
      expLabel = `${expLabel} (${expTab.fileName})`
    }

    for (const ct of containers) {
      const isRoot = ct.id === 'root'
      result.push({
        expTabId: expTab.id,
        containerTabId: ct.id,
        label: isRoot ? expLabel : `${expLabel} \u203A ${ct.label}`,
        isRoot,
        isActive: isActiveExp && activeContainer === ct.id,
        dirty: expTab.dirty,
        fileNotFound: !!expTab.fileNotFound,
        expLabel,
      })
    }
  }
  return result
})

// ── Internal ──────────────────────────────────────────────────────────────

/**
 * Find the next available experiment_N number across all tabs.
 */
function getNextExperimentNumber() {
  const ids = new Set()
  // Collect meta.id from the active experiment
  if (meta.id) ids.add(meta.id)
  // Collect from inactive experiment snapshots
  for (const tab of experimentTabs.value) {
    try {
      const state = JSON.parse(tab.stateSnapshot)
      if (state.meta?.id) ids.add(state.meta.id)
    } catch { /* ignore */ }
  }
  let n = 1
  while (ids.has(`experiment_${n}`)) n++
  return n
}

function saveCurrentTab() {
  const tab = experimentTabs.value.find(t => t.id === activeExperimentTabId.value)
  if (tab) {
    tab.stateSnapshot = serializeFullState()
    // Sync container tab cache from live state
    tab.containerTabs = [...openTabs.value]
    tab.activeContainerTab = activeTab.value
  }
}

// ── Tab persistence ──────────────────────────────────────────────────────

let persistTimer = null

/** Debounced save of all tabs to localStorage + file handles to IndexedDB. */
function schedulePersist() {
  clearTimeout(persistTimer)
  persistTimer = setTimeout(persistTabs, 300)
}

/** Synchronous save of tab list to localStorage (no IndexedDB). */
function persistTabsSync() {
  saveCurrentTab()

  const serializable = experimentTabs.value.map(t => ({
    id: t.id,
    label: t.label,
    fileName: t.fileName || null,
    fileNotFound: !!t.fileNotFound,
    dirty: t.dirty,
    stateSnapshot: t.stateSnapshot,
    containerTabs: t.containerTabs,
    activeContainerTab: t.activeContainerTab,
  }))

  const session = {
    tabs: serializable,
    activeTabId: activeExperimentTabId.value,
    tabIdCounter,
  }

  try {
    localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(session))
  } catch { /* storage full */ }
}

/** Save tab list to localStorage (JSON-serializable parts). */
async function persistTabs() {
  // Save current active tab's state first
  saveCurrentTab()

  const serializable = experimentTabs.value.map(t => ({
    id: t.id,
    label: t.label,
    fileName: t.fileName || null,
    fileNotFound: !!t.fileNotFound,
    dirty: t.dirty,
    stateSnapshot: t.stateSnapshot,
    containerTabs: t.containerTabs,
    activeContainerTab: t.activeContainerTab,
  }))

  const session = {
    tabs: serializable,
    activeTabId: activeExperimentTabId.value,
    tabIdCounter,
  }

  try {
    localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(session))
  } catch { /* storage full */ }

  // Save file handles to IndexedDB
  try {
    const db = await openDB()
    const store = db.transaction(TAB_HANDLES_STORE, 'readwrite').objectStore(TAB_HANDLES_STORE)
    await idbClear(store)
    const writeStore = db.transaction(TAB_HANDLES_STORE, 'readwrite').objectStore(TAB_HANDLES_STORE)
    for (const [tabId, handle] of fileHandles.entries()) {
      await idbPut(writeStore, { tabId, handle })
    }
    db.close()
  } catch { /* non-critical */ }
}

/**
 * Synchronous restore of tabs from localStorage (no IndexedDB file handles).
 * Use this in widget mode where onMounted must be synchronous to avoid
 * race conditions with the widget's applyFullState from Python.
 * Returns true if tabs were restored.
 */
export function restoreTabsSync() {
  try {
    const raw = localStorage.getItem(TABS_STORAGE_KEY)
    if (!raw) return false
    const session = JSON.parse(raw)
    if (!session.tabs || session.tabs.length === 0) return false

    tabIdCounter = session.tabIdCounter || 0
    experimentTabs.value = session.tabs

    const activeId = session.activeTabId
    const activeTab_ = experimentTabs.value.find(t => t.id === activeId)
    const targetTab = activeTab_ || experimentTabs.value[0]

    withSuppressedDirty(() => {
      loadFullState(targetTab.stateSnapshot)
      if (targetTab.containerTabs) {
        openTabs.value = [...targetTab.containerTabs]
        activeTab.value = targetTab.activeContainerTab || 'root'
      }
      activeExperimentTabId.value = targetTab.id
    })

    // Restore file handles from IndexedDB asynchronously (best-effort)
    restoreFileHandlesAsync()

    return true
  } catch {
    return false
  }
}

/** Best-effort async restore of file handles from IndexedDB. */
async function restoreFileHandlesAsync() {
  try {
    const db = await openDB()
    const store = db.transaction(TAB_HANDLES_STORE, 'readonly').objectStore(TAB_HANDLES_STORE)
    const handleEntries = await idbGetAll(store)
    db.close()
    for (const entry of handleEntries) {
      if (entry.tabId && entry.handle) {
        fileHandles.set(entry.tabId, entry.handle)
      }
    }
  } catch { /* non-critical */ }
}

/**
 * Restore tabs from localStorage + file handles from IndexedDB.
 * Returns true if tabs were restored.
 */
export async function restoreTabs() {
  try {
    const raw = localStorage.getItem(TABS_STORAGE_KEY)
    if (!raw) return false
    const session = JSON.parse(raw)
    if (!session.tabs || session.tabs.length === 0) return false

    // Restore file handles from IndexedDB and verify files still exist
    const missingFileTabIds = new Set()
    try {
      const db = await openDB()
      const store = db.transaction(TAB_HANDLES_STORE, 'readonly').objectStore(TAB_HANDLES_STORE)
      const handleEntries = await idbGetAll(store)
      db.close()
      for (const entry of handleEntries) {
        if (entry.tabId && entry.handle) {
          fileHandles.set(entry.tabId, entry.handle)
          try {
            await entry.handle.getFile()
          } catch (err) {
            // Only mark as missing if the file is actually gone,
            // not if the browser just hasn't re-granted permission yet
            if (err?.name === 'NotFoundError') {
              missingFileTabIds.add(entry.tabId)
            }
          }
        }
      }
    } catch { /* handles not critical */ }

    // Mark tabs whose backing file no longer exists
    for (const tab of session.tabs) {
      if (tab.fileName && missingFileTabIds.has(tab.id)) {
        tab.fileNotFound = true
      }
    }

    tabIdCounter = session.tabIdCounter || 0
    experimentTabs.value = session.tabs

    // Find the active tab, or default to first
    const activeId = session.activeTabId
    const activeTab_ = experimentTabs.value.find(t => t.id === activeId)
    const targetTab = activeTab_ || experimentTabs.value[0]

    withSuppressedDirty(() => {
      loadFullState(targetTab.stateSnapshot)
      if (targetTab.containerTabs) {
        openTabs.value = [...targetTab.containerTabs]
        activeTab.value = targetTab.activeContainerTab || 'root'
      }
      activeExperimentTabId.value = targetTab.id
    })

    return true
  } catch {
    return false
  }
}

// Auto-persist when tabs change (debounced)
watch(
  [experimentTabs, activeExperimentTabId],
  () => { schedulePersist() },
  { deep: true }
)

// Flush pending persist on page unload so the debounce timer doesn't lose data
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    clearTimeout(persistTimer)
    if (experimentTabs.value.length > 0) {
      persistTabsSync()
    }
  })
}
