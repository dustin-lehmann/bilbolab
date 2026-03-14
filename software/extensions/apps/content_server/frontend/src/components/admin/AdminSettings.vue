<template>
    <div class="settings-page">
        <h1 class="page-title">Settings</h1>

        <div class="settings-section" v-if="settings">
            <h2 class="section-title">General</h2>
            <div class="form-group">
                <label>Site Title</label>
                <input v-model="settings.title" class="input" placeholder="Additional Material">
            </div>
            <div class="form-group">
                <label>Home Page Title</label>
                <input v-model="settings.homeTitle" class="input" placeholder="Dissertation Material">
            </div>
            <div class="form-group">
                <label>Home Page Subtitle</label>
                <input v-model="settings.homeSubtitle" class="input">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Folder Style</label>
                    <select v-model="settings.folderStyle" class="input">
                        <option value="navigation">Navigation</option>
                        <option value="accordion">Accordion</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Folder Element Count</label>
                    <select v-model="settings.folderCountStyle" class="input">
                        <option value="total">Total (e.g. "5 elements")</option>
                        <option value="compact">By Category - Short (icon + number)</option>
                        <option value="detailed">By Category - Long (icon + number + label)</option>
                    </select>
                </div>
            </div>
            <label class="checkbox" style="margin-bottom: 16px">
                <input type="checkbox" v-model="settings.tourEnabled">
                Show guided tour for new visitors
            </label>
            <button class="btn btn-primary" @click="saveSettings" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save Settings' }}
            </button>
            <span v-if="savedMsg" class="saved-msg">{{ savedMsg }}</span>
        </div>

        <div class="settings-section" v-if="settings">
            <h2 class="section-title">Document Linking</h2>
            <p class="section-desc">Link content items to chapters/sections in your thesis. Upload a PDF and enable linking to show references on tiles and clickable links in item views.</p>
            <label class="checkbox" style="margin-bottom: 16px">
                <input type="checkbox" v-model="settings.documentLinkingEnabled">
                Enable document linking
            </label>
            <template v-if="settings.documentLinkingEnabled">
                <div class="form-group">
                    <label>Document Label</label>
                    <input v-model="settings.documentLabel" class="input" placeholder="Thesis">
                </div>
                <label class="checkbox" style="margin-bottom: 16px">
                    <input type="checkbox" v-model="settings.thesisOpenInPanel">
                    Open thesis in slide-in panel (instead of new tab)
                </label>
                <div class="thesis-preview" v-if="settings.thesisDocument">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span>{{ settings.thesisDocument }}</span>
                    <button class="btn btn-sm" @click="settings.thesisDocument = null">Remove</button>
                </div>
                <div class="upload-zone"
                     @dragover.prevent="thesisDrag = true"
                     @dragleave="thesisDrag = false"
                     @drop.prevent="handleThesisDrop"
                     :class="{ active: thesisDrag }">
                    <input type="file" ref="thesisInput" @change="handleThesisSelect" accept=".pdf" style="display:none">
                    <button class="btn btn-sm" @click="$refs.thesisInput.click()">Upload Thesis PDF</button>
                    <span class="upload-hint">or drag a PDF here</span>
                </div>

                <!-- Thesis TOC -->
                <div class="form-group" style="margin-top: 20px">
                    <label>Table of Contents</label>
                    <p class="section-desc" style="margin-bottom: 8px">One entry per line: number followed by name. Names appear next to document references on items.</p>
                    <textarea v-model="tocText" class="input toc-textarea" placeholder="1 Introduction
