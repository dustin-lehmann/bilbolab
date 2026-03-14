<template>
    <div class="edit-page" v-if="item">
        <div class="edit-header">
            <div class="edit-header-left">
                <router-link to="/admin/folders" class="back-link">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
                    Back
                </router-link>
                <h1>{{ item.title || 'Edit Item' }}</h1>
                <span class="item-type-pill">{{ item.type }}</span>
            </div>
            <div class="edit-header-right">
                <a :href="previewUrl" target="_blank" class="btn btn-ghost">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    Preview
                </a>
                <button class="btn btn-primary" @click="save" :disabled="saving || !form.title.trim()">
                    {{ saving ? 'Saving...' : 'Save Changes' }}
                </button>
            </div>
        </div>

        <div v-if="saved" class="save-toast">Saved</div>

        <ItemEditForm :form="form" :available-files="availableFiles" show-thumbnail
            @generate-thumbnail="generateThumbnail" @upload-thumbnail="uploadThumbnail"
            :generating-thumbnail="generatingThumb">
            <template #files>
                <div class="edit-card">
                    <h3>Files</h3>
                    <div class="file-chips">
                        <span v-for="f in files" :key="f" class="file-chip">
                            {{ f }}
                            <button @click="removeFile(f)">&times;</button>
                        </span>
                        <span v-for="(f, i) in pending" :key="'p'+i" class="file-chip file-chip-pending">
                            {{ f.name }}
                            <button @click="pending.splice(i, 1)">&times;</button>
                        </span>
                        <span v-if="files.length === 0 && pending.length === 0" class="no-files">No files</span>
                    </div>
                    <div class="drop-area" :class="{over: dragover}" @dragover.prevent="dragover=true" @dragleave="dragover=false" @drop.prevent="handleDrop">
                        <input type="file" multiple ref="fileInput" @change="handleFileSelect" style="display:none">
                        <span class="drop-label">Drop files or <button class="link-btn" @click="$refs.fileInput.click()">browse</button></span>
                    </div>
                </div>
            </template>
        </ItemEditForm>
    </div>
    <div v-else class="loading">Loading item...</div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '../../composables/useApi.js'
import ItemEditForm from './ItemEditForm.vue'
import { itemFormFromData } from './itemFormHelpers.js'

const route = useRoute()
const router = useRouter()
const { adminGet, adminPut, adminPost, adminDelete: adminDel } = useApi()

const item = ref(null)
const form = ref({})
const files = ref([])
const pending = ref([])
const dragover = ref(false)
const saving = ref(false)
const saved = ref(false)
const generatingThumb = ref(false)

const availableFiles = computed(() => {
    const all = [...files.value, ...pending.value.map(f => f.name)]
    return [...new Set(all)]
})

const previewUrl = computed(() => {
    if (!item.value) return '/'
    const t = item.value.type || 'synchronized'
    if (t === 'pdf') return `/pdf/${item.value.id}`
    if (t === 'figures') return `/figures/${item.value.id}`
    if (t === 'code') return `/code/${item.value.id}`
    if (t === 'video') return `/video/${item.value.id}`
    return `/experiment/${item.value.id}`
})

async function loadItem() {
    const id = route.params.id
    const data = await adminGet(`/api/admin/items/${id}`)
    if (!data || data.error) {
        router.push('/admin/folders')
        return
    }
    item.value = data
    form.value = itemFormFromData(data)
    files.value = data.files || []
}

async function save() {
    saving.value = true
    const id = item.value.id
    await adminPut(`/api/admin/items/${id}`, form.value)
    if (pending.value.length) {
        const fd = new FormData()
        for (const f of pending.value) fd.append('file', f)
        await adminPost(`/api/admin/items/${id}/files`, fd)
        pending.value = []
    }
    // Reload to get updated file list
    await loadItem()
    saving.value = false
    saved.value = true
    setTimeout(() => saved.value = false, 2000)
}

