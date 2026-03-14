<template>
    <div class="folder-view" v-if="folder">
        <div class="viewer-header">
            <div class="nav-section">
                <button v-if="folder.breadcrumb && folder.breadcrumb.length > 0" class="back-btn" @click="goBack">
                    &larr; Back
                </button>
                <router-link v-else to="/" class="back-btn">&larr; Home</router-link>

                <div class="breadcrumb">
                    <router-link to="/" class="breadcrumb-item">Home</router-link>
                    <template v-for="(crumb, index) in folder.breadcrumb" :key="crumb.id">
                        <span class="breadcrumb-sep">/</span>
                        <router-link :to="`/folder/${crumb.id}`" class="breadcrumb-item">
                            {{ crumb.name }}
                        </router-link>
                    </template>
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item current">{{ folder.name }}</span>
                </div>

                <button class="view-toggle" @click="toggle" :title="viewMode === 'grid' ? 'Switch to list view' : 'Switch to grid view'">
                    <svg v-if="viewMode === 'grid'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
                    </svg>
                    <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                        <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
                    </svg>
                </button>

                <button v-if="isAdmin" class="edit-mode-toggle" :class="{ active: editMode }" @click="editMode = !editMode" title="Toggle edit mode">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                    {{ editMode ? 'Done' : 'Edit' }}
                </button>
            </div>
            <div class="header-info">
                <div class="title-row">
                    <h1 class="item-title">{{ folder.name }}</h1>
                    <span class="item-type-badge folder">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                        </svg>
                        Folder
                    </span>
                    <button v-if="editMode" class="card-action-btn edit" @click="editCurrentFolder" title="Edit this folder">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                </div>
                <p class="item-description">{{ folder.description }}</p>
            </div>
        </div>

        <div class="folder-content">
            <!-- Subfolders -->
            <div v-if="folder.folders && folder.folders.length > 0" class="section">
                <h2 class="section-title">Subfolders</h2>
                <div class="content-layout" :class="viewMode">
                    <div v-for="subfolder in folder.folders" :key="subfolder.id" class="tile-wrapper">
                        <div v-if="editMode" class="card-edit-actions">
                            <button class="card-action-btn edit" @click="editFolder(subfolder)" title="Edit folder">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                </svg>
                            </button>
                            <button class="card-action-btn delete" @click="deleteFolder(subfolder)" title="Delete folder">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                                </svg>
                            </button>
                        </div>
                        <ContentTile :item="subfolder" :is-folder="true" :view-mode="viewMode" :edit-mode="editMode" />
                    </div>
                </div>
            </div>

            <!-- Elements (Experiments, PDFs, Figures, etc.) -->
            <div v-if="(folder.experiments && folder.experiments.length > 0) || editMode" class="section">
                <h2 class="section-title">Content</h2>
                <div class="content-layout" :class="viewMode">
                    <div
                        v-for="(exp, idx) in folder.experiments"
                        :key="exp.id"
                        class="tile-wrapper"
                        :class="{ dragging: dragIdx === idx, 'drag-over': dropIdx === idx }"
                        :draggable="editMode"
                        @dragstart="onDragStart(idx, $event)"
                        @dragend="onDragEnd"
                        @dragover.prevent="onDragOver(idx)"
                        @drop.prevent="onDrop(idx)"
                    >
                        <div v-if="editMode" class="card-edit-actions">
                            <button class="card-action-btn edit" @click="editItem(exp)" title="Edit">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                </svg>
                            </button>
                            <span class="drag-handle" title="Drag to reorder">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <circle cx="9" cy="5" r="1.5"/><circle cx="15" cy="5" r="1.5"/>
                                    <circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/>
                                    <circle cx="9" cy="19" r="1.5"/><circle cx="15" cy="19" r="1.5"/>
                                </svg>
                            </span>
                            <button class="card-action-btn delete" @click="deleteItem(exp)" title="Delete">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                                </svg>
                            </button>
                        </div>
                        <ContentTile :item="exp" :view-mode="viewMode" :edit-mode="editMode" />
                    </div>

                    <!-- Add item card -->
                    <div v-if="editMode" class="add-card" :class="viewMode" @click="showCreateModal = true">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                        </svg>
                        <span>Add Item</span>
                    </div>
                </div>
            </div>

            <div v-if="(!folder.folders || folder.folders.length === 0) && (!folder.experiments || folder.experiments.length === 0) && !editMode" class="empty-state">
                <p>This folder is empty</p>
            </div>
        </div>

        <!-- Create item modal -->
        <Teleport to="body">
            <div v-if="showCreateModal" class="ie-overlay" @click.self="showCreateModal = false">
                <div class="ie-modal">
                    <div class="ie-header">
                        <h2>New Item</h2>
                        <button class="ie-close" @click="showCreateModal = false">&times;</button>
                    </div>
                    <div class="ie-body">
                        <div class="ie-field">
                            <label>Type</label>
                            <select v-model="createForm.type" class="ie-input">
                                <option value="video">Video</option>
                                <option value="synchronized">Synchronized Videos</option>
                                <option value="collection">Video Collection</option>
                                <option value="figures">Figure Collection</option>
                                <option value="pdf">PDF</option>
                                <option value="code">Code</option>
                                <option value="interactive">Interactive Example</option>
                                <option value="model3d">3D Model</option>
                            </select>
                        </div>
                        <div class="ie-field">
                            <label>Title</label>
                            <input v-model="createForm.title" class="ie-input" placeholder="Item title">
                        </div>
                        <div class="ie-field">
                            <label>Description</label>
                            <textarea v-model="createForm.description" class="ie-input ie-textarea" placeholder="Optional description"></textarea>
                        </div>
                        <div class="ie-field">
                            <label>Date</label>
                            <input v-model="createForm.date" class="ie-input" type="date">
                        </div>
                        <div class="ie-field">
                            <label>Files</label>
                            <div class="ie-chips">
                                <span v-for="(f, i) in createPending" :key="i" class="ie-chip ie-chip-pending">
                                    {{ f.name }}
                                    <button @click="createPending.splice(i, 1)">&times;</button>
                                </span>
                                <span v-if="createPending.length === 0" class="ie-no-files">No files</span>
                            </div>
                            <div class="ie-drop" :class="{over: createDragover}"
                                 @dragover.prevent="createDragover=true"
                                 @dragleave="createDragover=false"
                                 @drop.prevent="onCreateDrop">
                                <input type="file" multiple ref="createFileInput" @change="onCreateFileSelect" style="display:none">
                                <span class="ie-drop-label">Drop files or <button class="ie-link" @click="$refs.createFileInput.click()">browse</button></span>
                            </div>
                        </div>
                    </div>
                    <div class="ie-footer">
                        <button class="ie-btn ie-btn-ghost" @click="showCreateModal = false">Cancel</button>
                        <button class="ie-btn ie-btn-primary" @click="createItem" :disabled="!createForm.title.trim()">Create Item</button>
                    </div>
                </div>
            </div>
        </Teleport>

        <!-- Folder edit modal -->
        <Teleport to="body">
            <div v-if="showFolderEditModal" class="ie-overlay" @click.self="showFolderEditModal = false">
                <div class="ie-modal">
                    <div class="ie-header">
                        <h2>Edit Folder</h2>
                        <button class="ie-close" @click="showFolderEditModal = false">&times;</button>
                    </div>
                    <div class="ie-body">
                        <div class="ie-field">
                            <label>Name</label>
                            <input v-model="folderEditForm.name" class="ie-input" placeholder="Folder name">
                        </div>
                        <div class="ie-field">
                            <label>Description</label>
                            <textarea v-model="folderEditForm.description" class="ie-input ie-textarea" placeholder="Optional description"></textarea>
                        </div>
                        <div class="ie-field">
                            <label>Thumbnail</label>
                            <div class="thumb-preview-row">
                                <div class="thumb-preview">
                                    <img v-if="folderEditForm.thumbnail" :src="`/thumbnails/${folderEditForm.thumbnail}`" alt="Thumbnail">
                                    <img v-else src="/tour/folder.svg" alt="Default" class="default-thumb">
                                </div>
                                <div class="thumb-actions">
                                    <input type="file" ref="folderThumbInput" accept="image/*" @change="onFolderThumbSelect" style="display:none">
                                    <button class="ie-btn ie-btn-ghost" @click="$refs.folderThumbInput.click()">Upload</button>
                                    <button v-if="folderEditForm.thumbnail" class="ie-btn ie-btn-ghost" @click="folderEditForm.thumbnail = null">Remove</button>
                                </div>
                            </div>
                        </div>
                        <label class="ie-checkbox"><input type="checkbox" v-model="folderEditForm.draft"> Draft (hidden from public)</label>
                    </div>
                    <div class="ie-footer">
                        <button class="ie-btn ie-btn-ghost" @click="showFolderEditModal = false">Cancel</button>
                        <button class="ie-btn ie-btn-primary" @click="saveFolderEdit" :disabled="!folderEditForm.name.trim()">Save Changes</button>
                    </div>
                </div>
            </div>
        </Teleport>
    </div>

    <div v-else class="loading">
        Loading folder...
    </div>
