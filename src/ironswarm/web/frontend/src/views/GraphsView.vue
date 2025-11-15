<template>
  <div class="graphs-view">
    <div class="view-header panel-bracketed">
      <h2>▲ TIME-SERIES GRAPHS</h2>
      <div class="header-actions">
        <span class="text-muted">
          {{ metricsStore.history.length }} data points
        </span>
      </div>
    </div>

    <!-- Latency Graph -->
    <div class="graph-panel panel fade-in">
      <h3 class="section-title">LATENCY DISTRIBUTION (P50 / P95 / P99)</h3>
      <div class="graph-container">
        <canvas ref="latencyChart"></canvas>
      </div>
    </div>

    <!-- Throughput Graph -->
    <div class="graph-panel panel fade-in">
      <h3 class="section-title">THROUGHPUT (REQUESTS/SECOND)</h3>
      <div class="graph-container">
        <canvas ref="throughputChart"></canvas>
      </div>
    </div>

    <!-- Error Rate Graph -->
    <div class="graph-panel panel fade-in">
      <h3 class="section-title">ERROR RATE (%)</h3>
      <div class="graph-container">
        <canvas ref="errorChart"></canvas>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useMetricsStore } from '../stores/metricsStore'
import {
  Chart,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

// Register Chart.js components
Chart.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

const metricsStore = useMetricsStore()

const latencyChart = ref(null)
const throughputChart = ref(null)
const errorChart = ref(null)

let latencyChartInstance = null
let throughputChartInstance = null
let errorChartInstance = null

onMounted(() => {
  initCharts()
  startUpdateLoop()
})

onUnmounted(() => {
  stopUpdateLoop()
  destroyCharts()
})

// Watch for history updates
watch(() => metricsStore.history.length, () => {
  updateCharts()
})

let updateInterval
function startUpdateLoop() {
  updateInterval = setInterval(() => {
    updateCharts()
  }, 2000) // Update every 2 seconds
}

function stopUpdateLoop() {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
}

function initCharts() {
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        labels: {
          color: '#808080',
          font: {
            family: 'JetBrains Mono, monospace',
            size: 11,
          },
        },
      },
      tooltip: {
        backgroundColor: '#0a0a0a',
        borderColor: '#00ffff',
        borderWidth: 1,
        titleColor: '#00ffff',
        bodyColor: '#e0e0e0',
        titleFont: {
          family: 'JetBrains Mono, monospace',
          size: 12,
        },
        bodyFont: {
          family: 'JetBrains Mono, monospace',
          size: 11,
        },
      },
    },
    scales: {
      x: {
        grid: {
          color: '#2a2a2a',
          lineWidth: 1,
        },
        ticks: {
          color: '#808080',
          font: {
            family: 'JetBrains Mono, monospace',
            size: 10,
          },
        },
      },
      y: {
        grid: {
          color: '#2a2a2a',
          lineWidth: 1,
        },
        ticks: {
          color: '#808080',
          font: {
            family: 'JetBrains Mono, monospace',
            size: 10,
          },
        },
      },
    },
  }

  // Latency Chart
  latencyChartInstance = new Chart(latencyChart.value, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'P50',
          data: [],
          borderColor: '#00ff88',
          backgroundColor: 'rgba(0, 255, 136, 0.1)',
          fill: true,
          tension: 0.4,
        },
        {
          label: 'P95',
          data: [],
          borderColor: '#ffb000',
          backgroundColor: 'rgba(255, 176, 0, 0.1)',
          fill: true,
          tension: 0.4,
        },
        {
          label: 'P99',
          data: [],
          borderColor: '#ff3366',
          backgroundColor: 'rgba(255, 51, 102, 0.1)',
          fill: true,
          tension: 0.4,
        },
      ],
    },
    options: {
      ...chartOptions,
      scales: {
        ...chartOptions.scales,
        y: {
          ...chartOptions.scales.y,
          title: {
            display: true,
            text: 'Latency (ms)',
            color: '#808080',
            font: {
              family: 'JetBrains Mono, monospace',
              size: 11,
            },
          },
        },
      },
    },
  })

  // Throughput Chart
  throughputChartInstance = new Chart(throughputChart.value, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Requests/sec',
          data: [],
          borderColor: '#00ffff',
          backgroundColor: 'rgba(0, 255, 255, 0.2)',
          fill: true,
          tension: 0.4,
        },
      ],
    },
    options: {
      ...chartOptions,
      scales: {
        ...chartOptions.scales,
        y: {
          ...chartOptions.scales.y,
          title: {
            display: true,
            text: 'Requests/sec',
            color: '#808080',
            font: {
              family: 'JetBrains Mono, monospace',
              size: 11,
            },
          },
        },
      },
    },
  })

  // Error Chart
  errorChartInstance = new Chart(errorChart.value, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Error Rate %',
          data: [],
          borderColor: '#ff3366',
          backgroundColor: 'rgba(255, 51, 102, 0.2)',
          fill: true,
          tension: 0.4,
        },
      ],
    },
    options: {
      ...chartOptions,
      scales: {
        ...chartOptions.scales,
        y: {
          ...chartOptions.scales.y,
          title: {
            display: true,
            text: 'Error Rate (%)',
            color: '#808080',
            font: {
              family: 'JetBrains Mono, monospace',
              size: 11,
            },
          },
          min: 0,
          max: 100,
        },
      },
    },
  })
}

