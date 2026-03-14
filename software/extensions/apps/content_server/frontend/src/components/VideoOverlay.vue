<template>
    <div class="video-overlay-container" v-if="activeOverlays.length">
        <div
            v-for="(entry, i) in activeOverlays"
            :key="i"
            class="video-overlay-text"
            :style="overlayPositionStyle"
        >
            <span class="video-overlay-label" :style="overlayTextStyle">{{ entry.text }}</span>
        </div>
    </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
    currentTime: { type: Number, default: 0 },
    overlays: { type: Array, default: () => [] },
    overlayStyle: { type: Object, default: () => ({}) },
})

const activeOverlays = computed(() => {
    if (!props.overlays || !props.overlays.length) return []
    const t = props.currentTime
    return props.overlays.filter(o => {
        const start = Number(o.time) || 0
        const dur = Number(o.duration) || 0
        return t >= start && t < start + dur
    })
})

const overlayPositionStyle = computed(() => {
    const s = props.overlayStyle
    const vPos = s.verticalPosition || 'bottom'
    const hPos = s.horizontalPosition || 'center'

    const style = {
        position: 'absolute',
        left: '0',
        right: '0',
        display: 'flex',
        padding: '12px 16px',
        pointerEvents: 'none',
    }

    // Vertical
    if (vPos === 'top') {
        style.top = '0'
    } else {
        style.bottom = '0'
    }

    // Horizontal
    if (hPos === 'left') {
        style.justifyContent = 'flex-start'
    } else if (hPos === 'right') {
        style.justifyContent = 'flex-end'
    } else {
        style.justifyContent = 'center'
    }

    return style
})

const overlayTextStyle = computed(() => {
    const s = props.overlayStyle
    return {
        fontSize: (s.fontSize || 16) + 'px',
        color: s.fontColor || '#ffffff',
        backgroundColor: s.backgroundColor || 'rgba(0, 0, 0, 0.75)',
        opacity: s.opacity != null ? s.opacity : 0.8,
        padding: '4px 12px',
        borderRadius: '4px',
        lineHeight: '1.4',
        maxWidth: '80%',
        textAlign: 'center',
    }
})
</script>

<style scoped>
.video-overlay-container {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 5;
}
</style>
