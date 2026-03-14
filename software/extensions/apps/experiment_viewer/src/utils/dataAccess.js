/**
 * Utilities for accessing nested fields in experiment result data.
 *
 * Samples are deeply nested dicts. This module provides:
 *   - Field tree discovery (walk a sample to find all leaf numeric fields)
 *   - Fast extraction of a field path across all samples into a Float64Array
 *   - Action-filtered sample slicing
 */

/**
 * Resolve a dot-path on an object.  Returns undefined when any segment is missing.
 */
export function getNestedValue(obj, path) {
  const parts = path.split('.')
  let cur = obj
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = cur[p]
  }
  return cur
}

/**
 * Walk a sample object and return a tree of { label, path, children, isNumeric }.
 * Only includes branches that eventually lead to numeric leaves.
 */
export function buildFieldTree(sample, prefix = '') {
  if (sample == null || typeof sample !== 'object') return []
  const nodes = []
  for (const key of Object.keys(sample)) {
    const val = sample[key]
    const path = prefix ? `${prefix}.${key}` : key
    if (val == null) continue
    if (typeof val === 'number') {
      nodes.push({ label: key, path, children: null, isNumeric: true })
    } else if (typeof val === 'boolean') {
      nodes.push({ label: key, path, children: null, isNumeric: true })
    } else if (typeof val === 'object' && !Array.isArray(val)) {
      const children = buildFieldTree(val, path)
      if (children.length > 0) {
        nodes.push({ label: key, path, children, isNumeric: false })
      }
    }
  }
  return nodes
}

/**
 * Extract a numeric field from every sample into a Float64Array.
 * Boolean values are mapped to 0/1.
 */
export function extractField(samples, fieldPath) {
  const out = new Float64Array(samples.length)
  const parts = fieldPath.split('.')
  for (let i = 0; i < samples.length; i++) {
    let cur = samples[i]
    for (let j = 0; j < parts.length; j++) {
      if (cur == null) { cur = NaN; break }
      cur = cur[parts[j]]
    }
    if (typeof cur === 'boolean') cur = cur ? 1 : 0
    out[i] = typeof cur === 'number' ? cur : NaN
  }
  return out
}

/**
 * Build a time vector from samples (using sample.time relative to first sample).
 * Falls back to tick * 0.01 if time field is absent.
 */
export function extractTimeVector(samples) {
  if (samples.length === 0) return new Float64Array(0)
  const out = new Float64Array(samples.length)
  const t0 = samples[0].time ?? (samples[0].tick ?? 0) * 0.01
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i]
    const t = s.time ?? (s.tick ?? i) * 0.01
    out[i] = t - t0
  }
  return out
}

/**
 * Slice samples that fall within an action's tick range.
 * Returns { samples, startIndex, endIndex } or null.
 */
export function getActionSamples(allSamples, actionData) {
  if (!actionData || allSamples.length === 0) return null
  const startTick = actionData.start_tick ?? 0
  const endTick = actionData.end_tick ?? allSamples.length - 1
  // Ticks are relative indices within the experiment
  const sliced = allSamples.slice(startTick, endTick + 1)
  return { samples: sliced, startIndex: startTick, endIndex: endTick }
}

/**
 * Compute summary statistics for a numeric array.
 */
export function fieldStats(arr) {
  let min = Infinity, max = -Infinity, sum = 0, count = 0
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i]
    if (!isFinite(v)) continue
    if (v < min) min = v
    if (v > max) max = v
    sum += v
    count++
  }
  return {
    min: count ? min : NaN,
    max: count ? max : NaN,
    mean: count ? sum / count : NaN,
    count
  }
}

/**
 * Format a numeric value for display (compact).
 */
export function fmtNum(v, decimals = 4) {
  if (v == null || !isFinite(v)) return '—'
  if (Math.abs(v) < 0.0001 && v !== 0) return v.toExponential(2)
  return v.toFixed(decimals).replace(/\.?0+$/, '') || '0'
}

/**
 * Format seconds as mm:ss.ms
 */
export function fmtTime(seconds) {
  if (!isFinite(seconds)) return '—'
  const sign = seconds < 0 ? '-' : ''
  const abs = Math.abs(seconds)
  const m = Math.floor(abs / 60)
  const s = (abs % 60).toFixed(2)
  return `${sign}${m}:${s.padStart(5, '0')}`
}

/**
 * Status color mapping for actions.
 */
export const STATUS_COLORS = {
  finished: '#2ecc71',
  completed: '#2ecc71',
  running: '#45aaf2',
  error: '#e74c3c',
  timeout: '#f39c12',
  aborted: '#e67e22',
  skipped: '#778ca3',
  pending: '#555',
}

/**
 * Action type category colors (same palette as experiment designer).
 */
export const ACTION_TYPE_COLORS = {
  set_mode: '#fc5c65',
  set_velocity: '#fc5c65',
  set_input: '#fc5c65',
  set_psi: '#fc5c65',
  set_feedback_gain: '#fc5c65',
  set_velocity_pid: '#fc5c65',
  load_control_config: '#fc5c65',
  move_to: '#45aaf2',
  turn_to: '#45aaf2',
  follow_path: '#45aaf2',
  wait_position_event: '#45aaf2',
  run_trajectory: '#a55eea',
  enable_tracking: '#26de81',
  set_tracker_updates: '#26de81',
  wait_for_static: '#f7b731',
  wait_time: '#f7b731',
  beep: '#4ecdc4',
  speak: '#4ecdc4',
  play_tone: '#4ecdc4',
  set_led: '#4ecdc4',
  set_marker: '#778ca3',
  read_state: '#778ca3',
  flush_logs: '#778ca3',
}

export function getActionColor(actionType) {
  return ACTION_TYPE_COLORS[actionType] || '#888'
}