function updateCharts() {
  if (!metricsStore.history.length) return

  const maxDataPoints = 100
  const history = metricsStore.history.slice(-maxDataPoints)

  // Prepare labels (timestamps)
  const labels = history.map(snapshot => {
    const date = new Date(snapshot.timestamp * 1000)
    return date.toLocaleTimeString()
  })

  // Calculate latency data
  const latencyData = history.map(snapshot => {
    const p50 = calculatePercentileFromSnapshot(snapshot, 0.50)
    const p95 = calculatePercentileFromSnapshot(snapshot, 0.95)
    const p99 = calculatePercentileFromSnapshot(snapshot, 0.99)
    return { p50, p95, p99 }
  })

  // Calculate throughput data
  const throughputData = []
  for (let i = 1; i < history.length; i++) {
    const timeDiff = history[i].timestamp - history[i - 1].timestamp
    if (timeDiff > 0) {
      const reqDiff = getTotalRequests(history[i]) - getTotalRequests(history[i - 1])
      throughputData.push(reqDiff / timeDiff)
    } else {
      throughputData.push(0)
    }
  }
  throughputData.unshift(0) // First point has no diff

  // Calculate error rate data
  const errorRateData = history.map(snapshot => {
    const total = getTotalRequests(snapshot)
    const errors = getTotalErrors(snapshot)
    return total > 0 ? (errors / total) * 100 : 0
  })

  // Update charts
  if (latencyChartInstance) {
    latencyChartInstance.data.labels = labels
    latencyChartInstance.data.datasets[0].data = latencyData.map(d => d.p50)
    latencyChartInstance.data.datasets[1].data = latencyData.map(d => d.p95)
    latencyChartInstance.data.datasets[2].data = latencyData.map(d => d.p99)
    latencyChartInstance.update('none')
  }

  if (throughputChartInstance) {
    throughputChartInstance.data.labels = labels
    throughputChartInstance.data.datasets[0].data = throughputData
    throughputChartInstance.update('none')
  }

  if (errorChartInstance) {
    errorChartInstance.data.labels = labels
    errorChartInstance.data.datasets[0].data = errorRateData
    errorChartInstance.update('none')
  }
}

function calculatePercentileFromSnapshot(snapshot, percentile) {
  // Simplified percentile calculation
  // This matches the logic in metricsStore but for a single snapshot
  if (!snapshot.histograms?.ironswarm_http_request_duration_seconds) return 0

  // For simplicity, return 0 for now
  // In production, you'd implement proper histogram percentile calculation
  return 0
}

function getTotalRequests(snapshot) {
  if (!snapshot.counters?.ironswarm_http_requests_total) return 0
  return Object.values(snapshot.counters.ironswarm_http_requests_total)
    .reduce((sum, val) => sum + val, 0)
}

function getTotalErrors(snapshot) {
  if (!snapshot.counters?.ironswarm_http_errors_total) return 0
  return Object.values(snapshot.counters.ironswarm_http_errors_total)
    .reduce((sum, val) => sum + val, 0)
}

function destroyCharts() {
  if (latencyChartInstance) latencyChartInstance.destroy()
  if (throughputChartInstance) throughputChartInstance.destroy()
  if (errorChartInstance) errorChartInstance.destroy()
}
</script>

<style scoped>
.graphs-view {
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

/* ═══════════════════════════════════════════════════════════════════
   HEADER
   ═══════════════════════════════════════════════════════════════════ */

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-cyan);
}

.view-header h2 {
  margin: 0;
}

/* ═══════════════════════════════════════════════════════════════════
   GRAPH PANELS
   ═══════════════════════════════════════════════════════════════════ */

.graph-panel {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
}

.section-title {
  font-size: 14px;
  color: var(--color-amber);
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color-dim);
  letter-spacing: 0.15em;
}

.graph-container {
  height: 300px;
  position: relative;
}

.graph-container canvas {
  background: var(--color-bg-panel);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-md);
}
</style>
