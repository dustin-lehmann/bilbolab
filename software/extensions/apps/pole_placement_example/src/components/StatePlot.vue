<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick, shallowRef } from 'vue'
import { Chart, LineController, LineElement, PointElement, LinearScale, Filler, Legend, Tooltip } from 'chart.js'

Chart.register(LineController, LineElement, PointElement, LinearScale, Filler, Legend, Tooltip)

const props = defineProps({
  history: Array,     // [{ t, state, phase }]
  totalDuration: Number, // fixed x-axis max
  darkMode: Boolean,
  stateLabels: Array, // full label list e.g. ['x','y','v','θ','θ̇','ψ','ψ̇']
  stateIndices: Array, // which indices to plot, e.g. [0,2,3,5]
  stateColors: Array,  // optional per-state colors, matching stateIndices length
  stateDashes: Array,  // optional per-state dash patterns, e.g. [undefined, [6,3]]
})

const emit = defineEmits(['chartArea'])
const canvasRef = ref(null)
let chart = null

const COLORS = [
  '#45aaf2', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22',
]

function buildChart() {
  if (chart) { chart.destroy(); chart = null }
  const canvas = canvasRef.value
  if (!canvas) return

  const indices = props.stateIndices || [0, 2, 3, 5]
  const labels = props.stateLabels || ['x', 'y', 'v', 'θ', 'θ̇', 'ψ', 'ψ̇']

  const gridColor = props.darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
  const tickColor = props.darkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)'
  const zeroLineColor = props.darkMode ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.15)'

  const datasets = indices.map((idx, si) => ({
    label: labels[idx] || `s${idx}`,
    data: [],
    borderColor: (props.stateColors && props.stateColors[si]) || COLORS[si % COLORS.length],
    borderDash: (props.stateDashes && props.stateDashes[si]) || [],
    borderWidth: 1.5,
    pointRadius: 0,
    tension: 0.1,
  }))

  const chartAreaPlugin = {
    id: 'chartAreaEmitter',
    afterLayout(c) {
      const area = c.chartArea
      if (area) {
        const containerPadLeft = 8  // matches .state-plot padding
        const containerPadRight = 8
        emit('chartArea', {
          left: containerPadLeft + area.left,
          right: containerPadRight + (c.width - area.right),
        })
      }
    },
  }

  chart = new Chart(canvas, {
    type: 'line',
    data: { datasets },
    plugins: [chartAreaPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'right',
          align: 'center',
          title: {
            display: true,
            text: ['(click to', 'hide)'],
            color: props.darkMode ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)',
            font: { family: 'JetBrains Mono', size: 9, style: 'italic' },
            padding: { top: 0, bottom: 6 },
          },
          labels: {
            color: tickColor,
            font: { family: 'JetBrains Mono', size: 13 },
            boxWidth: 24,
            boxHeight: 3,
            padding: 16,
          },
        },
        tooltip: {
          enabled: true,
          bodyFont: { family: 'JetBrains Mono', size: 10 },
          titleFont: { family: 'JetBrains Mono', size: 10 },
          callbacks: {
            title: (items) => items[0] ? `t = ${items[0].parsed.x.toFixed(2)}s` : '',
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}`,
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          min: 0,
          max: props.totalDuration || 10,
          title: { display: true, text: 't (s)', color: tickColor, font: { family: 'JetBrains Mono', size: 10 } },
          grid: { color: gridColor },
          ticks: { color: tickColor, font: { family: 'JetBrains Mono', size: 9 } },
        },
        y: {
          type: 'linear',
          grid: {
            color: (ctx) => ctx.tick.value === 0 ? zeroLineColor : gridColor,
            lineWidth: (ctx) => ctx.tick.value === 0 ? 1.5 : 1,
          },
          ticks: { color: tickColor, font: { family: 'JetBrains Mono', size: 9 } },
        },
      },
    },
  })

  updateData()
}

function updateData() {
  if (!chart) return
  const hist = props.history
  if (!hist || hist.length === 0) {
    chart.data.datasets.forEach(ds => { ds.data = [] })
    chart.update('none')
    return
  }

  const indices = props.stateIndices || [0, 2, 3, 5]

  // Downsample for performance
  const maxPts = 600
  const skip = Math.max(1, Math.floor(hist.length / maxPts))

  for (let si = 0; si < indices.length; si++) {
    const idx = indices[si]
    const points = []
    for (let i = 0; i < hist.length; i += skip) {
      points.push({ x: hist[i].t, y: hist[i].state[idx] })
    }
    // Always include last point
    const last = hist[hist.length - 1]
    points.push({ x: last.t, y: last.state[idx] })
    chart.data.datasets[si].data = points
  }
  chart.update('none')
}

// Rebuild chart on theme change (colors change)
watch(() => props.darkMode, () => nextTick(buildChart))

// Update data when history changes
watch(() => props.history, updateData, { deep: false })

// Also watch length changes (history is pushed to, not replaced)
watch(() => props.history?.length, updateData)

onMounted(() => {
  buildChart()
})

onBeforeUnmount(() => {
  if (chart) { chart.destroy(); chart = null }
})
</script>

<template>
  <div class="state-plot" data-tour="state-plot">
    <canvas ref="canvasRef" />
  </div>
</template>

<style scoped>
.state-plot {
  flex: 1;
  min-height: 0;
  position: relative;
  padding: 4px 8px;
}
</style>
