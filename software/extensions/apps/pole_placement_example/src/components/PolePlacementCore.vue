<script setup>
import { ref, reactive, watch, onMounted, computed, nextTick } from 'vue'
import BabylonScene from './BabylonScene.vue'
import PolePlot from './PolePlot.vue'
import PoleControls from './PoleControls.vue'
import SimTimeline from './SimTimeline.vue'
import StatePlot from './StatePlot.vue'
import { bilboEigenstructureAssignment, eigenstructureAssignment, DEFAULT_POLES, DEFAULT_EIGENVECTORS } from '../../../../libs/webapps/lib/control.js'
import { DEFAULT_BILBO_MODEL } from '../../../../libs/webapps/lib/model.js'
import { BilboDynamics3D, BilboDynamics3DLinearReduced, linearizeReduced } from '../../../../libs/webapps/lib/dynamics.js'

const props = defineProps({ darkMode: Boolean })

const sceneRef = ref(null)

// ── Pole state ──────────────────────────────────────────────────────────────
const poleParams = reactive({
  p0_re: 0,        // integrator
  p1_re: -10,      // real pole
  p2_re: -5,       // complex pair real part
  p2_im: 3,        // complex pair imaginary part
  p4_re: 0,        // integrator
  p5_re: -15,      // real pole
})

const poles = computed(() => [
  { re: poleParams.p0_re, im: 0 },
  { re: poleParams.p1_re, im: 0 },
  { re: poleParams.p2_re, im: poleParams.p2_im },
  { re: poleParams.p2_re, im: -poleParams.p2_im },
  { re: poleParams.p4_re, im: 0 },
  { re: poleParams.p5_re, im: 0 },
])

// ── Simulation config ────────────────────────────────────────────────────────
const useLinear = ref(false)
const extInputMag = ref(0.5)

// ── Gain matrix K ───────────────────────────────────────────────────────────
const K7 = ref(null)   // 2×7 for nonlinear (full state)
const K6 = ref(null)   // 2×6 for linear (reduced state)
const kError = ref(null)

function recomputeK() {
  try {
    // Full 2×7 K for nonlinear dynamics
    K7.value = bilboEigenstructureAssignment(DEFAULT_BILBO_MODEL, poles.value, DEFAULT_EIGENVECTORS)
    // Reduced 2×6 K for linear dynamics
    const { A, B } = linearizeReduced(DEFAULT_BILBO_MODEL)
    K6.value = eigenstructureAssignment(A, B, poles.value, DEFAULT_EIGENVECTORS)
    kError.value = null
  } catch (e) {
    kError.value = e.message
  }
}

// Debounce K recomputation
let recomputeTimer = null
function recomputeKDebounced() {
  clearTimeout(recomputeTimer)
  recomputeTimer = setTimeout(recomputeK, 200)
}

recomputeK()
watch(poles, recomputeKDebounced, { deep: true })

// ── Simulation ──────────────────────────────────────────────────────────────
const SIM_TS = 0.01
const simState = ref(null)      // current state (7-element for 3D view)
const simHistory = ref([])
const simPhase = ref('idle')
const simTime = ref(0)
const simRunning = ref(false)
let simTimer = null
let dynamics = null
let linearStandupDone = false

// Phase timing (seconds)
const PHASE_LYING    = 1.0
const PHASE_STANDUP  = 2.0
const PHASE_STEP_NEG = 2.0
const PHASE_PAUSE    = 1.0
const PHASE_STEP_POS = 2.0
const PHASE_SETTLE   = 2.0

const totalDuration = PHASE_LYING + PHASE_STANDUP + PHASE_STEP_NEG + PHASE_PAUSE + PHASE_STEP_POS + PHASE_SETTLE

function getPhase(t) {
  let acc = 0
  if (t < (acc += PHASE_LYING))    return 'lying'
  if (t < (acc += PHASE_STANDUP))  return 'standup'
  if (t < (acc += PHASE_STEP_NEG)) return 'step_neg'
  if (t < (acc += PHASE_PAUSE))    return 'pause'
  if (t < (acc += PHASE_STEP_POS)) return 'step_pos'
  if (t < (acc += PHASE_SETTLE))   return 'settle'
  return 'done'
}

