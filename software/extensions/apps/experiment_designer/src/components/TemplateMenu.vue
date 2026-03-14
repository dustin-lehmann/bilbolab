<script setup>
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import {
  templateTree, hasTemplates, editableFolders,
  loadTemplateManifest, loadRobotTemplates, fetchTemplateYaml, applyManifestUpdate,
} from '../templateRegistry.js'
import { selectedRobot } from '../actionRegistry.js'

const emit = defineEmits(['select', 'send-event'])

const open = ref(false)
const hoveredLib = ref(null)
const hoveredFolder = ref(null)
const menuRef = ref(null)

// ── Save-as-template modal ────────────────────────────────────────────────
const showSaveModal = ref(false)
const saveFolder = ref('')
const saveNewFolder = ref('')
const saveId = ref('')
const saveDescription = ref('')

// ── Confirmation modal ────────────────────────────────────────────────────
const showConfirmModal = ref(false)
const confirmTitle = ref('')
const confirmMessage = ref('')
let confirmResolve = null

// ── Rename modal ──────────────────────────────────────────────────────────
const showRenameModal = ref(false)
const renameValue = ref('')
const renameTitle = ref('')
let renameResolve = null

// ── Create folder modal ──────────────────────────────────────────────────
const showCreateFolderModal = ref(false)
const createFolderName = ref('')

// Reload robot templates when robot changes
watch(selectedRobot, (id) => {
  loadRobotTemplates(id)
}, { immediate: true })

// Listen for backend manifest updates
function onTemplatesUpdated(e) {
  if (e.detail) {
    applyManifestUpdate(e.detail)
  }
}

onMounted(() => {
  loadTemplateManifest()
  document.addEventListener('click', onClickOutside)
  window.addEventListener('designer-templates-updated', onTemplatesUpdated)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  window.removeEventListener('designer-templates-updated', onTemplatesUpdated)
})

function onClickOutside(e) {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    closeAll()
  }
}

function toggleMenu() {
  open.value = !open.value
  if (!open.value) {
    hoveredLib.value = null
    hoveredFolder.value = null
  }
}

function closeAll() {
  open.value = false
  hoveredLib.value = null
  hoveredFolder.value = null
}

function onLibEnter(lib) {
  hoveredLib.value = lib.id
  hoveredFolder.value = null
}

function onFolderEnter(folder) {
  hoveredFolder.value = folder.id
}

async function onTemplateClick(template) {
  closeAll()
  try {
    const yaml = await fetchTemplateYaml(template)
    emit('select', yaml, template.label)
  } catch (e) {
    alert('Failed to load template: ' + e.message)
  }
}

// ── Send event to Python backend ──────────────────────────────────────────
function sendEvent(event, data) {
  emit('send-event', { event, data })
}

// ── Confirm helper ────────────────────────────────────────────────────────
function confirm(title, message) {
  return new Promise((resolve) => {
    confirmTitle.value = title
    confirmMessage.value = message
    confirmResolve = resolve
    showConfirmModal.value = true
  })
}

function onConfirmYes() {
  showConfirmModal.value = false
  if (confirmResolve) confirmResolve(true)
  confirmResolve = null
}

function onConfirmNo() {
  showConfirmModal.value = false
  if (confirmResolve) confirmResolve(false)
  confirmResolve = null
}

// ── Rename/prompt helper ──────────────────────────────────────────────────
function promptRename(title, initialValue) {
  return new Promise((resolve) => {
    renameTitle.value = title
    renameValue.value = initialValue
    renameResolve = resolve
    showRenameModal.value = true
  })
}

function onRenameConfirm() {
  showRenameModal.value = false
  if (renameResolve) renameResolve(renameValue.value.trim())
  renameResolve = null
}

function onRenameCancel() {
  showRenameModal.value = false
  if (renameResolve) renameResolve(null)
  renameResolve = null
}

