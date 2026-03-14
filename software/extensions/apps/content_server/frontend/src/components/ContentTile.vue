<template>
    <component
        :is="tag"
        v-bind="linkProps"
        class="content-tile"
        :class="[
            `type-${displayType}`,
            viewMode,
            { 'edit-mode': editMode, 'is-folder': isFolder }
        ]"
    >
        <div class="tile-thumbnail">
            <img
                v-if="thumbnailSrc"
                :src="thumbnailSrc"
                :alt="title"
                @error="onImageError"
            >
            <img
                v-else
                :src="defaultThumbnail"
                :alt="displayType"
                class="default-thumb"
            >
        </div>
        <div class="tile-info">
            <div class="tile-top-row">
                <!-- Folder: show count badges based on folderCountStyle setting -->
                <template v-if="isFolder && folderCountStyle !== 'total'">
                    <span
                        v-for="cat in folderCategoryCounts"
                        :key="cat.type"
                        class="type-badge"
                        :class="cat.type"
                        :title="cat.label"
                    >
                        <component :is="iconForType(cat.type)" />
                        {{ cat.count }}{{ folderCountStyle === 'detailed' ? ' ' + cat.label : '' }}
                    </span>
                </template>
                <!-- Non-folder or total mode -->
                <span v-else class="type-badge" :class="displayType">
                    <component :is="badgeIconComponent" />
                    {{ badgeText }}
                </span>
            </div>
            <h3 class="tile-title">{{ title }}</h3>
            <p v-if="description" class="tile-description">{{ description }}</p>
            <div class="tile-bottom-row">
                <span v-if="docRef" class="tile-docref" :title="docRefFull">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
                    {{ docRef }}
                </span>
                <span v-if="date" class="tile-date">{{ date }}</span>
                <span v-if="metaInfo" class="tile-meta">{{ metaInfo }}</span>
                <span v-if="!editMode" class="tile-action">{{ isFolder ? 'Open' : 'View' }} &rarr;</span>
            </div>
        </div>
    </component>
</template>

<script setup>
import { computed, h, inject } from 'vue'

const settings = inject('settings')

const props = defineProps({
    item: { type: Object, required: true },
    isFolder: { type: Boolean, default: false },
    viewMode: { type: String, default: 'grid' }, // 'grid' or 'list'
    editMode: { type: Boolean, default: false },
    noLink: { type: Boolean, default: false },
})

const title = computed(() => props.isFolder ? props.item.name : props.item.title)
const description = computed(() => props.item.description || '')
const date = computed(() => props.item.date || '')
const displayType = computed(() => {
    if (props.isFolder) return 'folder'
    return props.item.type || 'synchronized'
})

const tag = computed(() => (props.editMode || props.noLink) ? 'div' : 'router-link')
const linkProps = computed(() => {
    if (props.editMode || props.noLink) return {}
    if (props.isFolder) return { to: `/folder/${props.item.id}` }
    return { to: getItemRoute(props.item) }
})

const thumbnailSrc = computed(() => {
    if (props.item.thumbnail) return `/thumbnails/${props.item.thumbnail}`
    return null
})

const defaultThumbnail = computed(() => {
    const type = displayType.value
    return `/tour/${type}.svg`
})

