<template>
    <div class="color-alpha-picker">
        <input type="color" :value="hex" @input="onColorChange" class="cap-color">
        <input type="range" min="0" max="1" step="0.05" :value="alpha" @input="onAlphaChange" class="cap-slider" :style="sliderBg">
        <span class="cap-alpha">{{ Math.round(alpha * 100) }}%</span>
    </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
    modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])

function parseValue(val) {
    if (!val) return { r: 0, g: 0, b: 0, a: 0.7 }

    // rgba(r, g, b, a)
    const rgbaMatch = val.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)/)
    if (rgbaMatch) {
        return {
            r: parseInt(rgbaMatch[1]),
            g: parseInt(rgbaMatch[2]),
            b: parseInt(rgbaMatch[3]),
            a: rgbaMatch[4] !== undefined ? parseFloat(rgbaMatch[4]) : 1
        }
    }

    // #hex
    const hexMatch = val.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i)
    if (hexMatch) {
        return {
            r: parseInt(hexMatch[1], 16),
            g: parseInt(hexMatch[2], 16),
            b: parseInt(hexMatch[3], 16),
            a: 1
        }
    }

    return { r: 0, g: 0, b: 0, a: 0.7 }
}

const parsed = computed(() => parseValue(props.modelValue))

const hex = computed(() => {
    const { r, g, b } = parsed.value
    return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('')
})

const alpha = computed(() => parsed.value.a)

const sliderBg = computed(() => {
    const { r, g, b } = parsed.value
    return {
        '--cap-color-solid': `rgb(${r},${g},${b})`,
        '--cap-color-transparent': `rgba(${r},${g},${b},0)`
    }
})

function emitRgba(r, g, b, a) {
    emit('update:modelValue', `rgba(${r}, ${g}, ${b}, ${a})`)
}

function onColorChange(e) {
    const h = e.target.value
    const r = parseInt(h.slice(1, 3), 16)
    const g = parseInt(h.slice(3, 5), 16)
    const b = parseInt(h.slice(5, 7), 16)
    emitRgba(r, g, b, alpha.value)
}

function onAlphaChange(e) {
    const { r, g, b } = parsed.value
    emitRgba(r, g, b, parseFloat(e.target.value))
}
</script>

<style scoped>
.color-alpha-picker {
    display: flex;
    align-items: center;
    gap: 4px;
}

.cap-color {
    width: 28px;
    height: 28px;
    padding: 1px;
    border: 1px solid var(--border, #333);
    border-radius: 4px;
    background: none;
    cursor: pointer;
    flex-shrink: 0;
}

.cap-slider {
    flex: 1;
    height: 6px;
    -webkit-appearance: none;
    appearance: none;
    border-radius: 3px;
    cursor: pointer;
    background: linear-gradient(to right, var(--cap-color-transparent), var(--cap-color-solid));
    min-width: 40px;
}

.cap-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px;
    height: 14px;
    background: #fff;
    border-radius: 50%;
    border: 2px solid var(--border, #333);
    cursor: pointer;
}

.cap-slider::-moz-range-thumb {
    width: 14px;
    height: 14px;
    background: #fff;
    border-radius: 50%;
    border: 2px solid var(--border, #333);
    cursor: pointer;
}

.cap-alpha {
    font-size: 10px;
    color: var(--text-faint, #888);
    width: 28px;
    text-align: right;
    flex-shrink: 0;
}
</style>