1.1 Motivation
1.2 Problem Statement
2 Related Work
2.1 Two-Wheeled Robots
3.2.1 Control Board" rows="10"></textarea>
                </div>
            </template>
            <button class="btn btn-primary" style="margin-top: 12px" @click="saveSettings" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save Settings' }}
            </button>
            <span v-if="savedMsg" class="saved-msg">{{ savedMsg }}</span>
        </div>

        <div class="settings-section">
            <h2 class="section-title">Logo</h2>
            <div class="logo-preview" v-if="settings?.logo">
                <img :src="`/${settings.logo}`" alt="Logo" class="logo-img">
            </div>
            <div class="upload-zone"
                 @dragover.prevent="logoDrag = true"
                 @dragleave="logoDrag = false"
                 @drop.prevent="handleLogoDrop"
                 :class="{ active: logoDrag }">
                <input type="file" ref="logoInput" @change="handleLogoSelect" accept="image/*" style="display:none">
                <button class="btn btn-sm" @click="$refs.logoInput.click()">Upload Logo</button>
                <span class="upload-hint">or drag an image here</span>
            </div>
        </div>

        <div class="settings-section">
            <h2 class="section-title">Change Password</h2>
            <div class="form-group">
                <label>New Password</label>
                <input v-model="newPassword" type="password" class="input" placeholder="New password (min 4 characters)">
            </div>
            <div class="form-group">
                <label>Confirm</label>
                <input v-model="confirmPassword" type="password" class="input" placeholder="Confirm password">
            </div>
            <div v-if="passwordError" class="error">{{ passwordError }}</div>
            <div v-if="passwordSuccess" class="success">{{ passwordSuccess }}</div>
            <button class="btn btn-primary" @click="changePassword"
                    :disabled="!newPassword || newPassword.length < 4 || newPassword !== confirmPassword">
                Change Password
            </button>
        </div>

        <div class="settings-section">
            <h2 class="section-title">Export / Import</h2>
            <p class="section-desc">Download all content as a ZIP archive, or replace all content from an uploaded ZIP.</p>
            <div class="export-import-row">
                <button class="btn btn-secondary" @click="downloadExport" :disabled="exporting">
                    {{ exporting ? 'Exporting...' : 'Download ZIP Export' }}
                </button>
                <input type="file" ref="importInput" @change="handleImportSelect" accept=".zip" style="display:none">
                <button class="btn btn-danger" @click="triggerImport" :disabled="importing">
                    {{ importing ? 'Importing...' : 'Import ZIP' }}
                </button>
            </div>
            <div v-if="importError" class="error" style="margin-top:12px">{{ importError }}</div>
            <div v-if="importSuccess" class="success" style="margin-top:12px">{{ importSuccess }}</div>
        </div>

        <div class="settings-section">
            <h2 class="section-title">Danger Zone</h2>
            <p class="section-desc">Remove all folders, items, and files. Settings, password, and logo are kept.</p>
            <button class="btn btn-danger" @click="showClearConfirm = true" :disabled="clearing">
                {{ clearing ? 'Clearing...' : 'Clear All Content' }}
            </button>
            <div v-if="clearSuccess" class="success" style="margin-top:12px">{{ clearSuccess }}</div>
        </div>

        <!-- Import confirmation modal -->
        <Teleport to="body">
            <div v-if="showImportConfirm" class="modal-overlay" @click.self="showImportConfirm = false">
                <div class="modal">
                    <h3 class="modal-title">Replace all content?</h3>
                    <p class="modal-desc">This will <strong>permanently replace</strong> all current content with the contents of the uploaded ZIP file. This action cannot be undone.</p>
                    <p class="modal-file">File: {{ importFile?.name }}</p>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" @click="showImportConfirm = false">Cancel</button>
                        <button class="btn btn-danger" @click="confirmImport">Replace All Content</button>
                    </div>
                </div>
            </div>
            <div v-if="showClearConfirm" class="modal-overlay" @click.self="showClearConfirm = false">
                <div class="modal">
                    <h3 class="modal-title">Clear all content?</h3>
                    <p class="modal-desc">This will <strong>permanently delete</strong> all folders, items, and uploaded files. Settings, password, and logo will be kept. This cannot be undone.</p>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" @click="showClearConfirm = false">Cancel</button>
                        <button class="btn btn-danger" @click="confirmClear">Delete Everything</button>
                    </div>
                </div>
            </div>
        </Teleport>
    </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useApi } from '../../composables/useApi.js'
import { useAuth } from '../../composables/useAuth.js'

const { adminGet, adminPut, adminPost, adminFetch } = useApi()
const { token } = useAuth()

const settings = ref(null)
const saving = ref(false)
const savedMsg = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordError = ref('')
const passwordSuccess = ref('')
const logoDrag = ref(false)
const thesisDrag = ref(false)
const thesisInput = ref(null)
const exporting = ref(false)
const importing = ref(false)
const importError = ref('')
const importSuccess = ref('')
const showImportConfirm = ref(false)
const importFile = ref(null)
const importInput = ref(null)
const clearing = ref(false)
const showClearConfirm = ref(false)
const clearSuccess = ref('')
const tocText = ref('')