// ── Save as template ──────────────────────────────────────────────────────
function openSaveModal() {
  closeAll()
  const folders = editableFolders.value
  saveFolder.value = folders.length > 0 ? folders[0].id : ''
  saveNewFolder.value = ''
  saveId.value = ''
  saveDescription.value = ''
  showSaveModal.value = true
}

function doSaveTemplate() {
  const folder = saveNewFolder.value.trim() || saveFolder.value
  const id = saveId.value.trim().replace(/\s+/g, '_').toLowerCase()
  if (!folder || !id) return

  // Get YAML from the designer (emitted via parent)
  emit('send-event', {
    event: 'get_yaml_for_save',
    data: { folder, id, description: saveDescription.value.trim() },
  })
  showSaveModal.value = false
}

// Called from parent when YAML is available
function completeSaveTemplate(yaml, folder, id, description) {
  sendEvent('save_template', {
    robot_id: selectedRobot.value,
    folder,
    id,
    yaml,
    description,
  })

  // Reopen as the saved template (with corrected id/description)
  let updatedYaml = yaml.replace(/^id:\s*.*$/m, `id: ${id}`)
  if (!/^id:/m.test(updatedYaml)) updatedYaml = `id: ${id}\n` + updatedYaml
  if (description) {
    if (/^description:\s*/m.test(updatedYaml)) {
      updatedYaml = updatedYaml.replace(/^description:\s*.*$/m, `description: ${description}`)
    } else {
      updatedYaml = updatedYaml.replace(/^(id:\s*.*)$/m, `$1\ndescription: ${description}`)
    }
  }
  const label = id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  emit('select', updatedYaml, label)
}

// ── Template actions ──────────────────────────────────────────────────────
async function deleteTemplate(e, template, folder, lib) {
  e.stopPropagation()
  closeAll()
  const yes = await confirm('Delete Template', `Delete "${template.label}" from ${folder.label}?`)
  if (!yes) return

  // Extract folder name from template file path: "bilbo/control/balance_test.yaml" → "control"
  const folderName = template.file.split('/').slice(-2, -1)[0]
  sendEvent('delete_template', {
    robot_id: lib.id,
    folder: folderName,
    id: template.id,
  })
}

async function renameTemplate(e, template, folder, lib) {
  e.stopPropagation()
  closeAll()
  const newId = await promptRename('Rename Template', template.id)
  if (!newId || newId === template.id) return

  const folderName = template.file.split('/').slice(-2, -1)[0]
  sendEvent('rename_template', {
    robot_id: lib.id,
    folder: folderName,
    old_id: template.id,
    new_id: newId.replace(/\s+/g, '_').toLowerCase(),
  })
}

// ── Folder actions ────────────────────────────────────────────────────────
function openCreateFolderModal() {
  closeAll()
  createFolderName.value = ''
  showCreateFolderModal.value = true
}

function doCreateFolder() {
  const name = createFolderName.value.trim().replace(/\s+/g, '_').toLowerCase()
  if (!name) return
  sendEvent('create_folder', {
    robot_id: selectedRobot.value,
    folder: name,
  })
  showCreateFolderModal.value = false
}

async function deleteFolder(e, folder, lib) {
  e.stopPropagation()
  closeAll()
  const count = folder.templates.length
  const msg = count > 0
    ? `Delete folder "${folder.label}" and its ${count} template${count > 1 ? 's' : ''}?`
    : `Delete empty folder "${folder.label}"?`
  const yes = await confirm('Delete Folder', msg)
  if (!yes) return

  sendEvent('delete_folder', {
    robot_id: lib.id,
    folder: folder.id,
  })
}

async function renameFolder(e, folder, lib) {
  e.stopPropagation()
  closeAll()
  const newName = await promptRename('Rename Folder', folder.id)
  if (!newName || newName === folder.id) return

  sendEvent('rename_folder', {
    robot_id: lib.id,
    old_name: folder.id,
    new_name: newName.replace(/\s+/g, '_').toLowerCase(),
  })
}

