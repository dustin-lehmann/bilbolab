<template>
    <Teleport to="body">
        <Transition name="info-panel">
            <div v-if="visible" class="info-panel-overlay" @click.self="close">
                <div class="info-panel">
                    <div class="info-panel-header">
                        <span class="info-panel-title">More Information</span>
                        <button class="info-panel-close" @click="close" title="Close">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="6" x2="6" y2="18"/>
                                <line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                        </button>
                    </div>
                    <div class="info-panel-body" v-html="renderedContent"></div>
                </div>
            </div>
        </Transition>
    </Teleport>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'

const props = defineProps({
    visible: { type: Boolean, default: false },
    content: { type: String, default: '' },
})

const emit = defineEmits(['close'])

marked.setOptions({
    breaks: true,
    gfm: true,
})

const renderedContent = computed(() => {
    if (!props.content) return ''
    return marked.parse(props.content)
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
.info-panel-overlay {
    position: fixed;
    inset: 0;
    z-index: 2000;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: flex-end;
}

.info-panel {
    width: min(700px, 85vw);
    height: 100%;
    background: var(--bg-elevated, #1a1a2e);
    display: flex;
    flex-direction: column;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.4);
}

.info-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    border-bottom: 1px solid var(--border, #333);
    flex-shrink: 0;
}

.info-panel-title {
    font-weight: 600;
    font-size: 15px;
    color: var(--text-primary, #eee);
}

.info-panel-close {
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
    transition: all 0.15s;
}

.info-panel-close:hover {
    background: var(--border, #333);
    color: var(--text-primary, #eee);
}

.info-panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    color: var(--text-secondary, #ccc);
    font-size: 15px;
    line-height: 1.7;
}

/* Markdown content styles */
.info-panel-body :deep(h1) { font-size: 22px; font-weight: 600; margin: 0 0 16px; color: var(--text-primary, #eee); }
.info-panel-body :deep(h2) { font-size: 18px; font-weight: 600; margin: 24px 0 12px; color: var(--text-primary, #eee); }
.info-panel-body :deep(h3) { font-size: 16px; font-weight: 600; margin: 20px 0 8px; color: var(--text-primary, #eee); }
.info-panel-body :deep(p) { margin: 0 0 12px; }
.info-panel-body :deep(ul), .info-panel-body :deep(ol) { margin: 0 0 12px; padding-left: 24px; }
.info-panel-body :deep(li) { margin-bottom: 4px; }
.info-panel-body :deep(a) { color: #3b82f6; text-decoration: none; }
.info-panel-body :deep(a:hover) { text-decoration: underline; }
.info-panel-body :deep(code) {
    background: var(--code-bg, rgba(255,255,255,0.06));
    padding: 2px 6px; border-radius: 4px; font-size: 13px;
    font-family: 'SF Mono', 'Fira Code', monospace;
}
.info-panel-body :deep(pre) {
    background: var(--code-bg, rgba(255,255,255,0.06));
    padding: 14px 16px; border-radius: 8px; overflow-x: auto;
    margin: 0 0 12px;
}
.info-panel-body :deep(pre code) { background: none; padding: 0; }
.info-panel-body :deep(blockquote) {
    border-left: 3px solid #3b82f6; margin: 0 0 12px; padding: 8px 16px;
    color: var(--text-muted, #999);
}
.info-panel-body :deep(img) { max-width: 100%; border-radius: 8px; margin: 8px 0; }
.info-panel-body :deep(table) { width: 100%; border-collapse: collapse; margin: 0 0 12px; }
.info-panel-body :deep(th), .info-panel-body :deep(td) {
    padding: 8px 12px; border: 1px solid var(--border, #333); text-align: left; font-size: 14px;
}
.info-panel-body :deep(th) { background: var(--code-bg, rgba(255,255,255,0.06)); font-weight: 600; }
.info-panel-body :deep(hr) { border: none; border-top: 1px solid var(--border, #333); margin: 20px 0; }

/* Slide transition */
.info-panel-enter-active,
.info-panel-leave-active {
    transition: opacity 0.25s ease;
}

.info-panel-enter-active .info-panel,
.info-panel-leave-active .info-panel {
    transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.info-panel-enter-from,
.info-panel-leave-to {
    opacity: 0;
}

.info-panel-enter-from .info-panel,
.info-panel-leave-to .info-panel {
    transform: translateX(100%);
}
</style>