function getInput(phase) {
  const m = extInputMag.value
  switch (phase) {
    case 'lying':    return [0, 0]
    case 'standup':  return [0, 0]
    case 'step_neg': return [-m, -m]
    case 'pause':    return [0, 0]
    case 'step_pos': return [m, m]
    case 'settle':   return [0, 0]
    default:         return [0, 0]
  }
}

// Convert linear reduced state [s,v,θ,θ̇,ψ,ψ̇] to full 7-state [x,y,v,θ,θ̇,ψ,ψ̇]
// For visualization: x=s (forward distance), y=0 (no lateral in reduced model)
function reducedToFull(rs) {
  return [rs[0], 0, rs[1], rs[2], rs[3], rs[4], rs[5]]
}

// State labels for the plot
const stateLabels = ['x', 'y', 'v', 'θ', 'θ̇', 'ψ', 'ψ̇']
const plotIndices = [0, 2, 3, 4, 5]  // x, v, theta, theta_dot, psi
// Colors matching pole groups: x→blue(pos integ), v→red(fast pole), θ→green(complex), θ̇→dark green(complex), ψ→orange(yaw pole)
const plotColors = ['#45aaf2', '#e74c3c', '#2ecc71', '#2ecc71', '#f39c12']
const plotDashes = [undefined, undefined, undefined, [6, 3], undefined]

function startSimulation() {
  const isLinear = useLinear.value

  if (isLinear) {
    if (!K6.value || kError.value) return
    dynamics = new BilboDynamics3DLinearReduced(DEFAULT_BILBO_MODEL, SIM_TS)
    dynamics.setK(K6.value)
    // Start held at 105° during lying phase; dynamics reset at standup
    dynamics.state = [0, 0, 0, 0, 0, 0]
  } else {
    if (!K7.value || kError.value) return
    dynamics = new BilboDynamics3D(DEFAULT_BILBO_MODEL, SIM_TS,
      [0, 0, 0, Math.PI / 2 * 0.95, 0, 0, 0])
    dynamics.setK(K7.value)
  }

  simTime.value = 0
  simPhase.value = 'lying'
  simHistory.value = []
  linearStandupDone = false
  simState.value = isLinear ? reducedToFull(dynamics.state) : dynamics.state.slice()
  simRunning.value = true

  if (simTimer) cancelAnimationFrame(simTimer)
  simLoop()
}

function simLoop() {
  if (!simRunning.value) return
  const isLinear = useLinear.value

  const stepsPerFrame = Math.max(1, Math.round(SIM_TS * 1000 / 16.67))
  for (let i = 0; i < stepsPerFrame; i++) {
    if (simTime.value >= totalDuration) {
      simPhase.value = 'done'
      simRunning.value = false
      break
    }

    const phase = getPhase(simTime.value)
    simPhase.value = phase

    if (isLinear) {
      const LYING_THETA = 105 * Math.PI / 180  // 105°
      if (phase === 'lying') {
        // Hold at 105° — don't step dynamics, just show the fallen pose
        const lyingState = [0, 0, 0, LYING_THETA, 0, 0, 0]
        simState.value = lyingState
        simHistory.value.push({ t: simTime.value, state: lyingState, phase })
      } else {
        // On transition out of lying, init dynamics at the fallen angle
        if (!linearStandupDone) {
          const LYING_THETA = 105 * Math.PI / 180
          // reduced state: [s, v, theta, theta_dot, psi, psi_dot]
          dynamics.state = [0, 0, LYING_THETA, 0, 0, 0]
          linearStandupDone = true
        }
        dynamics.step(getInput(phase))
        const fullState = reducedToFull(dynamics.state)
        simState.value = fullState
        simHistory.value.push({ t: simTime.value, state: fullState, phase })
      }
    } else {
      if (phase === 'lying') {
        dynamics.K = null
        dynamics.step([0, 0])
      } else {
        dynamics.K = K7.value
        dynamics.step(getInput(phase))
      }
      simState.value = dynamics.state.slice()
      simHistory.value.push({ t: simTime.value, state: dynamics.state.slice(), phase })
    }

    simTime.value += SIM_TS
  }

  simTimer = requestAnimationFrame(simLoop)
}

