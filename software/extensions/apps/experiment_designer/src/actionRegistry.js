/**
 * Action type definitions for the experiment designer.
 * Mirrors the new core experiment framework at core/utils/experiments/.
 *
 * This is the single source of truth for the designer UI — add an entry here
 * and the catalog, node renderer, property editor, and YAML serializer all
 * pick it up automatically.
 *
 * Actions match the 16 built-in types from builtin_actions.py.
 * Robot-specific actions are loaded dynamically from public/actions/<robot>.json.
 */

import { ref } from 'vue'

// ── Category colors (node header tint) ─────────────────────────────────────
export const CATEGORIES = {
  flow:         { label: 'Flow',         color: '#45aaf2', icon: '\u21C4' },
  timing:       { label: 'Timing',       color: '#f7b731', icon: '\u23F1' },
  events:       { label: 'Events',       color: '#a55eea', icon: '\u26A1' },
  variables:    { label: 'Variables',     color: '#26de81', icon: '\u{1D465}' },
  functions:    { label: 'Functions',     color: '#778ca3', icon: '\u0192' },
  logging:      { label: 'Logging',      color: '#4ecdc4', icon: '\u270E' },
  control:      { label: 'Control',      color: '#fc5c65', icon: '\u25A0' },
  requirements: { label: 'Requirements', color: '#e056a0', icon: '!' },
  guards:       { label: 'Guards',       color: '#3dc1d3', icon: '\uD83D\uDD12' },
}

// ── Trigger types (from types.py TriggerType enum) ─────────────────────────
export const TRIGGER_TYPES = [
  'immediate', 'transition', 'tick', 'time', 'event', 'periodic',
]

// ── Action definitions ─────────────────────────────────────────────────────
// Each action mirrors the ActionBase subclass from builtin_actions.py:
//   - parameter_defs  → params
//   - data_defs       → dataDefs
//   - transition_ports → transitionPorts (default: ['done'], 'error' always implicit)
//   - isContainer     → has sub-actions (group, parallel, loop, while, condition)

