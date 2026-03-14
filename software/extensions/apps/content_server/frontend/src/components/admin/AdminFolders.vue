<template>
    <div class="folders-page">
        <div class="page-header">
            <h1 class="page-title">Content</h1>
            <button class="btn btn-primary" @click="openCreateFolder(null)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                New Root Folder
            </button>
        </div>

        <div class="tree-container" v-if="content" @click="closeMenu"
             @dragover.prevent="onTreeDragOver"
             @drop.prevent="onTreeDrop"
             @dragleave="onTreeDragLeave">
            <template v-for="(folder, fi) in content.folders" :key="folder.id">
                <TreeFolder
                    :folder="folder"
                    :depth="0"
                    :index="fi"
                    :sibling-count="content.folders.length"
                    :active-menu="activeMenu"
                    :drag-state="dragState"
                    @open-menu="openMenu"
                    @action="handleAction"
                    @drag-start="onDragStart"
                    @drag-end="onDragEnd"
                />
            </template>
            <div v-if="content.folders.length === 0" class="empty-state">
                No content yet. Create a root folder to get started.
            </div>
        </div>
        <div v-else class="loading-state">Loading content...</div>

        <!-- Context Menu -->
        <Teleport to="body">
            <div v-if="activeMenu" class="context-menu" :style="menuStyle" @click.stop>
                <template v-if="activeMenu.type === 'folder'">
                    <button class="menu-item" @click="doAction('create-item')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                        Add Item
                    </button>
                    <button class="menu-item" @click="doAction('create-subfolder')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
                        Add Subfolder
                    </button>
                    <div class="menu-divider"></div>
                    <button class="menu-item" @click="doAction('edit')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        Edit Folder
                    </button>
                    <button class="menu-item" @click="doAction('toggle-draft')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                        {{ activeMenu.data.draft ? 'Publish' : 'Set as Draft' }}
                    </button>
                    <div class="menu-divider"></div>
                    <button class="menu-item" :disabled="activeMenu.index <= 0" @click="doAction('move-up')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"/></svg>
                        Move Up
                    </button>
                    <button class="menu-item" :disabled="activeMenu.index >= activeMenu.siblingCount - 1" @click="doAction('move-down')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                        Move Down
                    </button>
                    <div class="menu-divider"></div>
                    <button class="menu-item menu-item-danger" @click="doAction('delete')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        Delete Folder
                    </button>
                </template>
                <template v-else>
                    <button class="menu-item" @click="doAction('preview-item')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                        Preview
                    </button>
                    <button class="menu-item" @click="doAction('edit-item')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        Edit Item
                    </button>
                    <button class="menu-item" @click="doAction('toggle-item-draft')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                        {{ activeMenu.data.draft ? 'Publish' : 'Set as Draft' }}
                    </button>
                    <div class="menu-divider"></div>
                    <button class="menu-item" :disabled="activeMenu.index <= 0" @click="doAction('item-move-up')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"/></svg>
                        Move Up
                    </button>
                    <button class="menu-item" :disabled="activeMenu.index >= activeMenu.siblingCount - 1" @click="doAction('item-move-down')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                        Move Down
                    </button>
                    <div class="menu-divider"></div>
                    <button class="menu-item menu-item-danger" @click="doAction('delete-item')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        Delete Item
                    </button>
                </template>
            </div>
        </Teleport>

        <!-- Create/Edit Folder Modal -->
        <div v-if="showFolderModal" class="modal-overlay" @click.self="closeModals">
            <div class="modal">
                <div class="modal-header">
                    <h2>{{ editingFolder ? 'Edit Folder' : 'New Folder' }}</h2>
                    <button class="modal-close" @click="closeModals">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Name</label>
                        <input v-model="folderForm.name" class="input" placeholder="Folder name" @keyup.enter="saveFolder">
                    </div>
                    <div class="form-group">
                        <label>Description</label>
                        <textarea v-model="folderForm.description" class="input textarea" placeholder="Optional description"></textarea>
                    </div>
                    <div class="form-group" v-if="editingFolder">
                        <label>Thumbnail</label>
                        <div class="folder-thumb-row">
                            <div v-if="folderForm.thumbnail" class="folder-thumb-preview">
                                <img :src="`/thumbnails/${folderForm.thumbnail}`" @error="$event.target.style.display='none'">
                                <button class="folder-thumb-remove" @click="folderForm.thumbnail = ''" title="Remove thumbnail">&times;</button>
                            </div>
                            <span v-else class="folder-thumb-empty">No thumbnail</span>
                            <div class="folder-thumb-actions">
                                <input type="file" accept="image/*" ref="folderThumbInput" @change="uploadFolderThumbnail" style="display:none">
                                <button class="btn btn-xs" @click="$refs.folderThumbInput.click()">Upload image</button>
                            </div>
                        </div>
                    </div>
                    <label class="checkbox"><input type="checkbox" v-model="folderForm.draft"> Draft (hidden from public)</label>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-ghost" @click="closeModals">Cancel</button>
                    <button class="btn btn-primary" @click="saveFolder" :disabled="!folderForm.name.trim()">
                        {{ editingFolder ? 'Save Changes' : 'Create Folder' }}
                    </button>
                </div>
            </div>
        </div>

        <!-- Create/Edit Item Modal -->
        <div v-if="showItemModal" class="modal-overlay" @click.self="closeModals">
            <div class="modal modal-item-edit">
                <div class="modal-header">
                    <h2>{{ editingItem ? 'Edit Item' : 'New Item' }}</h2>
                    <div class="modal-header-actions">
                        <a v-if="editingItem" class="modal-open-tab" :href="`/admin/edit/${editingItem.id}`" target="_blank" title="Open full editor">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                                <polyline points="15 3 21 3 21 9"/>
                                <line x1="10" y1="14" x2="21" y2="3"/>
                            </svg>
                        </a>
                        <button class="modal-close" @click="closeModals">&times;</button>
                    </div>
                </div>
                <div class="modal-body">
                    <ItemEditForm :form="itemForm" :available-files="availableFiles"
                        :show-thumbnail="!!editingItem" :generating-thumbnail="generatingThumb"
                        @generate-thumbnail="generateItemThumbnail" @upload-thumbnail="uploadItemThumbnail">
                        <template #files>
                            <div class="ief-card">
                                <h3>Files</h3>
                                <div class="file-chips">
                                    <template v-if="editingItem">
                                        <span v-for="f in editingItemFiles" :key="f" class="file-chip">
                                            {{ f }}
                                            <button @click="removeFile(f)">&times;</button>
                                        </span>
                                        <span v-if="editingItemFiles.length === 0 && pendingFiles.length === 0" class="no-files">No files</span>
                                    </template>
                                    <span v-for="(f, i) in pendingFiles" :key="'p'+i" class="file-chip file-chip-pending">
                                        {{ f.name }}
                                        <button @click="pendingFiles.splice(i, 1)">&times;</button>
                                    </span>
                                    <span v-if="!editingItem && pendingFiles.length === 0" class="no-files">No files</span>
                                </div>
                                <div class="drop-area"
                                     :class="{over: dragover}"
                                     @dragover.prevent="dragover=true"
                                     @dragleave="dragover=false"
                                     @drop.prevent="handleDrop">
                                    <input type="file" multiple ref="fileInput" @change="handleFileSelect" style="display:none">
                                    <span class="drop-label">Drop files or <button class="link-btn" @click="$refs.fileInput.click()">browse</button></span>
                                </div>
                            </div>
                        </template>
                    </ItemEditForm>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-ghost" @click="closeModals">Cancel</button>
                    <button class="btn btn-primary" @click="saveItem" :disabled="!itemForm.title.trim()">
                        {{ editingItem ? 'Save Changes' : 'Create Item' }}
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, defineComponent, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '../../composables/useApi.js'
import ItemEditForm from './ItemEditForm.vue'
import { defaultItemForm, itemFormFromData } from './itemFormHelpers.js'