function stopSimulation() {
  simRunning.value = false
  if (simTimer) cancelAnimationFrame(simTimer)
}

function restartSimulation() {
  stopSimulation()
  nextTick(() => startSimulation())
}

function restartWithIntro() {
  stopSimulation()
  nextTick(() => {
    startSimulation()
    sceneRef.value?.playCameraIntro()
  })
}

defineExpose({ restartWithIntro })

// Auto-restart on K change
watch(K7, () => {
  if (!kError.value) restartSimulation()
})

// Restart on dynamics mode change
watch(useLinear, () => {
  if (!kError.value) restartSimulation()
})

onMounted(() => {
  if (!kError.value) startSimulation()
})

// ── Chart area alignment ────────────────────────────────────────────────────
const chartPadding = ref(null)
function onChartArea(area) {
  chartPadding.value = area
}

// ── Pole dragging from plot ─────────────────────────────────────────────────
function onPoleDragged(index, re, im) {
  if (index === 0) { poleParams.p0_re = re }
  else if (index === 1) { poleParams.p1_re = re }
  else if (index === 2 || index === 3) { poleParams.p2_re = re; poleParams.p2_im = Math.abs(im) }
  else if (index === 4) { poleParams.p4_re = re }
  else if (index === 5) { poleParams.p5_re = re }
}
</script>

<template>
  <div class="core-layout">
    <!-- Left: 3D Scene + State Plot -->
    <div class="panel panel-left">
      <div class="left-top">
        <BabylonScene
          ref="sceneRef"
          :state="simState"
          :phase="simPhase"
          :dark-mode="darkMode"
          @restart="restartSimulation"
        />
      </div>
      <div class="left-bottom">
        <SimTimeline
          :time="simTime"
          :total="totalDuration"
          :phase="simPhase"
          :running="simRunning"
          :align-padding="chartPadding"
          :phases="[
            { name: 'lying', duration: PHASE_LYING, label: 'Fallen', color: 'var(--text-dim)' },
            { name: 'standup', duration: PHASE_STANDUP, label: 'Stand up', color: 'var(--success)' },
            { name: 'step_neg', duration: PHASE_STEP_NEG, label: 'Step forward', color: 'var(--danger)' },
            { name: 'pause', duration: PHASE_PAUSE, label: 'Pause', color: 'var(--text-dim)' },
            { name: 'step_pos', duration: PHASE_STEP_POS, label: 'Step backward', color: 'var(--accent)' },
            { name: 'settle', duration: PHASE_SETTLE, label: 'Settle', color: 'var(--warning)' },
          ]"
        />
        <StatePlot
          :history="simHistory"
          :total-duration="totalDuration"
          :dark-mode="darkMode"
          :state-labels="stateLabels"
          :state-indices="plotIndices"
          :state-colors="plotColors"
          :state-dashes="plotDashes"
          @chart-area="onChartArea"
        />
      </div>
    </div>

    <!-- Right: Pole plot + controls -->
    <div class="panel panel-controls">
      <div class="right-top">
        <PolePlot
          :poles="poles"
          :dark-mode="darkMode"
          @pole-dragged="onPoleDragged"
        />
      </div>
      <div class="right-bottom">
        <PoleControls
          :pole-params="poleParams"
          :k-error="kError"
          :use-linear="useLinear"
          :ext-input-mag="extInputMag"
          :dark-mode="darkMode"
          @restart="restartSimulation"
          @update:use-linear="useLinear = $event"
          @update:ext-input-mag="extInputMag = $event"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.core-layout {
  display: grid;
  grid-template-columns: 1fr 420px;
  flex: 1;
  overflow: hidden;
}

.panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-left {
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}

.left-top {
  flex: 2.5;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.left-bottom {
  flex: 1.2;
  min-height: 0;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}

.panel-controls {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-top {
  flex: 1;
  min-height: 80px;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
}

.right-bottom {
  flex: 0 0 auto;
  overflow-y: auto;
}
</style>
