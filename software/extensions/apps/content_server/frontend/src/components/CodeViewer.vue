<template>
    <div class="code-viewer" v-if="item">
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
                    <span class="item-type-badge code">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="16 18 22 12 16 6"/>
                            <polyline points="8 6 2 12 8 18"/>
                        </svg>
                        {{ languageDisplay }}
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

        <div class="code-container">
            <div class="code-toolbar">
                <span class="file-name">{{ item.file }}</span>
                <div class="toolbar-actions">
                    <span class="line-count">{{ lineCount }} lines</span>
                    <button class="toolbar-btn" @click="copyCode" :class="{ copied: justCopied }">
                        <svg v-if="!justCopied" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                        </svg>
                        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="20 6 9 17 4 12"/>
                        </svg>
                        {{ justCopied ? 'Copied!' : 'Copy' }}
                    </button>
                    <a :href="`/code/${item.file}`" download class="toolbar-btn">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        Download
                    </a>
                </div>
            </div>
            <div class="code-content">
                <div class="line-numbers">
                    <span v-for="n in lineCount" :key="n">{{ n }}</span>
                </div>
                <pre><code ref="codeBlock" :class="`language-${item.language || 'plaintext'}`">{{ code }}</code></pre>
            </div>
        </div>
    </div>

    <div v-else class="loading">
        Loading code...
    </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import hljs from 'highlight.js'
import DocRefBadge from './DocRefBadge.vue'
import InfoPanel from './InfoPanel.vue'

const showInfo = ref(false)

const props = defineProps({
    id: String
})

const router = useRouter()
const item = ref(null)
const code = ref('')
const codeBlock = ref(null)
const justCopied = ref(false)

const lineCount = computed(() => {
    if (!code.value) return 0
    return code.value.split('\n').length
})

const languageDisplay = computed(() => {
    const lang = item.value?.language || 'plaintext'
    const displayNames = {
        'javascript': 'JavaScript',
        'typescript': 'TypeScript',
        'python': 'Python',
        'cpp': 'C++',
        'c': 'C',
        'java': 'Java',
        'rust': 'Rust',
        'go': 'Go',
        'html': 'HTML',
        'css': 'CSS',
        'json': 'JSON',
        'yaml': 'YAML',
        'bash': 'Bash',
        'shell': 'Shell',
        'sql': 'SQL',
        'plaintext': 'Plain Text'
    }
    return displayNames[lang] || lang.charAt(0).toUpperCase() + lang.slice(1)
})

function goBack() {
    if (item.value?.folderPath && item.value.folderPath.length > 0) {
        const parent = item.value.folderPath[item.value.folderPath.length - 1]
        router.push(`/folder/${parent.id}`)
    } else {
        router.push('/')
    }
}

async function copyCode() {
    try {
        await navigator.clipboard.writeText(code.value)
        justCopied.value = true
        setTimeout(() => {
            justCopied.value = false
        }, 2000)
    } catch (err) {
        console.error('Failed to copy:', err)
    }
}

function highlightCode() {
    if (codeBlock.value && code.value) {
        hljs.highlightElement(codeBlock.value)
    }
}

async function loadItem() {
    item.value = null
    code.value = ''
    try {
        // Load item metadata
        const response = await fetch(`/api/experiments/${props.id}`)
        item.value = await response.json()

        // Load code content
        if (item.value?.file) {
            const codeResponse = await fetch(`/code/${item.value.file}`)
            code.value = await codeResponse.text()

            nextTick(() => {
                highlightCode()
            })
        }
    } catch (error) {
        console.error('Failed to load code:', error)
    }
}

// Watch for id changes
watch(() => props.id, () => {
    loadItem()
})

onMounted(async () => {
    await loadItem()
})

watch(code, () => {
    nextTick(() => {
        highlightCode()
    })
})
</script>

<style scoped>
.code-viewer {
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

.item-type-badge.code {
    background: rgba(6, 182, 212, 0.15);
    color: #22d3ee;
    border: 1px solid rgba(6, 182, 212, 0.3);
}

.item-description {
    color: var(--text-muted);
    font-size: 13px;
    margin-top: 4px;
}

.code-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: #0d1117;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #30363d;
}

.code-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    background: #161b22;
    border-bottom: 1px solid #30363d;
    flex-shrink: 0;
}

.file-name {
    font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
    font-size: 13px;
    color: #8b949e;
}

.toolbar-actions {
    display: flex;
    align-items: center;
    gap: 12px;
}

.line-count {
    font-size: 12px;
    color: #6e7681;
}

.toolbar-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #21262d;
    border: 1px solid #30363d;
    color: #c9d1d9;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    text-decoration: none;
    font-size: 13px;
    transition: all 0.2s;
}

.toolbar-btn:hover {
    background: #30363d;
    border-color: #8b949e;
}

.toolbar-btn.copied {
    background: rgba(46, 160, 67, 0.2);
    border-color: #2ea043;
    color: #3fb950;
}

.code-content {
    flex: 1;
    display: flex;
    overflow: auto;
    min-height: 0;
}

.line-numbers {
    display: flex;
    flex-direction: column;
    padding: 16px 0;
    background: #0d1117;
    border-right: 1px solid #21262d;
    user-select: none;
    flex-shrink: 0;
    position: sticky;
    left: 0;
    z-index: 1;
}

.line-numbers span {
    padding: 0 16px;
    font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
    font-size: 13px;
    line-height: 1.5;
    color: #6e7681;
    text-align: right;
    min-width: 50px;
}

.code-content pre {
    margin: 0;
    padding: 16px;
    flex: 1;
    overflow: visible;
}

.code-content code {
    font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
    font-size: 13px;
    line-height: 1.5;
    background: transparent !important;
    padding: 0 !important;
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}
</style>

<style>
/* GitHub Dark theme for highlight.js */
.hljs {
    color: #c9d1d9;
    background: #0d1117;
}

.hljs-doctag,
.hljs-keyword,
.hljs-meta .hljs-keyword,
.hljs-template-tag,
.hljs-template-variable,
.hljs-type,
.hljs-variable.language_ {
    color: #ff7b72;
}

.hljs-title,
.hljs-title.class_,
.hljs-title.class_.inherited__,
.hljs-title.function_ {
    color: #d2a8ff;
}

.hljs-attr,
.hljs-attribute,
.hljs-literal,
.hljs-meta,
.hljs-number,
.hljs-operator,
.hljs-selector-attr,
.hljs-selector-class,
.hljs-selector-id,
.hljs-variable {
    color: #79c0ff;
}

.hljs-meta .hljs-string,
.hljs-regexp,
.hljs-string {
    color: #a5d6ff;
}

.hljs-built_in,
.hljs-symbol {
    color: #ffa657;
}

.hljs-code,
.hljs-comment,
.hljs-formula {
    color: #8b949e;
}

.hljs-name,
.hljs-quote,
.hljs-selector-pseudo,
.hljs-selector-tag {
    color: #7ee787;
}

.hljs-subst {
    color: #c9d1d9;
}

.hljs-section {
    color: #1f6feb;
    font-weight: bold;
}

.hljs-bullet {
    color: #f2cc60;
}

.hljs-emphasis {
    color: #c9d1d9;
    font-style: italic;
}

.hljs-strong {
    color: #c9d1d9;
    font-weight: bold;
}

.hljs-addition {
    color: #aff5b4;
    background-color: #033a16;
}

.hljs-deletion {
    color: #ffdcd7;
    background-color: #67060c;
}
</style>