async function removeFile(filename) {
    const id = item.value.id
    await adminDel(`/api/admin/items/${id}/files/${filename}`)
    files.value = files.value.filter(f => f !== filename)
}

function handleDrop(e) {
    dragover.value = false
    if (e.dataTransfer.files.length) pending.value.push(...e.dataTransfer.files)
}

function handleFileSelect(e) {
    if (e.target.files.length) pending.value.push(...e.target.files)
    e.target.value = ''
}

async function generateThumbnail() {
    const id = item.value?.id
    if (!id) return
    generatingThumb.value = true
    try {
        const res = await adminPost(`/api/admin/thumbnails/${id}/generate`, {})
        if (res?.thumbnail) {
            form.value.thumbnail = res.thumbnail
        }
    } catch (e) {
        console.error('Failed to generate thumbnail:', e)
    }
    generatingThumb.value = false
}

async function uploadThumbnail(file) {
    const id = item.value?.id
    if (!id || !file) return
    const fd = new FormData()
    fd.append('file', file)
    try {
        const res = await adminPost(`/api/admin/thumbnails/${id}`, fd)
        if (res?.thumbnail) {
            form.value.thumbnail = res.thumbnail
        }
    } catch (e) {
        console.error('Failed to upload thumbnail:', e)
    }
}

onMounted(loadItem)
</script>

<style scoped>
.edit-page {
    padding: 0;
    max-width: 1200px;
}

.edit-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 12px;
}

.edit-header-left {
    display: flex;
    align-items: center;
    gap: 12px;
}

.edit-header-left h1 {
    font-size: 20px;
    font-weight: 600;
    margin: 0;
}

.back-link {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 13px;
    padding: 6px 10px;
    border-radius: 6px;
    transition: all 0.15s;
}

.back-link:hover {
    background: var(--bg-button-hover);
    color: var(--text-primary);
}

.item-type-pill {
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    font-weight: 500;
    text-transform: capitalize;
}

.edit-header-right {
    display: flex;
    gap: 8px;
    align-items: center;
}

.save-toast {
    position: fixed;
    top: 20px;
    right: 20px;
    background: #22c55e;
    color: #fff;
    padding: 10px 20px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    z-index: 1000;
    animation: toast-in 0.3s ease;
}

@keyframes toast-in {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Buttons */
.btn {
    padding: 8px 16px;
    border-radius: 7px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: none;
    transition: all 0.15s;
}
.btn-primary { background: #3b82f6; color: #fff; }
.btn-primary:hover { background: #2563eb; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost {
    background: var(--bg-elevated, #1e1e2e);
    color: var(--text-secondary);
    border: 1px solid var(--border);
    text-decoration: none;
}
.btn-ghost:hover { background: var(--bg-button-hover); color: var(--text-primary); }

/* File management card */
.edit-card {
    background: var(--bg-card, #1e1e2e);
    border: 1px solid var(--border, #2a2a3e);
    border-radius: 10px;
    padding: 18px 20px;
}

.edit-card h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 0 0 14px;
    color: var(--text-primary);
}

/* Files */
.file-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.file-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; background: var(--bg-elevated); border: 1px solid var(--bg-button-hover);
    border-radius: 6px; font-size: 12px; color: var(--text-secondary);
}
.file-chip button { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 14px; padding: 0; }
.file-chip button:hover { color: #f87171; }
.file-chip-pending { border-style: dashed; color: var(--text-faint); }
.no-files { font-size: 12px; color: var(--border-hover); }

.drop-area {
    border: 1px dashed var(--border); border-radius: 8px;
    padding: 12px; text-align: center; transition: all 0.15s;
}
.drop-area.over { border-color: #3b82f6; background: rgba(59,130,246,0.04); }
.drop-label { font-size: 12px; color: var(--text-faint); }
.link-btn { background: none; border: none; color: #3b82f6; cursor: pointer; font-size: 12px; text-decoration: underline; }

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}
</style>