const { adminGet, adminPost, adminPut, adminDelete } = useApi()

const content = ref(null)
const activeMenu = ref(null)
const menuStyle = ref({})
const showFolderModal = ref(false)
const showItemModal = ref(false)
const editingFolder = ref(null)
const editingItem = ref(null)
const editingItemFiles = ref([])
const createParentId = ref(null)
const createItemFolderId = ref(null)
const pendingFiles = ref([])
const dragover = ref(false)
const availableFiles = computed(() => {
    const files = [...editingItemFiles.value, ...pendingFiles.value.map(f => f.name)]
    return [...new Set(files)]
})

// --- Expanded state (persisted in localStorage) ---
const STORAGE_KEY = 'admin_expanded_folders'
const expandedFolders = reactive(new Set(
    JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
))

function toggleExpanded(folderId) {
    if (expandedFolders.has(folderId)) {
        expandedFolders.delete(folderId)
    } else {
        expandedFolders.add(folderId)
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...expandedFolders]))
}

function isExpanded(folderId) {
    return expandedFolders.has(folderId)
}

// --- Drag and drop ---
const dragState = reactive({
    dragging: null,      // { type: 'folder'|'item', id, parentId }
    dropTarget: null,    // { type: 'on-folder'|'between', id, position, parentId }
})

const folderForm = ref({ name: '', description: '', draft: false, thumbnail: '' })
const generatingThumb = ref(false)
const itemForm = ref(defaultItemForm())

const adminRoute = useRoute()
const adminRouter = useRouter()

async function loadContent() {
    content.value = await adminGet('/api/admin/content')
}

onMounted(async () => {
    await loadContent()
    // Handle ?edit=<itemId> from public view
    const editId = adminRoute.query.edit
    if (editId) {
        adminRouter.replace({ path: adminRoute.path, query: {} })
        try {
            const data = await adminGet(`/api/admin/items/${editId}`)
            if (data && !data.error) {
                editingItem.value = data
                itemForm.value = itemFormFromData(data)
                editingItemFiles.value = data.files || []
                showItemModal.value = true
            }
        } catch (e) {
            console.error('Failed to open item for editing:', e)
        }
    }
})

// --- Context Menu ---

function openMenu(evt) {
    const { event, type, data, index, siblingCount } = evt
    activeMenu.value = { type, data, index, siblingCount }
    const x = Math.min(event.clientX, window.innerWidth - 200)
    const y = Math.min(event.clientY, window.innerHeight - 300)
    menuStyle.value = { left: x + 'px', top: y + 'px' }
}

