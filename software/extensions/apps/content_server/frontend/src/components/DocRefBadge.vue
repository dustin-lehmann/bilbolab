<template>
    <div v-if="visible" class="doc-ref-badge">
        <component
            :is="hasLink ? 'a' : 'span'"
            v-bind="hasLink ? linkBind : {}"
            class="doc-ref-link"
            :class="{ clickable: hasLink }"
            :title="hasLink ? `Open ${documentLabel} on page ${item.page}` : tooltip"
            @click="handleClick"
        >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <template v-if="tocPath.length">
                <template v-for="(crumb, i) in tocPath" :key="i">
                    <span v-if="i > 0" class="doc-ref-sep">/</span>
                    <span class="doc-ref-crumb">{{ crumb.number }} {{ crumb.name }}</span>
                </template>
            </template>
            <span v-else class="doc-ref-text">
                <template v-if="item.chapter">Ch. {{ item.chapter }}</template>
                <template v-if="fullSectionNumber"> &middot; Sec. {{ fullSectionNumber }}</template>
            </span>
            <span v-if="item.page" class="doc-ref-page">p.&thinsp;{{ item.page }}</span>
            <svg v-if="hasLink" class="external-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                <polyline points="15 3 21 3 21 9"/>
                <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
        </component>
    </div>
</template>

<script setup>
import { computed, inject } from 'vue'

const settings = inject('settings')
const openThesisPanel = inject('openThesisPanel', null)

const props = defineProps({
    item: { type: Object, required: true },
})

const documentLabel = computed(() => settings?.value?.documentLabel || 'Thesis')

const visible = computed(() => {
    const i = props.item
    return !!(i.chapter || i.section || i.subsection || i.page)
})

const hasLink = computed(() => {
    return visible.value && !!settings?.value?.thesisDocument
})

const usePanel = computed(() => {
    return settings?.value?.thesisOpenInPanel !== false && openThesisPanel
})

const linkBind = computed(() => {
    if (usePanel.value) {
        return { href: '#', role: 'button' }
    }
    return { href: thesisUrl.value, target: '_blank', rel: 'noopener' }
})

const thesisUrl = computed(() => {
    if (!hasLink.value) return ''
    const url = `/thesis/${settings.value.thesisDocument}`
    return props.item.page ? `${url}#page=${props.item.page}` : url
})

function handleClick(e) {
    if (!hasLink.value) return
    if (usePanel.value) {
        e.preventDefault()
        openThesisPanel(props.item.page || 1)
    }
}

const fullSectionNumber = computed(() => {
    const ch = props.item.chapter
    const sec = props.item.section
    const sub = props.item.subsection
    if (!sec && !sub) return ''
    let num = ch ? `${ch}.${sec}` : sec
    if (sub) num += `.${sub}`
    return num
})

function tocEntryNumber(e) {
    if (e.subsection) return `${e.chapter}.${e.section}.${e.subsection}`
    if (e.section) return `${e.chapter}.${e.section}`
    return e.chapter || ''
}

function findTocEntry(toc, number) {
    return toc.find(e => tocEntryNumber(e) === String(number)) || null
}

const tocPath = computed(() => {
    const toc = settings?.value?.thesisTOC
    if (!toc || !Array.isArray(toc) || toc.length === 0) return []
    const item = props.item
    const ch = String(item.chapter || '')
    const sec = item.section ? `${ch}.${item.section}` : ''
    const sub = item.subsection ? `${ch}.${item.section}.${item.subsection}` : ''

    const path = []
    if (ch) {
        const entry = findTocEntry(toc, ch)
        if (entry) path.push({ number: ch, name: entry.name })
    }
    if (sec) {
        const entry = findTocEntry(toc, sec)
        if (entry) path.push({ number: sec, name: entry.name })
    }
    if (sub) {
        const entry = findTocEntry(toc, sub)
        if (entry) path.push({ number: sub, name: entry.name })
    }
    return path
})

const tooltip = computed(() => {
    const parts = []
    if (props.item.chapter) parts.push(`Chapter ${props.item.chapter}`)
    if (fullSectionNumber.value) parts.push(`Section ${fullSectionNumber.value}`)
    if (props.item.page) parts.push(`Page ${props.item.page}`)
    const base = `${documentLabel.value}: ${parts.join(', ')}`
    if (tocPath.value.length) {
        return `${base} — ${tocPath.value.map(c => `${c.number} ${c.name}`).join(' / ')}`
    }
    return base
})
</script>

<style scoped>
.doc-ref-badge {
    display: inline-flex;
}

.doc-ref-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    background: var(--accent-muted);
    border: 1px solid rgba(59, 130, 246, 0.2);
    text-decoration: none;
    transition: all 0.2s;
}

.doc-ref-link.clickable {
    cursor: pointer;
}

.doc-ref-link.clickable:hover {
    background: rgba(59, 130, 246, 0.2);
    border-color: rgba(59, 130, 246, 0.4);
    color: var(--text-primary);
}

.doc-ref-text {
    white-space: nowrap;
}

.doc-ref-crumb {
    display: inline-block;
    background: rgba(255, 255, 255, 0.08);
    padding: 1px 7px;
    border-radius: 4px;
    font-size: 12px;
    white-space: nowrap;
}

.doc-ref-sep {
    font-size: 11px;
    color: var(--text-faint);
    margin: 0 -1px;
}

.doc-ref-page {
    font-size: 12px;
    opacity: 0.7;
    white-space: nowrap;
    margin-left: 2px;
}

.external-icon {
    opacity: 0.5;
    flex-shrink: 0;
}

.doc-ref-link.clickable:hover .external-icon {
    opacity: 1;
}
</style>