onMounted(async () => {
    settings.value = await adminGet('/api/admin/settings')
    // Initialize defaults for new settings
    if (settings.value) {
        if (settings.value.thesisOpenInPanel === undefined) {
            settings.value.thesisOpenInPanel = true
        }
        if (settings.value.thesisTOC && Array.isArray(settings.value.thesisTOC)) {
            tocText.value = tocArrayToText(settings.value.thesisTOC)
        }
    }
})

function tocArrayToText(arr) {
    return arr.map(e => {
        const num = e.subsection
            ? `${e.chapter || ''}.${e.section || ''}.${e.subsection}`
            : e.section
                ? `${e.chapter || ''}.${e.section}`
                : e.chapter || ''
        // Clean up leading/trailing dots from missing parts
        return `${num} ${e.name || ''}`.trim()
    }).join('\n')
}

function parseTocText(text) {
    return text.split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0)
        .map(line => {
            // Match: number (with dots) followed by text
            const m = line.match(/^([\d]+(?:\.[\d]+)*)[\s]+(.+)$/)
            if (!m) return null
            const parts = m[1].split('.')
            return {
                chapter: parts[0] || '',
                section: parts[1] || '',
                subsection: parts[2] || '',
                name: m[2].trim()
            }
        })
        .filter(e => e !== null)
}

async function saveSettings() {
    saving.value = true
    savedMsg.value = ''
    // Parse TOC text into structured array
    settings.value.thesisTOC = parseTocText(tocText.value)
    await adminPut('/api/admin/settings', settings.value)
    saving.value = false
    savedMsg.value = 'Saved!'
    setTimeout(() => { savedMsg.value = '' }, 2000)
}

async function changePassword() {
    passwordError.value = ''
    passwordSuccess.value = ''
    if (newPassword.value !== confirmPassword.value) {
        passwordError.value = 'Passwords do not match'
        return
    }
    try {
        await adminPost('/api/admin/set-password', { password: newPassword.value })
        passwordSuccess.value = 'Password changed successfully'
        newPassword.value = ''
        confirmPassword.value = ''
    } catch (e) {
        passwordError.value = e.message
    }
}

async function uploadLogo(file) {
    const form = new FormData()
    form.append('file', file)
    const data = await adminPost('/api/admin/logo', form)
    if (data.logo) {
        settings.value.logo = data.logo
    }
}

function handleLogoSelect(e) {
    if (e.target.files[0]) uploadLogo(e.target.files[0])
}

function handleLogoDrop(e) {
    logoDrag.value = false
    if (e.dataTransfer.files[0]) uploadLogo(e.dataTransfer.files[0])
}

async function uploadThesis(file) {
    const form = new FormData()
    form.append('file', file)
    const data = await adminPost('/api/admin/thesis', form)
    if (data.thesisDocument) {
        settings.value.thesisDocument = data.thesisDocument
    }
}

function handleThesisSelect(e) {
    if (e.target.files[0]) uploadThesis(e.target.files[0])
    e.target.value = ''
}

function handleThesisDrop(e) {
    thesisDrag.value = false
    if (e.dataTransfer.files[0]) uploadThesis(e.dataTransfer.files[0])
}

async function downloadExport() {
    exporting.value = true
    try {
        const res = await adminFetch('/api/admin/export')
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'content_export.zip'
        a.click()
        URL.revokeObjectURL(url)
    } finally {
        exporting.value = false
    }
}

function triggerImport() {
    importInput.value.click()
}

function handleImportSelect(e) {
    const file = e.target.files[0]
    if (!file) return
    importFile.value = file
    importError.value = ''
    importSuccess.value = ''
    showImportConfirm.value = true
    // Reset input so same file can be re-selected
    e.target.value = ''
}

