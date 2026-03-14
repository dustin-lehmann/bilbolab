/**
 * Loads plot presets from YAML files in /presets/ directory.
 *
 * Preset YAML format:
 *   presets:
 *     - label: "My Preset"
 *       category: "Estimation"       # optional, for grouping
 *       description: "..."           # optional tooltip
 *       fields:
 *         - estimation.state.theta
 *         - estimation.state.theta_dot
 *
 * Multiple YAML files are merged. A manifest.json lists available files.
 */
import { ref } from 'vue'

export const presets = ref([])
export const presetCategories = ref([])
export const presetsLoaded = ref(false)

/**
 * Minimal YAML parser — handles only the flat list-of-objects structure
 * used by preset files.  No dependency needed.
 */
function parsePresetsYaml(text) {
  const results = []
  let current = null

  for (const rawLine of text.split('\n')) {
    const line = rawLine.replace(/\r$/, '')

    // Skip blanks and comments
    if (/^\s*(#.*)?$/.test(line)) continue

    // Top-level key "presets:" — just a container, skip
    if (/^presets:\s*$/.test(line)) continue

    // New list item: "  - label: ..."
    const itemMatch = line.match(/^\s+-\s+(\w+):\s*(.*)$/)
    if (itemMatch) {
      current = {}
      results.push(current)
      const key = itemMatch[1]
      const val = stripQuotes(itemMatch[2])
      if (key === 'fields') {
        current.fields = []
      } else {
        current[key] = val
      }
      continue
    }

    // Continuation key on current item: "    category: ..."
    const kvMatch = line.match(/^\s{4,}(\w+):\s*(.*)$/)
    if (kvMatch && current && !line.match(/^\s+-\s/)) {
      const key = kvMatch[1]
      const val = stripQuotes(kvMatch[2])
      if (key === 'fields') {
        current.fields = []
      } else {
        current[key] = val
      }
      continue
    }

    // Field list item: "      - estimation.state.theta"
    const fieldMatch = line.match(/^\s+-\s+(.+)$/)
    if (fieldMatch && current) {
      if (!current.fields) current.fields = []
      current.fields.push(stripQuotes(fieldMatch[1].trim()))
    }
  }

  return results
}

function stripQuotes(s) {
  if (!s) return ''
  s = s.trim()
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1)
  }
  return s
}

/**
 * Load all preset YAML files. Tries manifest.json first, falls back to default.yaml.
 */
export async function loadPresets() {
  const allPresets = []

  // Try loading manifest
  let files = ['default.yaml']
  try {
    const resp = await fetch('/presets/manifest.json')
    if (resp.ok) {
      const manifest = await resp.json()
      if (Array.isArray(manifest.files)) files = manifest.files
    }
  } catch { /* use default */ }

  // Load each YAML file
  for (const file of files) {
    try {
      const resp = await fetch(`/presets/${file}`)
      if (!resp.ok) continue
      const text = await resp.text()
      const parsed = parsePresetsYaml(text)
      allPresets.push(...parsed)
    } catch (e) {
      console.warn(`Failed to load preset file ${file}:`, e)
    }
  }

  // Also try loading user presets from localStorage
  try {
    const userJson = localStorage.getItem('experiment-viewer-user-presets')
    if (userJson) {
      const userPresets = JSON.parse(userJson)
      if (Array.isArray(userPresets)) {
        allPresets.push(...userPresets.map(p => ({ ...p, category: p.category || 'User' })))
      }
    }
  } catch { /* ignore */ }

  // Deduplicate by label
  const seen = new Set()
  const deduped = []
  for (const p of allPresets) {
    if (!p.label || !p.fields?.length) continue
    if (seen.has(p.label)) continue
    seen.add(p.label)
    deduped.push(p)
  }

  presets.value = deduped

  // Build category list (ordered by first appearance)
  const catOrder = []
  const catSet = new Set()
  for (const p of deduped) {
    const cat = p.category || 'Other'
    if (!catSet.has(cat)) {
      catSet.add(cat)
      catOrder.push(cat)
    }
  }
  presetCategories.value = catOrder
  presetsLoaded.value = true
}

/**
 * Get presets grouped by category.
 */
export function getPresetsByCategory(presetList) {
  const groups = {}
  for (const p of presetList) {
    const cat = p.category || 'Other'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(p)
  }
  return groups
}

/**
 * Save a user-defined preset to localStorage.
 */
export function saveUserPreset(preset) {
  try {
    const existing = JSON.parse(localStorage.getItem('experiment-viewer-user-presets') || '[]')
    // Replace if same label exists
    const idx = existing.findIndex(p => p.label === preset.label)
    if (idx >= 0) existing[idx] = preset
    else existing.push(preset)
    localStorage.setItem('experiment-viewer-user-presets', JSON.stringify(existing))
    // Reload
    loadPresets()
  } catch (e) {
    console.error('Failed to save user preset:', e)
  }
}

/**
 * Delete a user-defined preset from localStorage.
 */
export function deleteUserPreset(label) {
  try {
    const existing = JSON.parse(localStorage.getItem('experiment-viewer-user-presets') || '[]')
    const filtered = existing.filter(p => p.label !== label)
    localStorage.setItem('experiment-viewer-user-presets', JSON.stringify(filtered))
    loadPresets()
  } catch (e) {
    console.error('Failed to delete user preset:', e)
  }
}