</template>

<script setup>
import { ref, watch, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'
import { useApi } from '../composables/useApi.js'
import { useViewMode } from '../composables/useViewMode.js'
import ContentTile from './ContentTile.vue'

const props = defineProps({
    id: String
})

const settings = inject('settings')
const route = useRoute()
const router = useRouter()
const { isAdmin } = useAuth()
const { adminGet, adminPost, adminPut, adminDelete } = useApi()
const { viewMode, toggle } = useViewMode()

const folder = ref(null)
const editMode = ref(false)

// Drag state
const dragIdx = ref(null)
const dropIdx = ref(null)

// Create modal
const showCreateModal = ref(false)
const createForm = ref(defaultCreateForm())
const createPending = ref([])
const createDragover = ref(false)
const createFileInput = ref(null)

function defaultCreateForm() {
    return {
        title: '', description: '', type: 'video',
        date: new Date().toISOString().split('T')[0],
        draft: false
    }
}

function getItemRoute(item) {
    const type = item.type || 'synchronized'
    if (type === 'video') return `/video/${item.id}`
    if (type === 'pdf') return `/pdf/${item.id}`
    if (type === 'figures') return `/figures/${item.id}`
    if (type === 'code') return `/code/${item.id}`
    if (type === 'interactive') return `/interactive/${item.id}`
    if (type === 'model3d') return `/model3d/${item.id}`
    return `/experiment/${item.id}`
}

function goBack() {
    if (folder.value?.breadcrumb && folder.value.breadcrumb.length > 0) {
        const parent = folder.value.breadcrumb[folder.value.breadcrumb.length - 1]
        router.push(`/folder/${parent.id}`)
    } else {
        router.push('/')
    }
}

async function loadFolder(folderId) {
    try {
        const response = await fetch(`/api/folders/${folderId}`)
        folder.value = await response.json()
    } catch (error) {
        console.error('Failed to load folder:', error)
    }
}

loadFolder(props.id)

watch(() => route.params.id, (newId) => {
    if (newId) {
        loadFolder(newId)
    }
})

// --- Edit mode: drag reorder ---

function onDragStart(idx, event) {
    dragIdx.value = idx
    event.dataTransfer.effectAllowed = 'move'
}

function onDragEnd() {
    dragIdx.value = null
    dropIdx.value = null
}

function onDragOver(idx) {
    if (dragIdx.value !== null && dragIdx.value !== idx) {
        dropIdx.value = idx
    }
}

async function onDrop(idx) {
    if (dragIdx.value === null || dragIdx.value === idx) return
    const experiments = [...folder.value.experiments]
    const [moved] = experiments.splice(dragIdx.value, 1)
    experiments.splice(idx, 0, moved)
    folder.value.experiments = experiments
    dragIdx.value = null
    dropIdx.value = null

    const orderedIds = experiments.map(e => e.id)
    await adminPut('/api/admin/items/reorder', { folderId: folder.value.id, orderedIds })
}

// --- Edit mode: edit item (via App.vue inline edit) ---

function editItem(exp) {
    const itemRoute = getItemRoute(exp)
    router.push(itemRoute + '?inlineEdit=1')
}

// --- Edit mode: delete ---

async function deleteItem(exp) {
    if (!confirm(`Delete "${exp.title}" and all its files?`)) return
    await adminDelete(`/api/admin/items/${exp.id}`)
    await loadFolder(props.id)
}

// --- Folder edit/delete ---

const showFolderEditModal = ref(false)
const folderEditForm = ref({ name: '', description: '', draft: false, thumbnail: null })
const editingFolderId = ref(null)
const folderThumbInput = ref(null)

function editCurrentFolder() {
    editingFolderId.value = folder.value.id
    folderEditForm.value = {
        name: folder.value.name || '',
        description: folder.value.description || '',
        draft: folder.value.draft || false,
        thumbnail: folder.value.thumbnail || null
    }
    showFolderEditModal.value = true
}

function editFolder(subfolder) {
    editingFolderId.value = subfolder.id
    folderEditForm.value = {
        name: subfolder.name || '',
        description: subfolder.description || '',
        draft: subfolder.draft || false,
        thumbnail: subfolder.thumbnail || null
    }
    showFolderEditModal.value = true
}

async function onFolderThumbSelect(e) {
    const file = e.target.files[0]
    if (!file || !editingFolderId.value) return
    const form = new FormData()
    form.append('file', file)
    const result = await adminPost(`/api/admin/thumbnails/${editingFolderId.value}`, form)
    if (result?.thumbnail) {
        folderEditForm.value.thumbnail = result.thumbnail
    }
    e.target.value = ''
}

async function saveFolderEdit() {
    if (!editingFolderId.value) return
    await adminPut(`/api/admin/folders/${editingFolderId.value}`, folderEditForm.value)
    showFolderEditModal.value = false
    await loadFolder(props.id)
}

async function deleteFolder(subfolder) {
    if (!confirm(`Delete folder "${subfolder.name}" and all its contents?`)) return
    await adminDelete(`/api/admin/folders/${subfolder.id}`)
    await loadFolder(props.id)
}

// --- Create item ---

function onCreateFileSelect(e) {
    if (e.target.files.length) createPending.value.push(...e.target.files)
    e.target.value = ''
}

function onCreateDrop(e) {
    createDragover.value = false
    if (e.dataTransfer.files.length) createPending.value.push(...e.dataTransfer.files)
}

async function createItem() {
    const created = await adminPost('/api/admin/items', { ...createForm.value, folderId: folder.value.id })
    if (created?.id && createPending.value.length) {
        const form = new FormData()
        for (const f of createPending.value) form.append('file', f)
        await adminPost(`/api/admin/items/${created.id}/files`, form)
    }
    showCreateModal.value = false
    createForm.value = defaultCreateForm()
    createPending.value = []
    await loadFolder(props.id)
}
</script>

<style scoped>
.folder-view {
    width: 100%;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
}

.viewer-header {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
    flex-shrink: 0;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
}

.folder-content {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}

.nav-section {
    display: flex;
    align-items: center;
    gap: 8px;
}

.back-btn {
    color: var(--text-primary);
    text-decoration: none;
    font-size: 14px;
    padding: 8px 16px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    transition: all 0.2s;
    flex-shrink: 0;
    cursor: pointer;
}

.back-btn:hover {
    background: var(--border);
    border-color: var(--border-hover);
}

.breadcrumb {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    flex-wrap: wrap;
}

.breadcrumb-item {
    color: var(--text-muted);
    text-decoration: none;
    padding: 4px 10px;
    background: var(--bg-elevated);
    border-radius: 6px;
    transition: all 0.2s;
}

.breadcrumb-item:hover:not(.current) {
    background: var(--border);
    color: var(--text-primary);
}

.breadcrumb-item.current {
    color: var(--text-primary);
    background: var(--border-light);
}

.breadcrumb-sep {
    color: var(--border-hover);
}

.title-row {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
}

.item-title {
    font-size: 24px;
    font-weight: 600;
    margin: 0;
}

.item-type-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 10px;
    border-radius: 6px;
}