// ── Templates in selected folder ─────────────────────────────────────────
const selectedFolderTemplates = computed(() => {
  const folderId = saveNewFolder.value.trim() || saveFolder.value
  if (!folderId) return []
  for (const lib of templateTree.value) {
    if (!lib.editable) continue
    for (const folder of lib.folders) {
      if (folder.id === folderId) return folder.templates || []
    }
  }
  return []
})

const existingTemplateIds = computed(() => {
  return new Set(selectedFolderTemplates.value.map(t => t.id))
})

const willOverwrite = computed(() => {
  const id = saveId.value.trim().replace(/\s+/g, '_').toLowerCase()
  return id && existingTemplateIds.value.has(id)
})

function selectExistingTemplate(e) {
  const val = e.target.value
  if (val === '__new__') {
    saveId.value = ''
    saveDescription.value = ''
  } else {
    saveId.value = val
    const tmpl = selectedFolderTemplates.value.find(t => t.id === val)
    saveDescription.value = tmpl?.description || ''
  }
}

defineExpose({ completeSaveTemplate })
</script>

<template>
  <div class="template-menu" ref="menuRef">
    <!-- Trigger buttons -->
    <div class="template-btn-group">
      <button
        class="template-trigger"
        @click="toggleMenu"
        :disabled="!hasTemplates"
        title="Open a predefined experiment template"
      >
        Templates <span class="caret">&#x25BE;</span>
      </button>
      <button
        v-if="selectedRobot"
        class="template-trigger save-trigger"
        @click="openSaveModal"
        title="Save current experiment as a template"
      >
        Save Template
      </button>
    </div>

    <!-- Level 1: Library list -->
    <div v-if="open" class="dropdown level-1">
      <div
        v-for="lib in templateTree"
        :key="lib.id"
        class="menu-item has-sub"
        @mouseenter="onLibEnter(lib)"
      >
        <span class="item-label">{{ lib.label }}</span>
        <span class="sub-arrow">&#x25B8;</span>

        <!-- Level 2: Folder list -->
        <div v-if="hoveredLib === lib.id" class="dropdown level-2">
          <div
            v-for="folder in lib.folders"
            :key="folder.id"
            class="menu-item has-sub"
            @mouseenter="onFolderEnter(folder)"
          >
            <span class="item-label">{{ folder.label }}</span>
            <div v-if="lib.editable" class="item-actions">
              <button class="icon-btn" @click="renameFolder($event, folder, lib)" title="Rename folder">&#x270E;</button>
              <button class="icon-btn danger" @click="deleteFolder($event, folder, lib)" title="Delete folder">&#x2715;</button>
            </div>
            <span v-else class="sub-arrow">&#x25B8;</span>

            <!-- Level 3: Template list -->
            <div v-if="hoveredFolder === folder.id" class="dropdown level-3">
              <div
                v-for="tmpl in folder.templates"
                :key="tmpl.id"
                class="menu-item template-item"
                @click="onTemplateClick(tmpl)"
              >
                <div class="template-header">
                  <span class="item-label">{{ tmpl.label }}</span>
                  <div v-if="lib.editable" class="item-actions">
                    <button class="icon-btn" @click="renameTemplate($event, tmpl, folder, lib)" title="Rename">&#x270E;</button>
                    <button class="icon-btn danger" @click="deleteTemplate($event, tmpl, folder, lib)" title="Delete">&#x2715;</button>
                  </div>
                </div>
                <span v-if="tmpl.description" class="item-desc">{{ tmpl.description }}</span>
              </div>
              <div v-if="folder.templates.length === 0" class="menu-item empty-hint">
                <span class="item-desc">No templates in this folder</span>
              </div>
            </div>
          </div>

          <!-- Add folder button -->
          <div v-if="lib.editable" class="menu-item add-item" @click="openCreateFolderModal">
            <span class="add-icon">+</span>
            <span class="item-label">New Folder</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Save Template Modal -->
  <Teleport to="body">
    <div v-if="showSaveModal" class="modal-overlay" @click.self="showSaveModal = false">
      <div class="modal dark">
        <h3>Save as Template</h3>

        <label class="field-label">Folder</label>
        <select v-model="saveFolder" class="field-input" :disabled="!!saveNewFolder">
          <option v-for="f in editableFolders" :key="f.id" :value="f.id">{{ f.label }}</option>
        </select>

        <label class="field-label">Or create new folder</label>
        <input
          v-model="saveNewFolder"
          class="field-input"
          placeholder="e.g. my_experiments"
        />

        <label class="field-label">Template</label>
        <select
          class="field-input"
          :value="existingTemplateIds.has(saveId.trim().replace(/\s+/g, '_').toLowerCase()) ? saveId.trim().replace(/\s+/g, '_').toLowerCase() : '__new__'"
          @change="selectExistingTemplate"
        >
          <option value="__new__">+ New template...</option>
          <option v-for="t in selectedFolderTemplates" :key="t.id" :value="t.id">
            {{ t.label }}{{ t.description ? ` — ${t.description}` : '' }}
          </option>
        </select>
        <input
          v-model="saveId"
          class="field-input"
          placeholder="e.g. velocity_step_slow"
        />
        <span v-if="willOverwrite" class="overwrite-warning">
          This will overwrite the existing template.
        </span>

        <label class="field-label">Description (optional)</label>
        <input
          v-model="saveDescription"
          class="field-input"
          placeholder="Short description of this template"
        />

        <div class="modal-actions">
          <span style="flex:1"></span>
          <button class="tb-btn" @click="showSaveModal = false">Cancel</button>
          <button
            class="tb-btn primary"
            @click="doSaveTemplate"
            :disabled="!saveId.trim() && !(saveNewFolder.trim() || saveFolder)"
          >{{ willOverwrite ? 'Overwrite' : 'Save' }}</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Create Folder Modal -->
  <Teleport to="body">
    <div v-if="showCreateFolderModal" class="modal-overlay" @click.self="showCreateFolderModal = false">
      <div class="modal dark">
        <h3>Create Folder</h3>
        <label class="field-label">Folder name</label>
        <input
          v-model="createFolderName"
          class="field-input"
          placeholder="e.g. my_experiments"
          @keydown.enter="doCreateFolder"
          autofocus
        />
        <div class="modal-actions">
          <span style="flex:1"></span>
          <button class="tb-btn" @click="showCreateFolderModal = false">Cancel</button>
          <button class="tb-btn primary" @click="doCreateFolder" :disabled="!createFolderName.trim()">Create</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Confirm Modal -->
  <Teleport to="body">
    <div v-if="showConfirmModal" class="modal-overlay" @click.self="onConfirmNo">
      <div class="modal dark">
        <h3>{{ confirmTitle }}</h3>
        <p class="confirm-message">{{ confirmMessage }}</p>
        <div class="modal-actions">
          <span style="flex:1"></span>
          <button class="tb-btn" @click="onConfirmNo">Cancel</button>
          <button class="tb-btn danger-btn" @click="onConfirmYes">Delete</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Rename Modal -->
  <Teleport to="body">
    <div v-if="showRenameModal" class="modal-overlay" @click.self="onRenameCancel">
      <div class="modal dark">
        <h3>{{ renameTitle }}</h3>
        <input
          v-model="renameValue"
          class="field-input"
          @keydown.enter="onRenameConfirm"
          autofocus
        />
        <div class="modal-actions">
          <span style="flex:1"></span>
          <button class="tb-btn" @click="onRenameCancel">Cancel</button>
          <button class="tb-btn primary" @click="onRenameConfirm" :disabled="!renameValue.trim()">Rename</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.template-menu {
  position: relative;
  display: inline-block;
}