function closeMenu() {
    activeMenu.value = null
}

function handleGlobalKey(e) {
    if (e.key === 'Escape') { closeMenu(); closeModals() }
}
onMounted(() => document.addEventListener('keydown', handleGlobalKey))
onUnmounted(() => document.removeEventListener('keydown', handleGlobalKey))

function doAction(action) {
    const menu = activeMenu.value
    if (!menu) return
    closeMenu()
    handleAction({ action, ...menu })
}

async function handleAction(evt) {
    const { action, data } = evt
    switch (action) {
        case 'create-item':
            createItemFolderId.value = data.id
            itemForm.value = defaultItemForm()
            showItemModal.value = true
            break
        case 'create-subfolder':
            openCreateFolder(data.id)
            break
        case 'edit':
            editingFolder.value = data
            folderForm.value = { name: data.name, description: data.description || '', draft: data.draft || false, thumbnail: data.thumbnail || '' }
            showFolderModal.value = true
            break
        case 'toggle-draft':
            await adminPut(`/api/admin/folders/${data.id}`, { draft: !data.draft })
            await loadContent()
            break
        case 'move-up':
            await reorderFolder(data.id, -1)
            break
        case 'move-down':
            await reorderFolder(data.id, 1)
            break
        case 'delete':
            if (confirm('Delete this folder and all its contents?')) {
                await adminDelete(`/api/admin/folders/${data.id}`)
                await loadContent()
            }
            break
        case 'preview-item':
            window.open(getItemPreviewRoute(data), '_blank')
            break
        case 'edit-item':
            editingItem.value = data
            itemForm.value = itemFormFromData(data)
            const info = await adminGet(`/api/admin/items/${data.id}`)
            editingItemFiles.value = info.files || []
            showItemModal.value = true
            break
        case 'toggle-item-draft':
            await adminPut(`/api/admin/items/${data.id}`, { draft: !data.draft })
            await loadContent()
            break
        case 'item-move-up':
            await reorderItem(data.id, -1)
            break
        case 'item-move-down':
            await reorderItem(data.id, 1)
            break
        case 'delete-item':
            if (confirm('Delete this item and all its files?')) {
                await adminDelete(`/api/admin/items/${data.id}`)
                await loadContent()
            }
            break
    }
}

// --- Folder CRUD ---

function openCreateFolder(parentId) {
    createParentId.value = parentId
    editingFolder.value = null
    folderForm.value = { name: '', description: '', draft: false, thumbnail: '' }
    showFolderModal.value = true
}

async function saveFolder() {
    if (editingFolder.value) {
        await adminPut(`/api/admin/folders/${editingFolder.value.id}`, folderForm.value)
    } else {
        const payload = { ...folderForm.value }
        if (createParentId.value) payload.parentId = createParentId.value
        await adminPost('/api/admin/folders', payload)
    }
    closeModals()
    await loadContent()
}

// --- Preview ---

function getItemPreviewRoute(item) {
    const type = item.type || 'synchronized'
    if (type === 'pdf') return `/pdf/${item.id}`
    if (type === 'figures') return `/figures/${item.id}`
    if (type === 'code') return `/code/${item.id}`
    if (type === 'video') return `/video/${item.id}`
    return `/experiment/${item.id}`
}

// --- Item CRUD ---

async function saveItem() {
    let itemId
    if (editingItem.value) {
        await adminPut(`/api/admin/items/${editingItem.value.id}`, itemForm.value)
        itemId = editingItem.value.id
    } else {
        const created = await adminPost('/api/admin/items', { ...itemForm.value, folderId: createItemFolderId.value })
        itemId = created?.id
    }
    // Upload any pending files
    if (itemId && pendingFiles.value.length) {
        const form = new FormData()
        for (const f of pendingFiles.value) form.append('file', f)
        await adminPost(`/api/admin/items/${itemId}/files`, form)
    }
    closeModals()
    await loadContent()
}

// --- Reorder ---

function findFolderContext(folders, targetId, parent = null) {
    for (const f of folders) {
        if (f.id === targetId) return { parent, siblings: folders }
        if (f.folders) {
            const r = findFolderContext(f.folders, targetId, f)
            if (r) return r
        }
    }
    return null
}

function findItemContext(folders, targetId) {
    for (const f of folders) {
        const idx = (f.experiments || []).findIndex(e => e.id === targetId)
        if (idx >= 0) return { folder: f, experiments: f.experiments }
        if (f.folders) {
            const r = findItemContext(f.folders, targetId)
            if (r) return r
        }
    }
    return null
}

async function reorderFolder(folderId, direction) {
    const ctx = findFolderContext(content.value.folders, folderId)
    if (!ctx) return
    const ids = ctx.siblings.map(f => f.id)
    const idx = ids.indexOf(folderId)
    const target = idx + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[idx], ids[target]] = [ids[target], ids[idx]]
    await adminPut('/api/admin/folders/reorder', { parentId: ctx.parent?.id || null, orderedIds: ids })
    await loadContent()
}

async function reorderItem(itemId, direction) {
    const ctx = findItemContext(content.value.folders, itemId)
    if (!ctx) return
    const ids = ctx.experiments.map(e => e.id)
    const idx = ids.indexOf(itemId)
    const target = idx + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[idx], ids[target]] = [ids[target], ids[idx]]
    await adminPut('/api/admin/items/reorder', { folderId: ctx.folder.id, orderedIds: ids })
    await loadContent()
}

