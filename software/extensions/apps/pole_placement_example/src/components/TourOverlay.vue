<template>
    <Teleport to="body">
        <div v-if="active" class="tour-overlay">
            <div class="tour-backdrop-click" @click="skip"></div>
            <div class="tour-backdrop" :style="backdropStyle"></div>
            <div v-if="targetRect" class="tour-spotlight" :style="spotlightStyle"></div>
            <div ref="cardRef" class="tour-card" :style="cardStyle">
                <div class="tour-card-header">
                    <span class="tour-step-label">{{ currentStep + 1 }} / {{ steps.length }}</span>
                    <button class="tour-skip" @click="skip">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </div>
                <h3 class="tour-card-title">{{ currentStepData.title }}</h3>
                <p class="tour-card-desc">{{ currentStepData.description }}</p>
                <div class="tour-card-footer">
                    <div class="tour-dots">
                        <span v-for="(_, i) in steps" :key="i"
                              class="tour-dot" :class="{ active: i === currentStep, seen: i < currentStep }"></span>
                    </div>
                    <div class="tour-card-actions">
                        <button v-if="currentStep > 0" class="tour-btn tour-btn-ghost" @click="prev">Back</button>
                        <button class="tour-btn tour-btn-primary" @click="next">
                            {{ currentStep === steps.length - 1 ? 'Done' : 'Next' }}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
    active: Boolean,
    steps: { type: Array, default: () => [] }
})

const emit = defineEmits(['close'])

const currentStep = ref(0)
const targetRect = ref(null)

const PAD = 10

const currentStepData = computed(() => props.steps[currentStep.value] || {})

function clampRect(r) {
    const vw = window.innerWidth
    const vh = window.innerHeight
    const left = Math.max(0, r.left - PAD)
    const top = Math.max(0, r.top - PAD)
    const right = Math.min(vw, r.right + PAD)
    const bottom = Math.min(vh, r.bottom + PAD)
    return { left, top, width: right - left, height: bottom - top, right, bottom }
}

const spotlightStyle = computed(() => {
    if (!targetRect.value) return { display: 'none' }
    const c = clampRect(targetRect.value)
    return {
        left: c.left + 'px',
        top: c.top + 'px',
        width: c.width + 'px',
        height: c.height + 'px',
    }
})

const backdropStyle = computed(() => {
    if (!targetRect.value) return {}
    const c = clampRect(targetRect.value)
    const br = Math.min(12, c.width / 2, c.height / 2)
    return {
        clipPath: `polygon(
            0% 0%, 0% 100%, 100% 100%, 100% 0%, 0% 0%,
            ${c.left}px ${c.top + br}px,
            ${c.left + br}px ${c.top}px,
            ${c.left + c.width - br}px ${c.top}px,
            ${c.left + c.width}px ${c.top + br}px,
            ${c.left + c.width}px ${c.top + c.height - br}px,
            ${c.left + c.width - br}px ${c.top + c.height}px,
            ${c.left + br}px ${c.top + c.height}px,
            ${c.left}px ${c.top + c.height - br}px,
            ${c.left}px ${c.top + br}px
        )`
    }
})

const cardRef = ref(null)

const cardStyle = computed(() => {
    const cardW = 300
    const gap = 16
    const margin = 12
    const vw = window.innerWidth
    const vh = window.innerHeight
    const cardH = cardRef.value?.offsetHeight || 180

    if (!targetRect.value) {
        return {
            top: '50%',
            left: '50%',
            width: cardW + 'px',
            transform: 'translate(-50%, -50%)'
        }
    }

    const c = clampRect(targetRect.value)
    let top, left

    const spaceBelow = vh - c.bottom
    const spaceAbove = c.top
    const spaceRight = vw - c.right
    const spaceLeft = c.left

    if (spaceBelow >= cardH + gap + margin) {
        top = c.bottom + gap
        left = c.left + c.width / 2 - cardW / 2
    } else if (spaceAbove >= cardH + gap + margin) {
        top = c.top - gap - cardH
        left = c.left + c.width / 2 - cardW / 2
    } else if (spaceRight >= cardW + gap + margin) {
        top = c.top + c.height / 2 - cardH / 2
        left = c.right + gap
    } else if (spaceLeft >= cardW + gap + margin) {
        top = c.top + c.height / 2 - cardH / 2
        left = c.left - gap - cardW
    } else {
        top = vh / 2 - cardH / 2
        left = vw / 2 - cardW / 2
    }

    // Clamp to viewport
    top = Math.max(margin, Math.min(top, vh - cardH - margin))
    left = Math.max(margin, Math.min(left, vw - cardW - margin))

    return { top: top + 'px', left: left + 'px', width: cardW + 'px' }
})