.template-btn-group {
  display: flex;
  gap: 2px;
}

.template-trigger {
  font-family: inherit;
  font-size: 11px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-surface);
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 4px;
}
.template-trigger:hover:not(:disabled) { background: var(--bg-hover); }
.template-trigger:disabled { opacity: 0.4; cursor: default; }

.save-trigger {
  border-color: rgba(46, 204, 113, 0.4);
  color: #2ecc71;
}
.save-trigger:hover { background: rgba(46, 204, 113, 0.1) !important; }

.caret {
  font-size: 9px;
  opacity: 0.7;
}

/* ── Dropdown panels ─────────────────────────────────────────────────────── */
.dropdown {
  position: absolute;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  min-width: 160px;
  padding: 4px 0;
  z-index: 1000;
}

.level-1 {
  top: 100%;
  left: 0;
  margin-top: 2px;
}

.level-2 {
  top: -4px;
  left: 100%;
  margin-left: 2px;
}

.level-3 {
  top: -4px;
  left: 100%;
  margin-left: 2px;
  min-width: 220px;
}

/* ── Menu items ──────────────────────────────────────────────────────────── */
.menu-item {
  position: relative;
  display: flex;
  align-items: center;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  gap: 8px;
  color: var(--text);
  transition: background 0.1s;
}