// --- File management ---

async function removeFile(filename) {
    if (!confirm(`Delete ${filename}?`)) return
    await adminDelete(`/api/admin/items/${editingItem.value.id}/files/${filename}`)
    editingItemFiles.value = editingItemFiles.value.filter(f => f !== filename)
}

async function uploadFiles(files) {
    if (editingItem.value) {
        const form = new FormData()
        for (const f of files) form.append('file', f)
        await adminPost(`/api/admin/items/${editingItem.value.id}/files`, form)
        const data = await adminGet(`/api/admin/items/${editingItem.value.id}`)
        editingItemFiles.value = data.files || []
    } else {
        pendingFiles.value.push(...files)
    }
}

function handleFileSelect(e) { if (e.target.files.length) uploadFiles([...e.target.files]); e.target.value = '' }
function handleDrop(e) { dragover.value = false; if (e.dataTransfer.files.length) uploadFiles([...e.dataTransfer.files]) }

// --- Thumbnail ---
async function uploadFolderThumbnail(e) {
    const file = e.target.files[0]
    if (!file || !editingFolder.value) return
    e.target.value = ''
    const fd = new FormData()
    fd.append('file', file)
    try {
        const res = await adminPost(`/api/admin/thumbnails/${editingFolder.value.id}`, fd)
        if (res?.thumbnail) folderForm.value.thumbnail = res.thumbnail
    } catch (err) { console.error('Failed to upload folder thumbnail:', err) }
}

async function generateItemThumbnail() {
    if (!editingItem.value) return
    generatingThumb.value = true
    try {
        const res = await adminPost(`/api/admin/thumbnails/${editingItem.value.id}/generate`, {})
        if (res?.thumbnail) itemForm.value.thumbnail = res.thumbnail
    } catch (err) { console.error('Failed to generate thumbnail:', err) }
    generatingThumb.value = false
}

async function uploadItemThumbnail(file) {
    if (!editingItem.value || !file) return
    const fd = new FormData()
    fd.append('file', file)
    try {
        const res = await adminPost(`/api/admin/thumbnails/${editingItem.value.id}`, fd)
        if (res?.thumbnail) itemForm.value.thumbnail = res.thumbnail
    } catch (err) { console.error('Failed to upload thumbnail:', err) }
}

function closeModals() {
    showFolderModal.value = false
    showItemModal.value = false
    editingFolder.value = null
    editingItem.value = null
    createParentId.value = null
    createItemFolderId.value = null
    pendingFiles.value = []
}

// --- Drag and drop handlers ---

function onDragStart(info) {
    dragState.dragging = info
    dragState.dropTarget = null
}

function onDragEnd() {
    dragState.dragging = null
    dragState.dropTarget = null
}

function onTreeDragOver(e) {
    // handled by individual rows
}

function onTreeDragLeave(e) {
    // Only clear if leaving the tree container entirely
    if (!e.currentTarget.contains(e.relatedTarget)) {
        dragState.dropTarget = null
    }
}

async function onTreeDrop(e) {
    const src = dragState.dragging
    const tgt = dragState.dropTarget
    dragState.dragging = null
    dragState.dropTarget = null
    if (!src || !tgt) return

    try {
        if (src.type === 'folder') {
            if (tgt.type === 'on-folder') {
                // Move folder into target folder as subfolder
                if (src.id === tgt.id) return // can't drop on self
                await adminPut(`/api/admin/folders/${src.id}/move`, {
                    newParentId: tgt.id,
                    position: 0
                })
            } else if (tgt.type === 'between') {
                // Reorder within same parent or move to different parent
                if (tgt.parentId === src.parentId) {
                    // Same parent — reorder
                    const ctx = findFolderContext(content.value.folders, src.id)
                    if (!ctx) return
                    const ids = ctx.siblings.map(f => f.id).filter(id => id !== src.id)
                    ids.splice(tgt.position, 0, src.id)
                    await adminPut('/api/admin/folders/reorder', {
                        parentId: src.parentId || null,
                        orderedIds: ids
                    })
                } else {
                    // Different parent — move
                    await adminPut(`/api/admin/folders/${src.id}/move`, {
                        newParentId: tgt.parentId || null,
                        position: tgt.position
                    })
                }
            }
        } else if (src.type === 'item') {
            if (tgt.type === 'on-folder') {
                // Move item into target folder
                await adminPut(`/api/admin/items/${src.id}/move`, {
                    targetFolderId: tgt.id,
                    position: 0
                })
            } else if (tgt.type === 'between-items') {
                if (tgt.folderId === src.parentId) {
                    // Same folder — reorder
                    const ctx = findItemContext(content.value.folders, src.id)
                    if (!ctx) return
                    const ids = ctx.experiments.map(e => e.id).filter(id => id !== src.id)
                    ids.splice(tgt.position, 0, src.id)
                    await adminPut('/api/admin/items/reorder', {
                        folderId: tgt.folderId,
                        orderedIds: ids
                    })
                } else {
                    // Different folder — move
                    await adminPut(`/api/admin/items/${src.id}/move`, {
                        targetFolderId: tgt.folderId,
                        position: tgt.position
                    })
                }
            }
        }
        await loadContent()
    } catch (err) {
        console.error('Drop failed:', err)
    }
}