.item-type-badge.folder {
    background: rgba(156, 163, 175, 0.15);
    color: #9ca3af;
    border: 1px solid rgba(156, 163, 175, 0.3);
}

.item-description {
    color: var(--text-muted);
    font-size: 14px;
    margin-top: 8px;
}

/* ── View toggle ── */
.view-toggle {
    margin-left: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.2s;
}

.view-toggle:hover {
    border-color: var(--border-hover);
    color: var(--text-primary);
}

/* ── Sections ── */
.section {
    margin-bottom: 28px;
    width: 100%;
}

.section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 12px;
}

/* ── Content layout: grid vs list ── */
.content-layout.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    width: 100%;
}

.content-layout.list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    width: 100%;
}

/* ── Tile wrapper (for edit actions) ── */
.tile-wrapper {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    transition: opacity 0.2s, transform 0.15s;
}

.tile-wrapper.dragging {
    opacity: 0.4;
}

.tile-wrapper.drag-over {
    transform: scale(1.02);
}

.tile-wrapper.drag-over::before {
    content: '';
    position: absolute;
    inset: -3px;
    border: 2px dashed #3b82f6;
    border-radius: 14px;
    pointer-events: none;
    z-index: 1;
}

.tile-wrapper[draggable="true"] {
    cursor: grab;
}

