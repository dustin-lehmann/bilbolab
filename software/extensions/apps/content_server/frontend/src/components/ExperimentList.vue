<template>
    <div class="experiment-list">
        <div class="page-header">
            <div>
                <h1 class="page-title">{{ settings.homeTitle || 'Additional Material' }}</h1>
                <p class="page-subtitle">{{ settings.homeSubtitle || 'Browse chapters and sections' }}</p>
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
        </div>

        <!-- Accordion Style Folders -->
        <div v-if="settings.folderStyle === 'accordion' && folders.length > 0" class="section">
            <div class="content-layout" :class="viewMode">
                <div
                    v-for="folder in folders"
                    :key="folder.id"
                    class="accordion-wrapper"
                    :class="{ expanded: expandedFolder === folder.id }"
                >
                    <div class="tile-wrapper" @click="toggleFolder(folder.id)">
                        <ContentTile :item="folder" :is-folder="true" :view-mode="viewMode" :no-link="true" />
                    </div>

                    <div v-if="expandedFolder === folder.id" class="accordion-content" @click.stop>
                        <div class="content-layout" :class="viewMode">
                            <div v-for="exp in folder.experiments" :key="exp.id" class="tile-wrapper" :data-tour-item="exp.id">
                                <ContentTile :item="exp" :view-mode="viewMode" />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Navigation Style Folders -->
        <div v-if="settings.folderStyle === 'navigation' && folders.length > 0" class="section">
            <div class="content-layout" :class="viewMode">
                <div v-for="folder in folders" :key="folder.id" class="tile-wrapper">
                    <ContentTile :item="folder" :is-folder="true" :view-mode="viewMode" />
                </div>
            </div>
        </div>

        <!-- Standalone Experiments (after navigation folders) -->
        <div v-if="experiments.length > 0" class="section">
            <h2 v-if="folders.length > 0" class="section-title">Other Content</h2>
            <div class="content-layout" :class="viewMode">
                <div v-for="exp in experiments" :key="exp.id" class="tile-wrapper" :data-tour-item="exp.id">
                    <ContentTile :item="exp" :view-mode="viewMode" />
                </div>
            </div>
        </div>

        <div v-if="folders.length === 0 && experiments.length === 0" class="empty-state">
            <p>No experiments found. Add experiments to experiments.json</p>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted, inject, watch } from 'vue'
import { useViewMode } from '../composables/useViewMode.js'
import ContentTile from './ContentTile.vue'

const settings = inject('settings')
const tourExpandFolder = inject('tourExpandFolder', ref(null))
const { viewMode, toggle } = useViewMode()
const folders = ref([])
const experiments = ref([])
const expandedFolder = ref(null)

// Watch for tour-driven folder expansion (accordion mode)
watch(tourExpandFolder, (folderId) => {
    if (folderId && settings.value.folderStyle === 'accordion') {
        expandedFolder.value = folderId
    }
})

function toggleFolder(folderId) {
    expandedFolder.value = expandedFolder.value === folderId ? null : folderId
}

onMounted(async () => {
    try {
        const response = await fetch('/api/experiments')
        const data = await response.json()
        folders.value = data.folders || []
        experiments.value = data.experiments || []
    } catch (error) {
        console.error('Failed to load experiments:', error)
    }
})
</script>

<style scoped>
.experiment-list {
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}

.page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 32px;
}

.page-title {
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 8px;
}

.page-subtitle {
    color: var(--text-muted);
    margin: 0;
}

/* ── View toggle ── */
.view-toggle {
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
    flex-shrink: 0;
    margin-top: 8px;
}

.view-toggle:hover {
    border-color: var(--border-hover);
    color: var(--text-primary);
}

/* ── Sections ── */
.section {
    margin-bottom: 28px;
}

.section-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 16px;
}

/* ── Content layout ── */
.content-layout.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
}

.content-layout.list {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.tile-wrapper {
    min-width: 0;
}

/* ── Accordion ── */
.accordion-wrapper {
    display: flex;
    flex-direction: column;
}

.accordion-wrapper > .tile-wrapper {
    cursor: pointer;
}

.accordion-wrapper.expanded {
    grid-column: 1 / -1;
}

.accordion-content {
    margin-top: 12px;
    padding: 16px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 10px;
}

.accordion-content .content-layout.grid {
    grid-template-columns: repeat(3, 1fr);
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 60px;
    color: var(--text-faint);
}

@media (max-width: 900px) {
    .content-layout.grid {
        grid-template-columns: repeat(2, 1fr);
    }
    .accordion-content .content-layout.grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 600px) {
    .content-layout.grid {
        grid-template-columns: 1fr;
    }
    .accordion-content .content-layout.grid {
        grid-template-columns: 1fr;
    }
}
</style>
