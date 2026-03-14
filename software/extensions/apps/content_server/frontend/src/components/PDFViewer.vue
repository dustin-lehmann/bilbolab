<template>
    <div class="pdf-viewer" v-if="item">
        <div class="viewer-header">
            <div class="nav-section">
                <button v-if="item.folderPath && item.folderPath.length > 0" class="back-btn" @click="goBack">
                    &larr; Back
                </button>
                <router-link v-else to="/" class="back-btn">&larr; Home</router-link>

                <div class="breadcrumb">
                    <router-link to="/" class="breadcrumb-item">Home</router-link>
                    <template v-for="(crumb, index) in item.folderPath" :key="crumb.id">
                        <span class="breadcrumb-sep">/</span>
                        <router-link :to="`/folder/${crumb.id}`" class="breadcrumb-item">
                            {{ crumb.name }}
                        </router-link>
                    </template>
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item current">{{ item.title }}</span>
                </div>
            </div>
            <div class="header-info">
                <div class="title-row">
                    <h1 class="item-title">{{ item.title }}</h1>
                    <span class="item-type-badge pdf">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/>
                        </svg>
                        PDF Document
                    </span>
                </div>
                <p class="item-description">{{ item.description }}</p>
                <div class="header-extras">
                    <DocRefBadge :item="item" />
                    <button v-if="item.additionalInfo" class="info-btn" @click="showInfo = true">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                        More Information
                    </button>
                </div>
                <InfoPanel :visible="showInfo" :content="item.additionalInfo || ''" @close="showInfo = false" />
            </div>
        </div>

        <div class="pdf-container">
            <div class="pdf-toolbar">
                <a :href="`/pdfs/${item.file}`" download class="toolbar-btn" title="Download PDF">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download
                </a>
                <a :href="`/pdfs/${item.file}`" target="_blank" class="toolbar-btn" title="Open in new tab">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                    Open in New Tab
                </a>
            </div>
            <div class="pdf-embed-container">
                <iframe
                    :src="`/pdfs/${item.file}`"
                    class="pdf-iframe"
                    type="application/pdf"
                ></iframe>
            </div>
        </div>
    </div>

    <div v-else class="loading">
        Loading document...
    </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import DocRefBadge from './DocRefBadge.vue'
import InfoPanel from './InfoPanel.vue'

const showInfo = ref(false)

const props = defineProps({
    id: String
})

const router = useRouter()
const item = ref(null)

function goBack() {
    if (item.value?.folderPath && item.value.folderPath.length > 0) {
        const parent = item.value.folderPath[item.value.folderPath.length - 1]
        router.push(`/folder/${parent.id}`)
    } else {
        router.push('/')
    }
}

async function loadItem() {
    item.value = null
    try {
        const response = await fetch(`/api/experiments/${props.id}`)
        item.value = await response.json()
    } catch (error) {
        console.error('Failed to load item:', error)
    }
}

// Watch for id changes
watch(() => props.id, () => {
    loadItem()
})

onMounted(async () => {
    await loadItem()
})
</script>

<style scoped>
.pdf-viewer {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

.viewer-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 12px;
    flex-shrink: 0;
}

.nav-section {
    display: flex;
    align-items: center;
    gap: 8px;
}

.breadcrumb {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    flex-wrap: wrap;
}

.breadcrumb-sep {
    color: var(--border-hover);
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

.item-type-badge.pdf {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
}

.item-description {
    color: var(--text-muted);
    font-size: 13px;
    margin-top: 4px;
}

.pdf-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--code-bg);
    border-radius: 12px;
    overflow: hidden;
}

.pdf-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
}

.toolbar-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    color: var(--text-primary);
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    text-decoration: none;
    font-size: 14px;
    transition: all 0.2s;
}

.toolbar-btn:hover {
    background: var(--border);
    border-color: var(--border-hover);
}

.pdf-embed-container {
    flex: 1;
    min-height: 0;
}

.pdf-iframe {
    width: 100%;
    height: 100%;
    border: none;
    background: var(--text-primary);
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}
</style>