.menu-item:hover {
  background: var(--bg-hover);
}

.item-label {
  flex: 1;
}

.sub-arrow {
  font-size: 9px;
  opacity: 0.5;
  flex-shrink: 0;
}

.template-item {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.template-header {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 8px;
}

.item-desc {
  font-size: 10px;
  opacity: 0.5;
  font-style: italic;
}

.empty-hint {
  cursor: default;
}
.empty-hint:hover {
  background: transparent;
}

/* ── Action buttons on items ─────────────────────────────────────────────── */
.item-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.menu-item:hover > .item-actions,
.template-header:hover > .item-actions {
  opacity: 1;
}

.icon-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 10px;
  padding: 2px 4px;
  border-radius: 3px;
  line-height: 1;
  transition: color 0.1s, background 0.1s;
}
.icon-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.icon-btn.danger:hover {
  color: #e74c3c;
  background: rgba(231, 76, 60, 0.1);
}

/* ── Add item ────────────────────────────────────────────────────────────── */
.add-item {
  border-top: 1px solid var(--border);
  margin-top: 2px;
  padding-top: 6px;
  color: var(--text-dim);
}
.add-item:hover {
  color: var(--accent);
}
.add-icon {
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
}

/* ── Modals ──────────────────────────────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal {
  background: var(--bg-surface, #14141f);
  border: 1px solid var(--border, #2a2a3a);
  border-radius: 8px;
  padding: 20px;
  width: 400px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-family: 'JetBrains Mono', monospace;
}
.modal.dark { background: #14141f; color: #e0e0e0; }

.modal h3 { font-size: 14px; font-weight: 600; margin: 0; }

.field-label {
  font-size: 11px;
  color: #888;
  margin-top: 4px;
}

.field-input {
  font-family: inherit;
  font-size: 12px;
  padding: 6px 10px;
  background: #0a0a0f;
  color: #e0e0e0;
  border: 1px solid #2a2a3a;
  border-radius: 4px;
  outline: none;
}
.field-input:focus { border-color: #45aaf2; }

select.field-input {
  cursor: pointer;
}

.confirm-message {
  font-size: 12px;
  color: #ccc;
  margin: 4px 0;
}

.overwrite-warning {
  font-size: 10px;
  color: #f39c12;
}

.modal-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.tb-btn {
  font-family: inherit;
  font-size: 11px;
  padding: 4px 12px;
  border: 1px solid #2a2a3a;
  border-radius: 4px;
  background: #14141f;
  color: #e0e0e0;
  cursor: pointer;
  transition: background 0.15s;
}
.tb-btn:hover:not(:disabled) { background: #1e1e2e; }
.tb-btn:disabled { opacity: 0.4; cursor: default; }
.tb-btn.primary { background: #45aaf2; color: #fff; border-color: #45aaf2; }
.tb-btn.primary:hover { background: #2d7ab8; }
.tb-btn.danger-btn { background: #e74c3c; color: #fff; border-color: #e74c3c; }
.tb-btn.danger-btn:hover { background: #c0392b; }
</style>