export const ACTIONS = {
  // ── Control Flow ──

  setup_group: {
    category: 'flow',
    description: 'Actions that run before the experiment timer starts (sequential, blocking)',
    isContainer: true,
    defaultWidth: 240,
    defaultHeight: 280,
    transitionPorts: [],
    params: {},
    dataDefs: {},
  },

  cleanup_group: {
    category: 'flow',
    description: 'Actions that run after the experiment finishes (sequential, blocking)',
    isContainer: true,
    defaultWidth: 240,
    defaultHeight: 280,
    transitionPorts: [],
    params: {},
    dataDefs: {},
  },

  group: {
    category: 'flow',
    description: 'Execute sub-actions sequentially',
    isContainer: true,
    defaultWidth: 240,
    defaultHeight: 280,
    transitionPorts: ['done'],
    params: {},
    dataDefs: {},
  },

  parallel: {
    category: 'flow',
    description: 'Execute sub-actions concurrently; done when all complete',
    isContainer: true,
    defaultWidth: 240,
    defaultHeight: 280,
    transitionPorts: ['done'],
    params: {},
    dataDefs: {},
  },

  loop: {
    category: 'flow',
    description: 'For-loop with counter variable',
    isContainer: true,
    defaultWidth: 240,
    defaultHeight: 280,
    transitionPorts: ['done'],
    params: {
      count:          { type: 'str', default: '1', required: true, description: 'Iterations (number or expression)' },
      variable:       { type: 'str', default: 'i', description: 'Loop variable name' },
      max_iterations: { type: 'int', default: null, description: 'Safety limit' },
    },
    dataDefs: {},
    summary: a => {
      const c = a.params.count ?? '1'
      const v = a.params.variable ?? 'i'
      return `${c}\u00D7, ${v}`
    },
  },

  while: {
    category: 'flow',
    description: 'Conditional loop; evaluates test each iteration',
    isContainer: true,
    defaultWidth: 240,
    defaultHeight: 280,
    transitionPorts: ['done'],
    params: {
      test:           { type: 'str', default: '', required: true, description: 'Boolean expression (e.g. "${x > 0}")' },
      max_iterations: { type: 'int', default: 10000, description: 'Safety limit' },
    },
    dataDefs: {},
    summary: a => a.params.test || '?',
  },

  condition: {
    category: 'flow',
    description: 'If/then/else branching on expression',
    transitionPorts: ['then', 'else'],
    params: {
      test: { type: 'str', default: '', required: true, description: 'Boolean expression (e.g. "${x > 10}")' },
    },
    dataDefs: {},
    summary: a => a.params.test || '?',
  },

  // ── Timing ──

  wait_time: {
    category: 'timing',
    description: 'Wait for a specified duration',
    transitionPorts: ['done'],
    params: {
      time: { type: 'str', default: '1.0', required: true, description: 'Duration in seconds (e.g. 2.0, "2s", "500ms")' },
    },
    dataDefs: {},
    summary: a => a.params.time ?? '?',
  },

  wait_ticks: {
    category: 'timing',
    description: 'Wait for N experiment ticks',
    transitionPorts: ['done'],
    params: {
      ticks: { type: 'int', default: 100, required: true, description: 'Number of ticks to wait', min: 0 },
    },
    dataDefs: {},
    summary: a => `${a.params.ticks ?? '?'} ticks`,
  },

  // ── Events ──

  wait_for_event: {
    category: 'events',
    description: 'Wait for an internal experiment event',
    transitionPorts: ['done', 'timeout'],
    params: {
      event:   { type: 'str', default: '', required: true, description: 'Event name/ID to wait for' },
      timeout: { type: 'float', default: null, description: 'Timeout in seconds (null = no timeout)' },
    },
    dataDefs: {
      data:      { type: 'any', description: 'Event data (on done port)' },
      timed_out: { type: 'bool', description: 'True if timed out (on timeout port)' },
    },
    summary: a => a.params.event || '?',
  },

  emit_event: {
    category: 'events',
    description: 'Emit an internal experiment event',
    transitionPorts: ['done'],
    params: {
      event: { type: 'str', default: '', required: true, description: 'Event name/ID to emit' },
      data:  { type: 'str', default: null, description: 'Optional event data (expression)' },
    },
    dataDefs: {},
    summary: a => a.params.event || '?',
  },

  // ── Variables ──

  set_variable: {
    category: 'variables',
    description: 'Set an experiment variable',
    transitionPorts: ['done'],
    params: {
      name:  { type: 'str', default: '', required: true, description: 'Variable name' },
      value: { type: 'str', default: '', required: true, description: 'Value (literal or ${expression})' },
    },
    dataDefs: {},
    summary: a => {
      const n = a.params.name || '?'
      const v = a.params.value ?? ''
      return `${n} = ${String(v).slice(0, 16)}`
    },
  },

  set_parameter: {
    category: 'variables',
    description: 'Modify another action\'s parameter at runtime',
    transitionPorts: ['done'],
    params: {
      action_id:  { type: 'str', default: '', required: true, description: 'Target action ID' },
      param_name: { type: 'str', default: '', required: true, description: 'Parameter name to set' },
      value:      { type: 'str', default: '', required: true, description: 'New value (literal or expression)' },
    },
    dataDefs: {},
    summary: a => {
      const target = `${a.params.action_id || '?'}.${a.params.param_name || '?'}`
      const v = a.params.value
      if (v === null || v === undefined || v === '') return target
      const vs = String(v).length > 12 ? String(v).slice(0, 10) + '\u2026' : String(v)
      return `${target} = ${vs}`
    },
  },

  // ── Functions ──

  execute_function: {
    category: 'functions',
    description: 'Call a function by dot-path on context objects',
    transitionPorts: ['done'],
    params: {
      function: { type: 'str', default: '', required: true, description: 'Dot-path (e.g. "robot.control.set_mode")' },
      args:     { type: 'list', default: [], description: 'Positional arguments' },
      kwargs:   { type: 'dict', default: {}, description: 'Keyword arguments' },
    },
    dataDefs: {
      result: { type: 'any', description: 'Return value of the function' },
    },
    summary: a => a.params.function || '?',
  },

  // ── Logging ──

  log: {
    category: 'logging',
    description: 'Log a message (supports ${expression} interpolation)',
    transitionPorts: ['done'],
    params: {
      message: { type: 'str', default: '', required: true, description: 'Message text (supports ${expr})' },
      level:   { type: 'str', default: 'info', description: 'Log level', options: ['info', 'warning', 'error', 'debug'] },
    },
    dataDefs: {},
    summary: a => `"${(a.params.message || '').slice(0, 20)}"`,
  },

  message: {
    category: 'logging',
    description: 'Emit a user-facing message (displayed on experiment page)',
    transitionPorts: ['done'],
    params: {
      text:  { type: 'str', default: '', required: true, description: 'Message text (supports ${expr})' },
      level: { type: 'str', default: 'info', description: 'Message level', options: ['info', 'warning', 'error'] },
    },
    dataDefs: {},
    summary: a => `"${(a.params.text || '').slice(0, 20)}"`,
  },

  // ── Comparison (designer-friendly condition) ──

  compare: {
    category: 'flow',
    description: 'Compare two values; routes to then/else',
    transitionPorts: ['then', 'else'],
    params: {
      value_a: { type: 'str', default: '', required: true, description: 'Left side (value or ${expression})' },
      operator: { type: 'str', default: '<', required: true, description: 'Comparison operator', options: ['<', '>', '<=', '>=', '==', '!='] },
      value_b: { type: 'str', default: '', required: true, description: 'Right side (value or ${expression})' },
    },
    dataDefs: {},
    summary: a => {
      const va = a.params.value_a || '?'
      const op = a.params.operator || '?'
      const vb = a.params.value_b || '?'
      return `${va} ${op} ${vb}`
    },
  },

  // ── Experiment Control ──

  stop: {
    category: 'control',
    description: 'End the experiment',
    transitionPorts: [],  // no outgoing transitions
    params: {
      status:  { type: 'str', default: 'finished', description: 'Experiment status', options: ['finished', 'error', 'aborted'] },
      message: { type: 'str', default: '', description: 'Status message' },
    },
    dataDefs: {},
    summary: a => a.params.status || 'finished',
  },

  marker: {
    category: 'control',
    description: 'Set a named marker (stored as _marker_{name} variable)',
    transitionPorts: ['done'],
    params: {
      name:  { type: 'str', default: '', required: true, description: 'Marker name' },
      value: { type: 'str', default: 'true', description: 'Marker value' },
    },
    dataDefs: {
      name:  { type: 'str', description: 'Marker name' },
      value: { type: 'str', description: 'Marker value' },
    },
    summary: a => a.params.name || '?',
  },
}