async function confirmImport() {
    showImportConfirm.value = false
    importing.value = true
    importError.value = ''
    importSuccess.value = ''
    try {
        const form = new FormData()
        form.append('file', importFile.value)
        const data = await adminPost('/api/admin/import', form)
        if (data.success) {
            importSuccess.value = 'Content imported successfully. Reloading settings...'
            settings.value = await adminGet('/api/admin/settings')
        } else {
            importError.value = data.error || 'Import failed'
        }
    } catch (e) {
        importError.value = e.message || 'Import failed'
    } finally {
        importing.value = false
        importFile.value = null
    }
}

async function confirmClear() {
    showClearConfirm.value = false
    clearing.value = true
    clearSuccess.value = ''
    try {
        await adminPost('/api/admin/clear')
        clearSuccess.value = 'All content has been cleared.'
        setTimeout(() => { clearSuccess.value = '' }, 3000)
    } finally {
        clearing.value = false
    }
}
</script>

<style scoped>
.page-title { font-size: 24px; font-weight: 600; margin-bottom: 24px; }
.settings-section {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
    padding: 24px; margin-bottom: 20px; max-width: 700px;
}
.section-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.section-desc { color: var(--text-muted); font-size: 14px; margin-bottom: 12px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 4px; }
.form-row { display: flex; gap: 16px; }
.form-row .form-group { flex: 1; }
.input {
    width: 100%; padding: 10px 12px; background: var(--code-bg); border: 1px solid var(--border-light);
    border-radius: 8px; color: var(--text-primary); font-size: 14px; outline: none; box-sizing: border-box;
}
.input:focus { border-color: #3b82f6; }
select.input { cursor: pointer; }
.btn {
    padding: 10px 20px; border: none; border-radius: 8px; font-size: 13px;
    font-weight: 500; cursor: pointer; transition: all 0.2s; text-decoration: none; display: inline-block;
}
.btn-sm { padding: 6px 12px; }
.btn-primary { background: #3b82f6; color: white; }
.btn-primary:hover:not(:disabled) { background: #2563eb; }
.btn-secondary { background: var(--border-light); color: var(--text-secondary); }
.btn-secondary:hover { background: var(--border-hover); color: var(--text-primary); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.saved-msg { color: #34d399; font-size: 13px; margin-left: 12px; }
.checkbox {
    display: flex; align-items: center; gap: 8px;
    font-size: 13px; color: var(--text-secondary); cursor: pointer;
}
.error { color: #f87171; font-size: 13px; margin-bottom: 12px; }
.success { color: #34d399; font-size: 13px; margin-bottom: 12px; }
.logo-preview { margin-bottom: 12px; }
.logo-img { height: 40px; }
.upload-zone {
    border: 2px dashed var(--border-light); border-radius: 8px; padding: 16px;
    text-align: center; transition: all 0.2s;
    display: flex; align-items: center; justify-content: center; gap: 12px;
}
.upload-zone.active { border-color: #3b82f6; background: rgba(59, 130, 246, 0.05); }
.upload-hint { color: var(--text-faint); font-size: 13px; }
.thesis-preview {
    display: flex; align-items: center; gap: 8px; padding: 10px 14px;
    background: var(--code-bg); border: 1px solid var(--border-light); border-radius: 8px;
    font-size: 13px; color: var(--text-secondary); margin-bottom: 12px;
}
.thesis-preview svg { flex-shrink: 0; color: #ef4444; }
.thesis-preview span { flex: 1; }
.export-import-row { display: flex; gap: 12px; align-items: center; }
.btn-danger { background: #dc2626; color: white; }
.btn-danger:hover:not(:disabled) { background: #b91c1c; }
.modal-overlay {
    position: fixed; inset: 0; background: var(--overlay); z-index: 1000;
    display: flex; align-items: center; justify-content: center;
}
.modal {
    background: var(--bg-elevated); border: 1px solid var(--border-light); border-radius: 12px;
    padding: 24px; max-width: 460px; width: 90%;
}
.modal-title { font-size: 18px; font-weight: 600; margin-bottom: 12px; }
.modal-desc { color: var(--text-secondary); font-size: 14px; line-height: 1.5; margin-bottom: 8px; }
.modal-file { color: var(--text-muted); font-size: 13px; margin-bottom: 20px; }
.modal-actions { display: flex; gap: 12px; justify-content: flex-end; }

/* TOC textarea */
.toc-textarea {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    line-height: 1.6;
    resize: vertical;
    min-height: 120px;
}
</style>