function onImageError(event) {
    // Fall back to default thumbnail
    event.target.src = defaultThumbnail.value
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

const badgeText = computed(() => {
    if (props.isFolder) {
        const count = countElements(props.item)
        return `${count} ${count === 1 ? 'element' : 'elements'}`
    }
    const item = props.item
    const type = item.type || 'synchronized'
    const videoCount = item.videos?.length || 0
    const figureCount = item.figures?.length || 0
    if (type === 'video') return 'Video'
    if (type === 'synchronized') return `${videoCount} ${videoCount === 1 ? 'video' : 'videos'}`
    if (type === 'collection') return `${videoCount} ${videoCount === 1 ? 'clip' : 'clips'}`
    if (type === 'pdf') return 'PDF'
    if (type === 'figures') return `${figureCount} ${figureCount === 1 ? 'figure' : 'figures'}`
    if (type === 'code') return item.language || 'Code'
    if (type === 'interactive') return 'Interactive'
    if (type === 'model3d') return '3D Model'
    return type
})

const metaInfo = computed(() => {
    if (props.isFolder) return ''
    const item = props.item
    const type = item.type || 'synchronized'
    if (type === 'video') return ''
    if (type === 'synchronized') return ''
    if (type === 'collection') return 'Comparison'
    if (type === 'pdf') return 'Document'
    if (type === 'figures') return 'Gallery'
    if (type === 'code') return 'Snippet'
    if (type === 'interactive') return 'Interactive'
    if (type === 'model3d') return '3D Model'
    return ''
})

const docRef = computed(() => {
    if (props.isFolder) return ''
    const item = props.item
    const ch = item.chapter || ''
    const sec = item.section ? `${ch}.${item.section}` : ''
    const sub = item.subsection ? `${sec}.${item.subsection}` : ''
    const fullNum = sub || sec || ch
    if (!fullNum && !item.page) return ''
    let ref = fullNum ? `Sec.\u2009${fullNum}` : ''
    if (item.page) ref += ref ? `, p.\u2009${item.page}` : `p.\u2009${item.page}`
    return ref
})

const docRefFull = computed(() => {
    if (props.isFolder) return ''
    const item = props.item
    const parts = []
    if (item.chapter) parts.push(`Chapter ${item.chapter}`)
    if (item.section) parts.push(`Section ${item.section}`)
    if (item.subsection) parts.push(`Subsection ${item.subsection}`)
    if (item.page) parts.push(`Page ${item.page}`)
    return parts.join(', ')
})

function countElements(folder) {
    let count = folder.experiments?.length || 0
    if (folder.folders) {
        for (const subfolder of folder.folders) {
            count += countElements(subfolder)
        }
    }
    return count
}

// --- Folder category count modes ---

const folderCountStyle = computed(() => settings?.value?.folderCountStyle || 'total')

const typeLabels = {
    video: { singular: 'Video', plural: 'Videos' },
    synchronized: { singular: 'Sync Video', plural: 'Sync Videos' },
    collection: { singular: 'Collection', plural: 'Collections' },
    pdf: { singular: 'PDF', plural: 'PDFs' },
    figures: { singular: 'Figures', plural: 'Figures' },
    code: { singular: 'Code', plural: 'Code' },
    interactive: { singular: 'Interactive', plural: 'Interactive' },
    model3d: { singular: '3D Model', plural: '3D Models' },
}

function countByType(folder, type) {
    let count = 0
    if (folder.experiments) {
        for (const exp of folder.experiments) {
            if ((exp.type || 'synchronized') === type) count++
        }
    }
    if (folder.folders) {
        for (const sub of folder.folders) {
            count += countByType(sub, type)
        }
    }
    return count
}

const folderCategoryCounts = computed(() => {
    if (!props.isFolder) return []
    const types = ['video', 'synchronized', 'collection', 'pdf', 'figures', 'code', 'interactive', 'model3d']
    const results = []
    for (const t of types) {
        const c = countByType(props.item, t)
        if (c > 0) {
            const labels = typeLabels[t] || { singular: t, plural: t }
            results.push({
                type: t,
                count: c,
                label: c === 1 ? labels.singular : labels.plural,
            })
        }
    }
    return results
})

// Badge icon as a render function component
const badgeIconComponent = computed(() => {
    const type = displayType.value
    const icons = {
        folder: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'currentColor', innerHTML: '<path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>' }),
        video: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.5', innerHTML: '<polygon points="5 3 19 12 5 21 5 3"/>' }),
        synchronized: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.5', innerHTML: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>' }),
        collection: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'currentColor', innerHTML: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>' }),
        pdf: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'currentColor', innerHTML: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/>' }),
        figures: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', innerHTML: '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>' }),
        code: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', innerHTML: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>' }),
        interactive: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', innerHTML: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>' }),
        model3d: () => h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', innerHTML: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>' }),
    }
    return icons[type] || icons.synchronized
})