// Internal action — not shown in catalog but used by the designer
export const INTERNAL_ACTIONS = {
  _noop: {
    category: 'flow',
    description: 'Internal merge point',
    transitionPorts: ['done'],
    params: {},
    dataDefs: {},
    hidden: true,
  },
}

// ── Requirement definitions ────────────────────────────────────────────────
// Built-in requirements (generic, not robot-specific)
export const REQUIREMENTS = {
  require_os: {
    category: 'requirements',
    description: 'Require a specific operating system',
    isRequirement: true,
    transitionPorts: [],
    params: {
      os: { type: 'str', default: 'linux', required: true, description: 'Required OS (linux, darwin, win32)', options: ['linux', 'darwin', 'win32'] },
    },
    dataDefs: {},
  },
  require_context_object: {
    category: 'requirements',
    description: 'Require a named context object to be available',
    isRequirement: true,
    transitionPorts: [],
    params: {
      name: { type: 'str', default: '', required: true, description: 'Context object name (e.g. "robot")' },
      type: { type: 'str', default: '', description: 'Expected type (optional)' },
    },
    dataDefs: {},
  },
}

// ── Guard definitions ─────────────────────────────────────────────────────
// Built-in guards (generic, not robot-specific) — none currently
export const GUARDS = {}

// ── Reactive robot state ──────────────────────────────────────────────────
export const robotRequirements = ref({})  // loaded from JSON alongside robotActions
export const robotGuards = ref({})        // loaded from JSON alongside robotActions
export const selectedRobot = ref(localStorage.getItem('experiment-designer-robot') || '')
export const robotActions = ref({})       // loaded from JSON
export const robotCategories = ref({})    // loaded from JSON
export const robotLabel = ref('')         // e.g. "BILBO"
export const availableRobots = ref([])    // [{id, label}, ...] from manifest

