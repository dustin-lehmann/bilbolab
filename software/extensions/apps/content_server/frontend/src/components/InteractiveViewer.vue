<template>
    <div class="interactive-viewer" v-if="item">
        <div class="viewer-header">
            <div class="nav-section">
                <button class="back-btn" @click="$router.back()">&larr; Back</button>
                <div class="breadcrumb" v-if="item.breadcrumb">
                    <router-link to="/" class="breadcrumb-item">Home</router-link>
                    <template v-for="crumb in item.breadcrumb" :key="crumb.id">
                        <span class="breadcrumb-sep">/</span>
                        <router-link :to="`/folder/${crumb.id}`" class="breadcrumb-item">{{ crumb.name }}</router-link>
                    </template>
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item current">{{ item.title }}</span>
                </div>
            </div>
            <div class="header-info">
                <div class="title-row">
                    <h1 class="item-title">{{ item.title }}</h1>
                    <span class="item-type-badge">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                        </svg>
                        Interactive
                    </span>
                </div>
                <p class="item-description" v-if="item.description">{{ item.description }}</p>
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

        <div class="interactive-content">
            <div class="interactive-placeholder">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                    <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                    <line x1="12" y1="22.08" x2="12" y2="12"/>
                </svg>
                <p class="placeholder-text">Interactive content will be rendered here</p>
                <p class="placeholder-hint">Simulations, 3D models, and interactive visualizations</p>
            </div>
        </div>
    </div>

    <div v-else class="loading">Loading...</div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import DocRefBadge from './DocRefBadge.vue'
import InfoPanel from './InfoPanel.vue'

const showInfo = ref(false)

const props = defineProps({ id: String })
const route = useRoute()
const item = ref(null)

async function loadItem(itemId) {
    try {
        const response = await fetch(`/api/experiments/${itemId}`)
        item.value = await response.json()
    } catch (error) {
        console.error('Failed to load interactive item:', error)
    }
}

loadItem(props.id)

watch(() => route.params.id, (newId) => {
    if (newId) loadItem(newId)
})
</script>

<style scoped>
.interactive-viewer {
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
.breadcrumb-sep { color: var(--border-hover); }

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
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.3);
}
.item-description {
    color: var(--text-muted);
    font-size: 14px;
    margin-top: 8px;
}

.interactive-content {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
}

.interactive-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 60px;
    border: 2px dashed var(--border);
    border-radius: 16px;
    color: #22c55e;
    width: 100%;
    max-width: 800px;
    min-height: 400px;
}

.placeholder-text {
    font-size: 18px;
    font-weight: 500;
    color: var(--text-faint);
}

.placeholder-hint {
    font-size: 13px;
    color: var(--border-hover);
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}
</style>