function iconForType(type) {
    const icons = {
        video: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.5', innerHTML: '<polygon points="5 3 19 12 5 21 5 3"/>' }),
        synchronized: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.5', innerHTML: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>' }),
        collection: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'currentColor', innerHTML: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>' }),
        pdf: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'currentColor', innerHTML: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' }),
        figures: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', innerHTML: '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>' }),
        code: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2.5', innerHTML: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>' }),
        interactive: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', innerHTML: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>' }),
        model3d: () => h('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', innerHTML: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>' }),
    }
    return icons[type] || icons.synchronized
}
</script>

<style scoped>
.content-tile {
    display: flex;
    flex-direction: row;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    text-decoration: none;
    color: inherit;
    transition: all 0.2s ease;
    overflow: hidden;
    cursor: pointer;
}

.content-tile:hover {
    border-color: #3b82f6;
    transform: translateY(-2px);
}

.content-tile.edit-mode {
    cursor: default;
}

.content-tile.edit-mode:hover {
    transform: none;
}

/* ── Type-colored left border ── */
.content-tile.type-folder { border-left: 3px solid #6b7280; }
.content-tile.type-video { border-left: 3px solid #8b5cf6; }
.content-tile.type-synchronized { border-left: 3px solid #3b82f6; }
.content-tile.type-collection { border-left: 3px solid #f59e0b; }
.content-tile.type-pdf { border-left: 3px solid #ef4444; }
.content-tile.type-figures { border-left: 3px solid #a855f7; }
.content-tile.type-code { border-left: 3px solid #06b6d4; }
.content-tile.type-interactive { border-left: 3px solid #22c55e; }
.content-tile.type-model3d { border-left: 3px solid #0ea5e9; }

/* ── Grid view ── */
.content-tile.grid {
    width: 100%;
    height: 160px;
}

.content-tile.grid .tile-thumbnail {
    width: 130px;
    min-width: 130px;
    height: 100%;
}

/* ── List view ── */
.content-tile.list {
    width: 100%;
    height: 100px;
}

.content-tile.list .tile-thumbnail {
    width: 130px;
    min-width: 130px;
    height: 100%;
}

.content-tile.list .tile-title {
    font-size: 15px;
}

.content-tile.list .tile-description {
    -webkit-line-clamp: 1;
}

/* ── Thumbnail ── */
.tile-thumbnail {
    flex-shrink: 0;
    overflow: hidden;
    background: var(--code-bg);
    display: flex;
    align-items: center;
    justify-content: center;
}

.tile-thumbnail img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.tile-thumbnail img.default-thumb {
    object-fit: contain;
    padding: 8px;
    opacity: 0.6;
}

/* ── Info area ── */
.tile-info {
    flex: 1;
    min-width: 0;
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    overflow: hidden;
}

.tile-top-row {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 4px;
    flex-wrap: wrap;
}

.tile-title {
    font-size: 16px;
    font-weight: 600;
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
}

.tile-description {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.4;
    margin: 2px 0 0;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}

.tile-bottom-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: auto;
    padding-top: 4px;
}

.tile-docref {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    color: var(--text-muted);
    background: var(--accent-muted);
    padding: 1px 6px;
    border-radius: 4px;
    flex-shrink: 0;
}

.tile-date {
    font-size: 11px;
    color: var(--text-faint);
}

.tile-meta {
    font-size: 11px;
    color: var(--text-faint);
}

.tile-action {
    margin-left: auto;
    font-size: 12px;
    color: #3b82f6;
    font-weight: 500;
}

/* ── Type badges ── */
.type-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 12px;
    font-weight: 500;
    font-size: 11px;
    flex-shrink: 0;
}

.type-badge.folder { background: rgba(107, 114, 128, 0.2); color: #9ca3af; }
.type-badge.video { background: #8b5cf6; color: white; }
.type-badge.synchronized { background: #3b82f6; color: white; }
.type-badge.collection { background: #f59e0b; color: white; }
.type-badge.pdf { background: #ef4444; color: white; }
.type-badge.figures { background: #a855f7; color: white; }
.type-badge.code { background: #06b6d4; color: white; }
.type-badge.interactive { background: #22c55e; color: white; }
.type-badge.model3d { background: #0ea5e9; color: white; }
</style>
