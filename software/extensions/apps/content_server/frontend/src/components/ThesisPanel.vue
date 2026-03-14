<template>
    <Teleport to="body">
        <Transition name="thesis-panel">
            <div v-if="visible" class="thesis-panel-overlay" @click.self="close">
                <div class="thesis-panel">
                    <div class="thesis-panel-header">
                        <span class="thesis-panel-title">{{ documentLabel }}</span>
                        <span v-if="page" class="thesis-panel-page">Page {{ page }}</span>
                        <div class="thesis-panel-actions">
                            <a :href="fullUrl" target="_blank" rel="noopener" class="thesis-panel-btn" title="Open in new tab">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                                    <polyline points="15 3 21 3 21 9"/>
                                    <line x1="10" y1="14" x2="21" y2="3"/>
                                </svg>
                            </a>
                            <button class="thesis-panel-btn" @click="close" title="Close">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <line x1="18" y1="6" x2="6" y2="18"/>
                                    <line x1="6" y1="6" x2="18" y2="18"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                    <iframe
                        v-if="visible"
                        :src="fullUrl"
                        class="thesis-panel-iframe"
                    ></iframe>
                </div>
            </div>
        </Transition>
    </Teleport>
</template>

<script setup>
import { computed, inject, onMounted, onUnmounted } from 'vue'

const settings = inject('settings')

const props = defineProps({
    visible: { type: Boolean, default: false },
    page: { type: [Number, String], default: null },
})

const emit = defineEmits(['close'])

const documentLabel = computed(() => settings?.value?.documentLabel || 'Thesis')

const fullUrl = computed(() => {
    const doc = settings?.value?.thesisDocument
    if (!doc) return ''
    const params = ['navpanes=0']
    if (props.page) params.push(`page=${props.page}`)
    return `/thesis/${doc}#${params.join('&')}`
})

function close() {
    emit('close')
}

function onKeydown(e) {
    if (e.key === 'Escape' && props.visible) {
        close()
    }
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.thesis-panel-overlay {
    position: fixed;
    inset: 0;
    z-index: 2000;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: flex-end;
}

.thesis-panel {
    width: min(800px, 85vw);
    height: 100%;
    background: var(--bg-elevated, #1a1a2e);
    display: flex;
    flex-direction: column;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.4);
}

.thesis-panel-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border, #333);
    flex-shrink: 0;
}

.thesis-panel-title {
    font-weight: 600;
    font-size: 15px;
    color: var(--text-primary, #eee);
}

.thesis-panel-page {
    font-size: 13px;
    color: var(--text-muted, #999);
    padding: 2px 8px;
    background: var(--accent-muted, rgba(59, 130, 246, 0.1));
    border-radius: 4px;
}

.thesis-panel-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 4px;
}

.thesis-panel-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    background: none;
    color: var(--text-muted, #999);
    border-radius: 6px;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.15s;
}

.thesis-panel-btn:hover {
    background: var(--border, #333);
    color: var(--text-primary, #eee);
}

.thesis-panel-iframe {
    flex: 1;
    border: none;
    width: 100%;
    background: white;
}

/* Slide transition */
.thesis-panel-enter-active,
.thesis-panel-leave-active {
    transition: opacity 0.25s ease;
}

.thesis-panel-enter-active .thesis-panel,
.thesis-panel-leave-active .thesis-panel {
    transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.thesis-panel-enter-from,
.thesis-panel-leave-to {
    opacity: 0;
}

.thesis-panel-enter-from .thesis-panel,
.thesis-panel-leave-to .thesis-panel {
    transform: translateX(100%);
}
</style>