// --- Tree components (using render functions but NO scoped styles - use global classes) ---

const TYPE_COLORS = {
    video: '#8b5cf6', synchronized: '#3b82f6', collection: '#f59e0b', pdf: '#ef4444',
    figures: '#a855f7', code: '#06b6d4', interactive: '#22c55e', model3d: '#0ea5e9'
}
const TYPE_LABELS = {
    video: 'Video', synchronized: 'Sync', collection: 'Collection', pdf: 'PDF',
    figures: 'Figures', code: 'Code', interactive: 'Interactive', model3d: '3D'
}

// Helper: determine drop zone from mouse position on a row element
function getDropZone(e, el) {
    const rect = el.getBoundingClientRect()
    const y = e.clientY - rect.top
    const h = rect.height
    if (y < h * 0.25) return 'before'
    if (y > h * 0.75) return 'after'
    return 'on'
}

// Helper: check if folderId is a descendant of ancestorId
function isDescendant(folders, ancestorId, folderId) {
    function walk(list) {
        for (const f of list) {
            if (f.id === ancestorId) {
                return containsId(f.folders || [], folderId)
            }
            if (f.folders) {
                const r = walk(f.folders)
                if (r) return true
            }
        }
        return false
    }
    function containsId(list, id) {
        for (const f of list) {
            if (f.id === id) return true
            if (f.folders && containsId(f.folders, id)) return true
        }
        return false
    }
    return walk(folders)
}

// Helper: find parent ID of a folder
function findParentId(folders, targetId, parentId = null) {
    for (const f of folders) {
        if (f.id === targetId) return parentId
        if (f.folders) {
            const r = findParentId(f.folders, targetId, f.id)
            if (r !== undefined) return r
        }
    }
    return undefined
}

