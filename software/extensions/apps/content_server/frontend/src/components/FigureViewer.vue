<template>
    <div class="figure-viewer" v-if="item">
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
                    <span class="item-type-badge figures">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                            <circle cx="8.5" cy="8.5" r="1.5"/>
                            <polyline points="21 15 16 10 5 21"/>
                        </svg>
                        Figure{{ item.figures?.length > 1 ? 's' : '' }}
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

        <div class="figure-container">
            <div class="figure-main">
                <div class="main-figure" v-if="currentFigure">
                    <div class="figure-label">{{ currentFigure.name }}</div>
                    <img
                        :src="`/figures/${currentFigure.file}`"
                        :alt="currentFigure.name"
                        @click="openFullscreen"
                    >
                    <div class="figure-hint">Click to view fullscreen</div>
                </div>
            </div>
            <div class="figure-sidebar" v-if="item.figures && item.figures.length > 1">
                <div class="sidebar-header">
                    <span>Figures</span>
                    <span class="figure-count">{{ selectedIndex + 1 }} / {{ item.figures.length }}</span>
                </div>
                <div class="figure-thumbnails">
                    <div
                        v-for="(figure, index) in item.figures"
                        :key="index"
                        class="figure-thumbnail"
                        :class="{ active: index === selectedIndex }"
                        @click="selectFigure(index)"
                    >
                        <img :src="`/figures/${figure.file}`" :alt="figure.name">
                        <div class="thumbnail-label">{{ figure.name }}</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Fullscreen overlay -->
        <div class="fullscreen-overlay" v-if="isFullscreen" @click="closeFullscreen">
            <button class="close-btn" @click="closeFullscreen">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
            </button>
            <div class="fullscreen-nav" v-if="item.figures.length > 1">
                <button class="nav-btn prev" @click.stop="prevFigure" :disabled="selectedIndex <= 0">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M15 18l-6-6 6-6"/>
                    </svg>
                </button>
                <button class="nav-btn next" @click.stop="nextFigure" :disabled="selectedIndex >= item.figures.length - 1">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M9 18l6-6-6-6"/>
                    </svg>
                </button>
            </div>
            <img
                v-if="currentFigure"
                :src="`/figures/${currentFigure.file}`"
                :alt="currentFigure.name"
                @click.stop
            >
            <div class="fullscreen-label" v-if="currentFigure">{{ currentFigure.name }}</div>
        </div>
    </div>

    <div v-else class="loading">
        Loading figures...
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import DocRefBadge from './DocRefBadge.vue'
import InfoPanel from './InfoPanel.vue'

const showInfo = ref(false)

const props = defineProps({
    id: String
})

const router = useRouter()
const item = ref(null)
const selectedIndex = ref(0)
const isFullscreen = ref(false)

async function loadItem() {
    item.value = null
    selectedIndex.value = 0
    isFullscreen.value = false
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

const currentFigure = computed(() => {
    return item.value?.figures?.[selectedIndex.value]
})

function goBack() {
    if (item.value?.folderPath && item.value.folderPath.length > 0) {
        const parent = item.value.folderPath[item.value.folderPath.length - 1]
        router.push(`/folder/${parent.id}`)
    } else {
        router.push('/')
    }
}

function selectFigure(index) {
    selectedIndex.value = index
}

function prevFigure() {
    if (selectedIndex.value > 0) {
        selectedIndex.value--
    }
}

function nextFigure() {
    if (item.value?.figures && selectedIndex.value < item.value.figures.length - 1) {
        selectedIndex.value++
    }
}

function openFullscreen() {
    isFullscreen.value = true
}

function closeFullscreen() {
    isFullscreen.value = false
}

function handleKeydown(event) {
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA' || event.target.tagName === 'SELECT' || event.target.isContentEditable) return

    if (event.code === 'Escape' && isFullscreen.value) {
        closeFullscreen()
    } else if (event.code === 'ArrowLeft') {
        prevFigure()
    } else if (event.code === 'ArrowRight') {
        nextFigure()
    } else if (event.code === 'Enter' || event.code === 'Space') {
        if (isFullscreen.value) {
            closeFullscreen()
        } else {
            openFullscreen()
        }
    }
}

onMounted(async () => {
    await loadItem()
    window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
    window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.figure-viewer {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

.viewer-header {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
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

.item-type-badge.figures {
    background: rgba(168, 85, 247, 0.15);
    color: #c084fc;
    border: 1px solid rgba(168, 85, 247, 0.3);
}

.item-description {
    color: var(--text-muted);
    font-size: 14px;
    margin-top: 8px;
}

.figure-container {
    flex: 1;
    display: flex;
    gap: 16px;
    min-height: 0;
    overflow: hidden;
}

.figure-main {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--code-bg);
    border-radius: 12px;
    overflow: hidden;
    min-width: 0;
}

.main-figure {
    position: relative;
    max-width: 100%;
    max-height: 100%;
    padding: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.main-figure img {
    max-width: 100%;
    max-height: calc(100vh - 300px);
    object-fit: contain;
    border-radius: 8px;
    cursor: pointer;
    transition: transform 0.2s;
}

.main-figure img:hover {
    transform: scale(1.01);
}

.figure-label {
    position: absolute;
    top: 32px;
    left: 32px;
    background: var(--overlay);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
}

.figure-hint {
    margin-top: 12px;
    font-size: 12px;
    color: var(--text-faint);
}

.figure-sidebar {
    width: 200px;
    background: var(--code-bg);
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    flex-shrink: 0;
}

.sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    font-weight: 500;
}

.figure-count {
    color: var(--text-muted);
}

.figure-thumbnails {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.figure-thumbnail {
    position: relative;
    background: var(--bg-elevated);
    border: 2px solid transparent;
    border-radius: 8px;
    cursor: pointer;
    overflow: hidden;
    transition: border-color 0.2s;
}

.figure-thumbnail:hover {
    border-color: var(--border-hover);
}

.figure-thumbnail.active {
    border-color: #a855f7;
}

.figure-thumbnail img {
    width: 100%;
    height: auto;
    display: block;
}

.thumbnail-label {
    padding: 8px;
    font-size: 11px;
    color: var(--text-muted);
    background: linear-gradient(to top, rgba(0,0,0,0.8), transparent);
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
}

/* Fullscreen overlay */
.fullscreen-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.95);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
}

.fullscreen-overlay img {
    max-width: 90vw;
    max-height: 90vh;
    object-fit: contain;
    cursor: default;
}

.close-btn {
    position: absolute;
    top: 20px;
    right: 20px;
    background: rgba(255, 255, 255, 0.1);
    border: none;
    color: white;
    padding: 12px;
    border-radius: 50%;
    cursor: pointer;
    transition: background 0.2s;
    z-index: 1001;
}

.close-btn:hover {
    background: rgba(255, 255, 255, 0.2);
}

.fullscreen-nav {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    pointer-events: none;
}

.nav-btn {
    background: rgba(255, 255, 255, 0.1);
    border: none;
    color: white;
    padding: 16px;
    border-radius: 50%;
    cursor: pointer;
    transition: background 0.2s;
    pointer-events: auto;
}

.nav-btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.2);
}

.nav-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
}

.fullscreen-label {
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--overlay);
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 500;
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}
</style>
