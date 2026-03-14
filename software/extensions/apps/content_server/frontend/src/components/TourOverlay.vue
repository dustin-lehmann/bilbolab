<template>
    <Teleport to="body">
        <div v-if="active" class="tour-overlay">
            <!-- Clickable backdrop to dismiss -->
            <div class="tour-backdrop-click" @click="skip"></div>

            <!-- Dark backdrop with cutout -->
            <div class="tour-backdrop" :style="backdropStyle"></div>

            <!-- Spotlight ring around target -->
            <div v-if="targetRect" class="tour-spotlight" :style="spotlightStyle"></div>

            <!-- Tooltip card -->
            <div class="tour-card" :style="cardStyle">
                <div class="tour-card-header">
                    <span class="tour-step-label">{{ currentStep + 1 }} / {{ steps.length }}</span>
                    <button class="tour-skip" @click="skip">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </div>
                <div v-if="currentStepData.badge" class="tour-card-badge" :class="currentStepData.badgeClass">{{ currentStepData.badge }}</div>
                <h3 class="tour-card-title">{{ currentStepData.title }}</h3>
                <div v-if="currentStepData.image" class="tour-card-image">
                    <img :src="currentStepData.image" alt="" @error="$event.target.parentElement.style.display='none'">
                </div>
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

// Clamp rect so it never goes outside the viewport
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

const cardStyle = computed(() => {
    const hasImage = currentStepData.value?.image
    const cardW = hasImage ? 400 : 340
    const gap = 16
    const vw = window.innerWidth
    const vh = window.innerHeight

    // If no target, center the card
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

    if (spaceBelow >= 180) {
        top = c.bottom + gap
        left = Math.max(16, Math.min(c.left + c.width / 2 - cardW / 2, vw - cardW - 16))
    } else if (spaceAbove >= 180) {
        top = c.top - gap - 170
        left = Math.max(16, Math.min(c.left + c.width / 2 - cardW / 2, vw - cardW - 16))
    } else if (spaceRight >= cardW + gap + 16) {
        top = Math.max(16, Math.min(c.top + c.height / 2 - 85, vh - 200))
        left = c.right + gap
    } else if (spaceLeft >= cardW + gap + 16) {
        top = Math.max(16, Math.min(c.top + c.height / 2 - 85, vh - 200))
        left = c.left - gap - cardW
    } else {
        // Fallback: bottom, clamped
        top = Math.min(c.bottom + gap, vh - 200)
        left = Math.max(16, Math.min(vw / 2 - cardW / 2, vw - cardW - 16))
    }

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
        // Scroll into view if needed
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
    // Delay to allow onEnter DOM changes (e.g. accordion expand) to render
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
    background: var(--overlay);
    transition: clip-path 0.35s ease;
    z-index: 10001;
    pointer-events: none;
}

.tour-spotlight {
    position: fixed;
    border-radius: 12px;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.5), 0 0 20px 4px rgba(59, 130, 246, 0.15);
    transition: all 0.35s ease;
    pointer-events: none;
    z-index: 10002;
}

.tour-card {
    position: fixed;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    box-shadow: 0 16px 48px var(--overlay-light);
    z-index: 10003;
    transition: top 0.35s ease, left 0.35s ease;
    animation: tourCardIn 0.3s ease;
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
    color: #3b82f6;
    letter-spacing: 0.5px;
}

.tour-skip {
    background: none;
    border: none;
    color: var(--text-faint);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
}
.tour-skip:hover {
    color: var(--text-primary);
    background: var(--bg-button-hover);
}

.tour-card-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 8px;
    color: var(--text-primary);
    background: var(--text-faint);
}
.tour-card-badge.video { background: #8b5cf6; }
.tour-card-badge.synchronized { background: #3b82f6; }
.tour-card-badge.collection { background: #f59e0b; }
.tour-card-badge.pdf { background: #ef4444; }
.tour-card-badge.figures { background: #a855f7; }
.tour-card-badge.code { background: #06b6d4; }
.tour-card-badge.interactive { background: #22c55e; }
.tour-card-badge.model3d { background: #0ea5e9; }

.tour-card-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 8px;
}

.tour-card-image {
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 10px;
    background: var(--code-bg);
}

.tour-card-image img {
    width: 100%;
    display: block;
}

.tour-card-desc {
    font-size: 13px;
    color: var(--text-secondary);
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
    background: var(--border-light);
    transition: all 0.2s;
}
.tour-dot.active {
    background: #3b82f6;
    width: 16px;
    border-radius: 3px;
}
.tour-dot.seen {
    background: var(--text-faint);
}

.tour-card-actions {
    display: flex;
    gap: 6px;
}

.tour-btn {
    padding: 7px 16px;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
}

.tour-btn-primary {
    background: #3b82f6;
    color: var(--text-primary);
}
.tour-btn-primary:hover {
    background: #2563eb;
}

.tour-btn-ghost {
    background: transparent;
    color: var(--text-muted);
    border: 1px solid var(--border-light);
}
.tour-btn-ghost:hover {
    background: var(--border);
    color: var(--text-secondary);
}
</style>