const TreeFolder = defineComponent({
    name: 'TreeFolder',
    props: ['folder', 'depth', 'index', 'siblingCount', 'activeMenu', 'dragState'],
    emits: ['open-menu', 'action', 'drag-start', 'drag-end'],
    setup(props, { emit }) {
        function folderParentId() {
            // Walk tree to find this folder's parent
            return findParentId(content.value?.folders || [], props.folder.id)
        }

        function handleFolderDragStart(e) {
            e.dataTransfer.effectAllowed = 'move'
            e.dataTransfer.setData('text/plain', props.folder.id)
            // Small delay so the drag image renders before we set state
            setTimeout(() => {
                emit('drag-start', { type: 'folder', id: props.folder.id, parentId: folderParentId() })
            }, 0)
        }

        function handleItemDragStart(e, item) {
            e.dataTransfer.effectAllowed = 'move'
            e.dataTransfer.setData('text/plain', item.id)
            setTimeout(() => {
                emit('drag-start', { type: 'item', id: item.id, parentId: props.folder.id })
            }, 0)
        }

        function handleFolderDragOver(e) {
            e.preventDefault()
            e.stopPropagation()
            const ds = props.dragState
            if (!ds.dragging) return

            const zone = getDropZone(e, e.currentTarget)
            const f = props.folder

            // Prevent dropping folder on itself or its descendants
            if (ds.dragging.type === 'folder') {
                if (ds.dragging.id === f.id) return
                if (content.value && isDescendant(content.value.folders, ds.dragging.id, f.id)) return
            }

            if (zone === 'on') {
                ds.dropTarget = { type: 'on-folder', id: f.id }
            } else {
                const parentId = folderParentId()
                const pos = zone === 'before' ? props.index : props.index + 1
                if (ds.dragging.type === 'folder') {
                    ds.dropTarget = { type: 'between', parentId: parentId, position: pos }
                } else {
                    // Items dropping between folders → drop into the folder
                    ds.dropTarget = { type: 'on-folder', id: f.id }
                }
            }
        }

        function handleItemDragOver(e, item, itemIndex) {
            e.preventDefault()
            e.stopPropagation()
            const ds = props.dragState
            if (!ds.dragging) return

            const rect = e.currentTarget.getBoundingClientRect()
            const y = e.clientY - rect.top
            const before = y < rect.height / 2

            if (ds.dragging.type === 'item') {
                if (ds.dragging.id === item.id) return
                const pos = before ? itemIndex : itemIndex + 1
                ds.dropTarget = { type: 'between-items', folderId: props.folder.id, position: pos }
            } else {
                // Folder being dragged over an item — treat as reorder between folders
                // not meaningful, ignore
            }
        }

        return () => {
            const f = props.folder
            const ds = props.dragState
            const pad = 12 + props.depth * 20
            const items = f.experiments || []
            const subs = f.folders || []
            const hasKids = items.length > 0 || subs.length > 0
            const nodes = []

            // Determine highlight state for this folder row
            const isDropOnThis = ds.dropTarget?.type === 'on-folder' && ds.dropTarget?.id === f.id
            const isBeforeLine = ds.dropTarget?.type === 'between' && ds.dropTarget?.parentId === folderParentId() && ds.dropTarget?.position === props.index
            const isAfterLine = ds.dropTarget?.type === 'between' && ds.dropTarget?.parentId === folderParentId() && ds.dropTarget?.position === props.index + 1
            const isDraggingSelf = ds.dragging?.type === 'folder' && ds.dragging?.id === f.id

            // Drop indicator line before
            if (isBeforeLine && ds.dragging) {
                nodes.push(h('div', { class: 'drop-indicator-line', style: { marginLeft: pad + 'px' } }))
            }

            // Folder row
            nodes.push(h('div', {
                class: 'tree-row tree-folder-row'
                    + (f.draft ? ' is-draft' : '')
                    + (isDropOnThis ? ' drop-target-on' : '')
                    + (isDraggingSelf ? ' dragging-self' : ''),
                style: { paddingLeft: pad + 'px' },
                draggable: true,
                onDragstart: handleFolderDragStart,
                onDragend: () => emit('drag-end'),
                onDragover: handleFolderDragOver,
                onContextmenu: (e) => {
                    e.preventDefault()
                    emit('open-menu', { event: e, type: 'folder', data: f, index: props.index, siblingCount: props.siblingCount })
                }
            }, [
                // Expand toggle
                h('button', {
                    class: 'tree-toggle' + (isExpanded(f.id) ? ' open' : '') + (!hasKids ? ' invisible' : ''),
                    onClick: (e) => { e.stopPropagation(); toggleExpanded(f.id) },
                    draggable: false
                }, [
                    h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2.5 }, [
                        h('polyline', { points: '9 18 15 12 9 6' })
                    ])
                ]),
                // Folder icon
                h('svg', { class: 'tree-icon', width: 15, height: 15, viewBox: '0 0 24 24', fill: '#6b7280' }, [
                    h('path', { d: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' })
                ]),
                // Name
                h('span', { class: 'tree-label' }, f.name),
                // Draft badge
                f.draft ? h('span', { class: 'tree-badge draft' }, 'DRAFT') : null,
                // Count
                h('span', { class: 'tree-count' }, `${items.length} item${items.length !== 1 ? 's' : ''}${subs.length ? ', ' + subs.length + ' sub' : ''}`),
                // More button
                h('button', {
                    class: 'tree-more',
                    draggable: false,
                    onClick: (e) => {
                        e.stopPropagation()
                        emit('open-menu', { event: e, type: 'folder', data: f, index: props.index, siblingCount: props.siblingCount })
                    }
                }, [
                    h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                        h('circle', { cx: 12, cy: 5, r: 1.5 }),
                        h('circle', { cx: 12, cy: 12, r: 1.5 }),
                        h('circle', { cx: 12, cy: 19, r: 1.5 })
                    ])
                ])
            ]))

            // Drop indicator line after folder (when no children or collapsed)
            if (isAfterLine && ds.dragging && (!hasKids || !isExpanded(f.id))) {
                nodes.push(h('div', { class: 'drop-indicator-line', style: { marginLeft: pad + 'px' } }))
            }

            // Children
            if (isExpanded(f.id) && hasKids) {
                // Items
                items.forEach((item, ii) => {
                    const color = TYPE_COLORS[item.type || 'synchronized'] || '#3b82f6'
                    const isItemDragging = ds.dragging?.type === 'item' && ds.dragging?.id === item.id
                    const isItemDropBefore = ds.dropTarget?.type === 'between-items'
                        && ds.dropTarget?.folderId === f.id && ds.dropTarget?.position === ii
                    const isItemDropAfter = ds.dropTarget?.type === 'between-items'
                        && ds.dropTarget?.folderId === f.id && ds.dropTarget?.position === ii + 1

                    if (isItemDropBefore && ds.dragging) {
                        nodes.push(h('div', { class: 'drop-indicator-line', style: { marginLeft: (pad + 24) + 'px' } }))
                    }

                    nodes.push(h('div', {
                        class: 'tree-row tree-item-row'
                            + (item.draft ? ' is-draft' : '')
                            + (isItemDragging ? ' dragging-self' : ''),
                        style: { paddingLeft: (pad + 24) + 'px' },
                        draggable: true,
                        onDragstart: (e) => handleItemDragStart(e, item),
                        onDragend: () => emit('drag-end'),
                        onDragover: (e) => handleItemDragOver(e, item, ii),
                        onContextmenu: (e) => {
                            e.preventDefault()
                            emit('open-menu', { event: e, type: 'item', data: item, index: ii, siblingCount: items.length })
                        },
                        onDblclick: () => emit('action', { action: 'edit-item', data: item })
                    }, [
                        h('span', { class: 'tree-dot', style: { background: color } }),
                        h('span', { class: 'tree-label' }, item.title),
                        h('span', { class: 'tree-type-tag', style: { color, borderColor: color + '33' } }, TYPE_LABELS[item.type || 'synchronized']),
                        item.draft ? h('span', { class: 'tree-badge draft' }, 'DRAFT') : null,
                        h('button', {
                            class: 'tree-more',
                            draggable: false,
                            onClick: (e) => {
                                e.stopPropagation()
                                emit('open-menu', { event: e, type: 'item', data: item, index: ii, siblingCount: items.length })
                            }
                        }, [
                            h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                                h('circle', { cx: 12, cy: 5, r: 1.5 }),
                                h('circle', { cx: 12, cy: 12, r: 1.5 }),
                                h('circle', { cx: 12, cy: 19, r: 1.5 })
                            ])
                        ])
                    ]))

                    // Drop indicator after last item
                    if (isItemDropAfter && ii === items.length - 1 && ds.dragging) {
                        nodes.push(h('div', { class: 'drop-indicator-line', style: { marginLeft: (pad + 24) + 'px' } }))
                    }
                })

                // Subfolders
                subs.forEach((sub, si) => {
                    nodes.push(h(TreeFolder, {
                        key: sub.id,
                        folder: sub,
                        depth: props.depth + 1,
                        index: si,
                        siblingCount: subs.length,
                        activeMenu: props.activeMenu,
                        dragState: props.dragState,
                        'onOpen-menu': (e) => emit('open-menu', e),
                        onAction: (e) => emit('action', e),
                        'onDrag-start': (e) => emit('drag-start', e),
                        'onDrag-end': () => emit('drag-end'),
                    }))
                })
            }

            return h('div', { class: 'tree-node' }, nodes)
        }
    }
})
</script>