/** Merge builtin + robot-loaded actions. */
export function getAllActions() { return { ...ACTIONS, ...robotActions.value } }

/** Merge builtin + robot-loaded categories. */
export function getAllCategories() { return { ...CATEGORIES, ...robotCategories.value } }

/** Merge builtin + robot-loaded requirements. */
export function getAllRequirements() { return { ...REQUIREMENTS, ...robotRequirements.value } }

/** Merge builtin + robot-loaded guards. */
export function getAllGuards() { return { ...GUARDS, ...robotGuards.value } }

/** Check if a type is a requirement. */
export function isRequirementType(type) {
  return type in REQUIREMENTS || type in robotRequirements.value
}

/** Check if a type is a guard. */
export function isGuardType(type) {
  return type in GUARDS || type in robotGuards.value
}

/** Create default params for a requirement type. */
export function createDefaultRequirementParams(type) {
  const all = getAllRequirements()
  const def = all[type]
  if (!def || !def.params) return {}
  const params = {}
  for (const [key, pDef] of Object.entries(def.params)) {
    params[key] = pDef.default !== undefined ? pDef.default : null
  }
  return params
}

/** Create default params for a guard type. */
export function createDefaultGuardParams(type) {
  const all = getAllGuards()
  const def = all[type]
  if (!def || !def.params) return {}
  const params = {}
  for (const [key, pDef] of Object.entries(def.params)) {
    params[key] = pDef.default !== undefined ? pDef.default : null
  }
  return params
}

/** Get requirements grouped by category (for the catalog sidebar). */
export function getRequirementsByCategory() {
  const all = getAllRequirements()
  const grouped = {}
  for (const [type, def] of Object.entries(all)) {
    const cat = def.category || 'requirements'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push({ type, ...def })
  }
  return grouped
}

/** Get guards grouped by category (for the catalog sidebar). */
export function getGuardsByCategory() {
  const all = getAllGuards()
  const grouped = {}
  for (const [type, def] of Object.entries(all)) {
    const cat = def.category || 'guards'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push({ type, ...def })
  }
  return grouped
}

/** Load the robot manifest on startup. */
export async function loadManifest() {
  try {
    const resp = await fetch('/actions/manifest.json')
    if (resp.ok) availableRobots.value = await resp.json()
  } catch { /* no manifest = no robots */ }
}

/** Switch the active robot (loads its action JSON). */
export async function setRobot(id) {
  selectedRobot.value = id
  localStorage.setItem('experiment-designer-robot', id)
  if (!id) {
    robotActions.value = {}
    robotCategories.value = {}
    robotRequirements.value = {}
    robotGuards.value = {}
    robotLabel.value = ''
    return
  }
  await loadRobotActions(id)
}

