/**
 * Template registry for the experiment designer.
 *
 * Templates are predefined experiment YAML files organized by library (builtin, robot)
 * and category folder. They are loaded from public/templates/manifest.json and
 * robot-specific template manifests from public/templates/<robot>/manifest.json.
 *
 * Structure:
 *   manifest.json → { libraryId: { label, folders: { folderId: { label, templates: [...] } } } }
 *   Robot templates are merged in when a robot is selected.
 */

import { ref, computed } from 'vue'
import { selectedRobot, robotLabel } from './actionRegistry.js'

// ── State ───────────────────────────────────────────────────────────────────
// Raw manifest data: { libraryId: { label, folders: { folderId: { label, templates } } } }
const builtinManifest = ref({})
const robotTemplateManifest = ref({})

/** Whether templates have been loaded. */
export const templatesLoaded = ref(false)

// ── Computed: merged template tree ──────────────────────────────────────────

/**
 * Merged template tree for the dropdown menu.
 * Returns an array of library groups:
 *   [{ id, label, folders: [{ id, label, templates: [{ id, label, file, description }] }] }]
 */
export const templateTree = computed(() => {
  const tree = []

  // Built-in templates
  for (const [libId, lib] of Object.entries(builtinManifest.value)) {
    const folders = []
    for (const [folderId, folder] of Object.entries(lib.folders || {})) {
      if (folder.templates && folder.templates.length > 0) {
        folders.push({
          id: folderId,
          label: folder.label || folderId,
          templates: folder.templates,
        })
      }
    }
    if (folders.length > 0) {
      tree.push({ id: libId, label: lib.label || libId, folders, editable: false })
    }
  }

  // Robot-specific templates
  for (const [libId, lib] of Object.entries(robotTemplateManifest.value)) {
    const folders = []
    for (const [folderId, folder] of Object.entries(lib.folders || {})) {
      folders.push({
        id: folderId,
        label: folder.label || folderId,
        templates: folder.templates || [],
      })
    }
    tree.push({ id: libId, label: lib.label || libId, folders, editable: true })
  }

  return tree
})

/** Flat check: any templates available? */
export const hasTemplates = computed(() => templateTree.value.length > 0)

/** Get list of editable folder IDs for the current robot. */
export const editableFolders = computed(() => {
  const folders = []
  for (const lib of templateTree.value) {
    if (lib.editable) {
      for (const f of lib.folders) {
        folders.push({ id: f.id, label: f.label, libraryId: lib.id })
      }
    }
  }
  return folders
})

// ── Loading ─────────────────────────────────────────────────────────────────

/** Load the built-in template manifest (call once on mount). */
export async function loadTemplateManifest() {
  try {
    const resp = await fetch('/templates/manifest.json')
    if (resp.ok) {
      builtinManifest.value = await resp.json()
    }
  } catch { /* no templates available */ }
  templatesLoaded.value = true
}

/** Load robot-specific templates (call when robot changes). */
export async function loadRobotTemplates(robotId) {
  if (!robotId) {
    robotTemplateManifest.value = {}
    return
  }
  try {
    const resp = await fetch(`/templates/${robotId}/manifest.json`)
    if (resp.ok) {
      robotTemplateManifest.value = await resp.json()
    } else {
      robotTemplateManifest.value = {}
    }
  } catch {
    robotTemplateManifest.value = {}
  }
}

/**
 * Apply a manifest update pushed from the backend.
 * @param {object} manifest - Full robot manifest object
 */
export function applyManifestUpdate(manifest) {
  robotTemplateManifest.value = manifest
}

/**
 * Fetch the YAML content for a template entry.
 * @param {object} template - Template entry from the manifest ({ id, label, file })
 * @returns {Promise<string>} YAML string
 */
export async function fetchTemplateYaml(template) {
  const resp = await fetch(`/templates/${template.file}`)
  if (!resp.ok) throw new Error(`Failed to load template: ${resp.status}`)
  return await resp.text()
}