.tile-wrapper[draggable="true"]:active {
    cursor: grabbing;
}

/* ── Edit mode toggle ── */
.edit-mode-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.edit-mode-toggle:hover {
    border-color: var(--border-hover);
    color: var(--text-primary);
}

.edit-mode-toggle.active {
    background: rgba(59, 130, 246, 0.15);
    border-color: rgba(59, 130, 246, 0.4);
    color: #60a5fa;
}

/* ── Edit action bar ── */
.card-edit-actions {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    margin-bottom: 6px;
}

.card-action-btn {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-elevated);
    color: var(--text-faint);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
}

.card-action-btn.edit:hover {
    color: #60a5fa;
    border-color: #3b82f6;
    background: rgba(59, 130, 246, 0.1);
}

.card-action-btn.delete:hover {
    color: #f87171;
    border-color: #ef4444;
    background: rgba(239, 68, 68, 0.1);
}

.drag-handle {
    color: var(--text-faint);
    display: flex;
    align-items: center;
    padding: 0 4px;
    cursor: grab;
}

/* ── Add card ── */
.add-card {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    border: 2px dashed var(--border);
    border-radius: 10px;
    background: transparent;
    color: var(--text-faint);
    cursor: pointer;
    transition: all 0.2s;
    font-size: 14px;
    font-weight: 500;
}