<style>
/* ---- Tree styles (global, not scoped, so render-function components inherit them) ---- */
.tree-container {
    background: var(--bg-sidebar);
    border: 1px solid var(--bg-card-hover);
    border-radius: 10px;
    overflow: hidden;
}

.tree-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 14px;
    cursor: default;
    transition: background 0.1s;
    min-height: 34px;
}
.tree-row:hover {
    background: var(--bg-elevated);
}
.tree-row.is-draft {
    opacity: 0.5;
}
.tree-row.is-draft:hover {
    opacity: 0.75;
}

.tree-toggle {
    width: 18px; height: 18px;
    display: flex; align-items: center; justify-content: center;
    background: none; border: none; color: var(--text-faint);
    cursor: pointer; border-radius: 3px; flex-shrink: 0;
    transition: all 0.15s;
}
.tree-toggle:hover { color: var(--text-secondary); background: var(--bg-button-hover); }
.tree-toggle svg { transition: transform 0.15s; }
.tree-toggle.open svg { transform: rotate(90deg); }
.tree-toggle.invisible { visibility: hidden; }

.tree-icon { flex-shrink: 0; }

.tree-label {
    flex: 1; min-width: 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    font-size: 13px;
}
.tree-folder-row .tree-label { font-weight: 500; color: #d4d4d4; }
.tree-item-row .tree-label { color: var(--text-secondary); }

.tree-dot {
    width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}

.tree-type-tag {
    font-size: 10px; font-weight: 600;
    padding: 1px 7px; border-radius: 4px;
    border: 1px solid; flex-shrink: 0;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}

.tree-badge.draft {
    font-size: 9px; font-weight: 700;
    padding: 1px 5px; border-radius: 3px;
    background: rgba(245,158,11,0.15); color: #f59e0b;
    letter-spacing: 0.5px; flex-shrink: 0;
}

.tree-count {
    font-size: 11px; color: var(--border-hover); flex-shrink: 0;
    margin-left: auto;
}

.tree-more {
    width: 24px; height: 24px;
    display: flex; align-items: center; justify-content: center;
    background: none; border: none; color: var(--border-hover);
    cursor: pointer; border-radius: 4px; flex-shrink: 0;
    opacity: 0; transition: all 0.15s;
}
.tree-row:hover .tree-more { opacity: 1; }
.tree-more:hover { background: var(--bg-button-hover); color: var(--text-secondary); }

/* Context menu */
.context-menu {
    position: fixed;
    background: var(--bg-card, #1e1e2e);
    border: 1px solid var(--border-hover, #3a3a52);
    border-radius: 10px;
    padding: 5px;
    min-width: 190px;
    z-index: 9999;
    box-shadow: 0 12px 40px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.04);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
}
.menu-item {
    display: flex; align-items: center; gap: 10px;
    width: 100%; padding: 7px 12px;
    background: none; border: none; color: var(--text-secondary, #bbb);
    font-size: 13px; cursor: pointer;
    border-radius: 6px; transition: all 0.12s;
    text-align: left;
}
.menu-item svg { opacity: 0.55; transition: opacity 0.12s; flex-shrink: 0; }
.menu-item:hover { background: rgba(59,130,246,0.12); color: var(--text-primary); }
.menu-item:hover svg { opacity: 0.9; }
.menu-item:disabled { opacity: 0.3; cursor: default; }
.menu-item:disabled:hover { background: none; color: var(--text-secondary, #bbb); }
.menu-item:disabled:hover svg { opacity: 0.55; }
.menu-item-danger { color: var(--text-secondary, #bbb); }
.menu-item-danger svg { color: #f87171; opacity: 0.7; }
.menu-item-danger:hover { background: rgba(239,68,68,0.1); color: #f87171; }
.menu-item-danger:hover svg { opacity: 1; }
.menu-divider { height: 1px; background: var(--border, #2a2a3e); margin: 4px 8px; }

/* Drag and drop */
.tree-row[draggable="true"] { cursor: grab; }
.tree-row[draggable="true"]:active { cursor: grabbing; }
.tree-row.dragging-self { opacity: 0.3; }
.tree-row.drop-target-on {
    background: rgba(59, 130, 246, 0.1) !important;
    outline: 1px dashed #3b82f6;
    outline-offset: -1px;
    border-radius: 4px;
}
.drop-indicator-line {
    height: 2px;
    background: #3b82f6;
    border-radius: 1px;
    margin: -1px 14px -1px 0;
    position: relative;
    pointer-events: none;
}
.drop-indicator-line::before {
    content: '';
    position: absolute;
    left: -3px; top: -3px;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #3b82f6;
}
</style>

<style scoped>
/* ---- Page / Modal styles (scoped) ---- */
.folders-page { max-width: 900px; }

.page-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 16px;
}
.page-title { font-size: 24px; font-weight: 600; }

.empty-state, .loading-state {
    padding: 48px; text-align: center; color: var(--text-faint); font-size: 14px;
}

/* Buttons */
.btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 16px; border: none; border-radius: 7px;
    font-size: 13px; font-weight: 500; cursor: pointer;
    transition: all 0.15s;
}
.btn-primary { background: #3b82f6; color: var(--text-primary); }
.btn-primary:hover:not(:disabled) { background: #2563eb; }
.btn-primary:disabled { opacity: 0.45; cursor: default; }
.btn-ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border-light); }
.btn-ghost:hover { background: var(--bg-elevated); color: var(--text-secondary); border-color: var(--border-hover); }

/* Modals */
.modal-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.65);
    display: flex; align-items: center; justify-content: center;
    z-index: 500; padding: 20px;
}
.modal {
    background: var(--bg-card); border: 1px solid var(--bg-button-hover); border-radius: 12px;
    width: 100%; max-width: 480px; max-height: 90vh;
    display: flex; flex-direction: column;
    box-shadow: 0 20px 60px var(--overlay-light);
}
.modal.modal-wide { max-width: 640px; }
.modal.modal-item-edit { max-width: 780px; }
.modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 18px 22px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.modal-header h2 { font-size: 17px; font-weight: 600; margin: 0; }
.modal-header-actions { display: flex; align-items: center; gap: 8px; }
.modal-open-tab {
    display: flex; align-items: center; justify-content: center;
    width: 30px; height: 30px; border-radius: 6px;
    color: var(--text-faint); text-decoration: none; transition: all 0.15s;
}
.modal-open-tab:hover { color: var(--text-primary); background: var(--border); }
.modal-close {
    background: none; border: none; color: var(--text-faint); font-size: 22px;
    cursor: pointer; line-height: 1; padding: 0 4px; border-radius: 4px;
}
.modal-close:hover { color: var(--text-primary); background: var(--border); }
.modal-body { padding: 20px 22px; overflow-y: auto; flex: 1; }
.modal-footer {
    display: flex; justify-content: flex-end; gap: 8px;
    padding: 14px 22px; border-top: 1px solid var(--border); flex-shrink: 0;
}

/* Form (folder modal) */
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--text-faint); margin-bottom: 5px; font-weight: 500; letter-spacing: 0.3px; }

.input {
    width: 100%; padding: 9px 12px;
    background: var(--bg-input); border: 1px solid var(--border); border-radius: 7px;
    color: #ddd; font-size: 13px; outline: none; box-sizing: border-box;
    transition: border-color 0.15s;
}
.input:focus { border-color: #3b82f6; }
.textarea { min-height: 70px; resize: vertical; font-family: inherit; }
select.input { cursor: pointer; }

.checkbox {
    display: flex; align-items: center; gap: 8px;
    font-size: 13px; color: var(--text-secondary); cursor: pointer;
}

/* File management (used inside ItemEditForm slot) */
.file-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.file-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; background: var(--bg-elevated); border: 1px solid var(--bg-button-hover);
    border-radius: 6px; font-size: 12px; color: var(--text-secondary);
}
.file-chip button {
    background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 14px;
    padding: 0; line-height: 1;
}
.file-chip button:hover { color: #f87171; }
.file-chip-pending { border-style: dashed; color: var(--text-faint); }
.no-files { font-size: 12px; color: var(--border-hover); }

.drop-area {
    border: 1px dashed var(--border); border-radius: 8px;
    padding: 14px; text-align: center; transition: all 0.15s;
}
.drop-area.over { border-color: #3b82f6; background: rgba(59,130,246,0.04); }
.drop-label { font-size: 12px; color: var(--text-faint); }
.link-btn {
    background: none; border: none; color: #3b82f6;
    cursor: pointer; font-size: 12px; text-decoration: underline;
}

.btn-xs {
    padding: 5px 12px; font-size: 11px;
    background: var(--bg-elevated); color: var(--text-muted);
    border: 1px solid var(--border); border-radius: 5px; cursor: pointer;
}
.btn-xs:hover { color: var(--text-secondary); border-color: var(--border-hover); }

/* Folder thumbnail */
.folder-thumb-row { display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin-top: 4px; }
.folder-thumb-preview { position: relative; }
.folder-thumb-preview img { width: 100px; border-radius: 8px; border: 1px solid var(--border); }
.folder-thumb-remove {
    position: absolute; top: -6px; right: -6px;
    width: 20px; height: 20px; border-radius: 50%;
    background: #ef4444; color: #fff; border: none;
    cursor: pointer; font-size: 14px; line-height: 1;
    display: flex; align-items: center; justify-content: center;
}
.folder-thumb-empty { font-size: 12px; color: var(--text-faint); }
.folder-thumb-actions { display: flex; flex-direction: column; gap: 6px; }
</style>