async function loadRobotActions(id) {
  try {
    const resp = await fetch(`/actions/${id}.json`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    robotActions.value = data.actions || {}
    robotCategories.value = data.categories || {}
    robotLabel.value = data.label || id.toUpperCase()
    // Load robot-specific requirements (marked with isRequirement: true)
    const reqs = data.requirements || {}
    for (const [key, def] of Object.entries(reqs)) {
      def.isRequirement = true
      def.transitionPorts = []
      if (!def.category) def.category = 'requirements'
    }
    robotRequirements.value = reqs
    // Load robot-specific guards (marked with isGuard: true)
    const guards = data.guards || {}
    for (const [key, def] of Object.entries(guards)) {
      def.isGuard = true
      def.transitionPorts = []
      if (!def.category) def.category = 'guards'
    }
    robotGuards.value = guards
  } catch (e) {
    console.warn(`Failed to load ${id} actions:`, e)
    robotActions.value = {}
    robotCategories.value = {}
    robotRequirements.value = {}
    robotGuards.value = {}
    robotLabel.value = ''
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Create a new action parameter set with default values for a given type.
 */
export function createDefaultParams(type) {
  const all = getAllActions()
  const def = all[type] || INTERNAL_ACTIONS[type] || getAllRequirements()[type] || getAllGuards()[type]
  if (!def || !def.params) return {}

  const params = {}
  for (const [key, pDef] of Object.entries(def.params)) {
    if (pDef.default !== undefined) {
      params[key] = Array.isArray(pDef.default)
        ? [...pDef.default]
        : (pDef.default !== null && typeof pDef.default === 'object')
          ? { ...pDef.default }
          : pDef.default
    } else {
      params[key] = null
    }
  }
  return params
}

/**
 * Get actions grouped by category (for the catalog sidebar).
 */
export function getActionsByCategory() {
  const all = getAllActions()
  const grouped = {}
  for (const [type, def] of Object.entries(all)) {
    const cat = def.category
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push({ type, ...def })
  }
  return grouped
}

/**
 * Get a compact summary string for an action node.
 * Builtin actions with a custom summary function use that;
 * all others get an auto-generated summary from their params.
 */
export function getSummary(action) {
  const all = getAllActions()
  const def = all[action.type] || INTERNAL_ACTIONS[action.type] || getAllRequirements()[action.type] || getAllGuards()[action.type]
  if (!def) return ''
  if (typeof def.summary === 'function') {
    try { return def.summary(action) } catch { return '' }
  }
  return ''
}

// Keys to skip in auto-generated param displays (boring / always-default flags)
const SKIP_PARAM_KEYS = new Set(['wait', 'normalized'])

/**
 * Get displayable parameter lines for an action node.
 * Returns [{key, display}]:
 *   1. Required params (always shown)
 *   2. Params changed from their default
 *   3. If nothing from above, the first few non-null params as context
 * Max 3 lines to keep nodes compact.
 */
export function getParamLines(action) {
  const all = getAllActions()
  const def = all[action.type] || INTERNAL_ACTIONS[action.type] || getAllRequirements()[action.type] || getAllGuards()[action.type]
  if (!def || !def.params) return []
  const params = action.params || {}
  const entries = Object.entries(def.params).filter(([k]) => !SKIP_PARAM_KEYS.has(k))
  const important = []  // required + changed
  const contextual = [] // non-null defaults (for fresh nodes)

  for (const [key, pDef] of entries) {
    const val = params[key]
    const isSet = val !== null && val !== undefined && val !== ''
    const isDefault = pDef.default !== undefined && val === pDef.default

    if (pDef.required) {
      important.push({ key, display: formatParamValue(val) })
    } else if (isSet && !isDefault) {
      important.push({ key, display: formatParamValue(val) })
    } else if (isSet && isDefault) {
      contextual.push({ key, display: formatParamValue(val) })
    }
  }

  // If we have important params, show those; otherwise show first few contextual
  if (important.length > 0) return important.slice(0, 3)
  return contextual.slice(0, 3)
}

function formatParamValue(val) {
  if (val === null || val === undefined) return '?'
  if (val === true) return 'true'
  if (val === false) return 'false'
  if (Array.isArray(val)) {
    if (val.length === 0) return '[]'
    const inner = val.map(v => formatParamValue(v)).join(', ')
    return inner.length > 20 ? `[${inner.slice(0, 18)}\u2026]` : `[${inner}]`
  }
  if (typeof val === 'object') return JSON.stringify(val).slice(0, 20)
  const s = String(val)
  return s.length > 20 ? s.slice(0, 18) + '\u2026' : s
}

/**
 * Get the transition ports for an action type (always includes implicit 'error').
 */
export function getTransitionPorts(type) {
  const all = getAllActions()
  const def = all[type] || INTERNAL_ACTIONS[type]
  if (!def) return ['done']
  return def.transitionPorts ?? ['done']
}

/**
 * Get data output definitions for an action type.
 */
export function getDataDefs(type) {
  const all = getAllActions()
  const def = all[type] || INTERNAL_ACTIONS[type]
  return def?.dataDefs ?? {}
}

/**
 * Check if an action has missing required parameters.
 */
export function hasMissingRequired(action) {
  const all = getAllActions()
  const def = all[action.type] || INTERNAL_ACTIONS[action.type]
  if (!def || !def.params) return false
  for (const [key, pDef] of Object.entries(def.params)) {
    if (!pDef.required) continue
    const val = action.params[key]
    if (val === null || val === undefined || val === '') return true
    if (Array.isArray(val) && val.length === 0) return true
  }
  return false
}

/**
 * Check if an action type is a container (has sub-actions).
 */
export function isContainer(type) {
  const all = getAllActions()
  const def = all[type]
  return def?.isContainer === true
}