function updateTargetRect() {
    const step = props.steps[currentStep.value]
    if (!step?.selector) {
        targetRect.value = null
        return
    }
    const el = document.querySelector(step.selector)
    if (el) {
        const r = el.getBoundingClientRect()
        targetRect.value = { left: r.left, top: r.top, width: r.width, height: r.height, bottom: r.bottom, right: r.right }
        if (r.top < -50 || r.bottom > window.innerHeight + 50) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            setTimeout(updateTargetRect, 400)
        }
    } else {
        targetRect.value = null
    }
}

function leaveStep(idx) {
    const step = props.steps[idx]
    if (step?.onLeave) step.onLeave()
}

function enterStep(idx) {
    const step = props.steps[idx]
    if (step?.onEnter) step.onEnter()
}

function next() {
    if (currentStep.value < props.steps.length - 1) {
        leaveStep(currentStep.value)
        currentStep.value++
    } else {
        finish()
    }
}

function prev() {
    if (currentStep.value > 0) {
        leaveStep(currentStep.value)
        currentStep.value--
    }
}

function skip() {
    finish()
}

function finish() {
    leaveStep(currentStep.value)
    currentStep.value = 0
    emit('close')
}

function onKeyDown(e) {
    if (!props.active) return
    if (e.key === 'Escape') skip()
    if (e.key === 'ArrowRight' || e.key === 'Enter') next()
    if (e.key === 'ArrowLeft') prev()
}

function onResize() {
    if (props.active) updateTargetRect()
}

watch(() => currentStep.value, (newVal) => {
    enterStep(newVal)
    nextTick(() => setTimeout(updateTargetRect, 150))
})

watch(() => props.active, (val) => {
    if (val) {
        currentStep.value = 0
        enterStep(0)
        nextTick(() => setTimeout(updateTargetRect, 100))
    }
})

onMounted(() => {
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('resize', onResize)
})

onUnmounted(() => {
    document.removeEventListener('keydown', onKeyDown)
    window.removeEventListener('resize', onResize)
})
</script>

<style>
.tour-overlay {
    position: fixed;
    inset: 0;
    z-index: 10000;
}

.tour-backdrop-click {
    position: fixed;
    inset: 0;
    z-index: 10000;
}

.tour-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    transition: clip-path 0.35s ease;
    z-index: 10001;
    pointer-events: none;
}

.tour-spotlight {
    position: fixed;
    border-radius: 12px;
    box-shadow: 0 0 0 2px rgba(69, 170, 242, 0.5), 0 0 20px 4px rgba(69, 170, 242, 0.15);
    transition: all 0.35s ease;
    pointer-events: none;
    z-index: 10002;
}

.tour-card {
    position: fixed;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
    z-index: 10003;
    transition: top 0.35s ease, left 0.35s ease;
    animation: tourCardIn 0.3s ease;
    font-family: 'JetBrains Mono', monospace;
}

@keyframes tourCardIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

.tour-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}

.tour-step-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.5px;
}

.tour-skip {
    background: none;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
}
.tour-skip:hover {
    color: var(--text);
    background: var(--bg-hover);
}

.tour-card-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    margin: 0 0 8px;
}

.tour-card-desc {
    font-size: 12px;
    color: var(--text-dim);
    line-height: 1.6;
    margin: 0 0 16px;
}

.tour-card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.tour-dots {
    display: flex;
    gap: 5px;
    flex-wrap: wrap;
    max-width: 140px;
}

.tour-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--border);
    transition: all 0.2s;
}
.tour-dot.active {
    background: var(--accent);
    width: 16px;
    border-radius: 3px;
}
.tour-dot.seen {
    background: var(--text-dim);
}

.tour-card-actions {
    display: flex;
    gap: 6px;
}

.tour-btn {
    padding: 7px 16px;
    border: none;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    font-family: 'JetBrains Mono', monospace;
}

.tour-btn-primary {
    background: var(--accent);
    color: #fff;
}
.tour-btn-primary:hover {
    filter: brightness(1.15);
}

.tour-btn-ghost {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
}
.tour-btn-ghost:hover {
    background: var(--bg-hover);
    color: var(--text);
}
</style>