.add-card.grid {
    height: 160px;
    flex-direction: column;
}

.add-card.list {
    height: 100px;
}

.add-card:hover {
    border-color: #3b82f6;
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.04);
}

/* ── Thumbnail preview in edit modal ── */
.thumb-preview-row {
    display: flex;
    align-items: center;
    gap: 12px;
}

.thumb-preview {
    width: 100px;
    height: 70px;
    border-radius: 8px;
    overflow: hidden;
    background: var(--code-bg);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.thumb-preview img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.thumb-preview img.default-thumb {
    object-fit: contain;
    padding: 6px;
    opacity: 0.5;
}

.thumb-actions {
    display: flex;
    gap: 8px;
    flex-direction: column;
}

/* ── ie-* form field styles (modal forms) ── */
.ie-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 14px;
}

.ie-field label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

.ie-input {
    width: 100%;
    padding: 8px 12px;
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 0.15s;
    box-sizing: border-box;
}

.ie-input:focus {
    outline: none;
    border-color: #3b82f6;
}

select.ie-input {
    appearance: auto;
    cursor: pointer;
}

.ie-textarea {
    resize: vertical;
    min-height: 70px;
}

.ie-checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
    cursor: pointer;
    margin-bottom: 14px;
}

.ie-checkbox input[type="checkbox"] {
    accent-color: #3b82f6;
}

/* ── States ── */
.empty-state {
    text-align: center;
    padding: 60px;
    color: var(--text-faint);
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}

@media (max-width: 900px) {
    .content-layout.grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 600px) {
    .content-layout.grid {
        grid-template-columns: 1fr;
    }
}
</style>
