/**
 * Central reactive state for the experiment viewer.
 *
 * Holds the loaded experiment data and viewer-wide selection state.
 * All components read from here; mutations go through exported functions.
 */
import { ref, computed, shallowRef, triggerRef } from 'vue'
import { buildFieldTree, extractTimeVector } from './utils/dataAccess.js'

// ── Loaded experiment ────────────────────────────────────────────────────────
/** Raw parsed JSON object — the full experiment result */
export const experimentData = shallowRef(null)

/** File name of the loaded experiment (for display) */
export const fileName = ref('')

// ── Derived data (computed from experimentData) ──────────────────────────────
export const experimentId = computed(() => experimentData.value?.id ?? '')
export const experimentStatus = computed(() => experimentData.value?.status ?? '')
export const experimentMeta = computed(() => experimentData.value?.meta ?? null)
export const experimentDefinition = computed(() => experimentData.value?.definition ?? null)

export const samples = computed(() => experimentData.value?.samples ?? [])
export const actions = computed(() => experimentData.value?.action_data ?? experimentData.value?.actions ?? {})
export const logs = computed(() => experimentData.value?.logs ?? [])

export const sampleCount = computed(() => samples.value.length)
export const duration = computed(() => sampleCount.value * 0.01)

export const timeVector = computed(() => extractTimeVector(samples.value))

/** Field tree built from the first sample (cached). */
export const fieldTree = computed(() => {
  const s = samples.value
  if (s.length === 0) return []
  return buildFieldTree(s[0])
})

/** Sorted action list with IDs attached */
export const actionList = computed(() => {
  const acts = actions.value
  if (!acts) return []
  return Object.entries(acts)
    .map(([id, data]) => ({ id, ...data }))
    .sort((a, b) => (a.start_tick ?? 0) - (b.start_tick ?? 0))
})

// ── Selection state ──────────────────────────────────────────────────────────
/** Currently selected action ID (null = show all samples) */
export const selectedActionId = ref(null)

/** Currently hovered action ID (null = nothing hovered) */
export const hoveredActionId = ref(null)

/** Selected action data */
export const selectedAction = computed(() => {
  if (!selectedActionId.value) return null
  return actions.value?.[selectedActionId.value] ?? null
})

/** Sample range currently visible (filtered by selected action or full) */
export const visibleSampleRange = computed(() => {
  const action = selectedAction.value
  if (!action) return { start: 0, end: sampleCount.value }
  return {
    start: action.start_tick ?? 0,
    end: (action.end_tick ?? sampleCount.value - 1) + 1
  }
})

// ── Dark mode ────────────────────────────────────────────────────────────────
export const darkMode = ref(localStorage.getItem('experiment-viewer-theme') !== 'light')

// ── Session persistence ──────────────────────────────────────────────────────
const STORAGE_KEY = 'experiment-viewer-session'
const SESSION_MAX_AGE_MS = 15 * 60 * 1000 // 15 minutes

function saveSession(data, name) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      data, name, timestamp: Date.now()
    }))
  } catch (e) {
    // localStorage full or unavailable — silently ignore
  }
}

function clearSession() {
  localStorage.removeItem(STORAGE_KEY)
}

function restoreSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const session = JSON.parse(raw)
    if (Date.now() - session.timestamp > SESSION_MAX_AGE_MS) {
      clearSession()
      return
    }
    if (session.data) {
      experimentData.value = session.data
      triggerRef(experimentData)
      fileName.value = session.name ?? ''
    }
  } catch (e) {
    clearSession()
  }
}

// Restore on module load
restoreSession()

// ── Actions ──────────────────────────────────────────────────────────────────

export function loadExperiment(data, name = '') {
  experimentData.value = data
  triggerRef(experimentData)
  fileName.value = name
  selectedActionId.value = null
  saveSession(data, name)
}

export function selectAction(actionId) {
  selectedActionId.value = selectedActionId.value === actionId ? null : actionId
}

export function hoverAction(actionId) {
  hoveredActionId.value = actionId
}

export function clearExperiment() {
  experimentData.value = null
  fileName.value = ''
  selectedActionId.value = null
  hoveredActionId.value = null
  clearSession()
}
