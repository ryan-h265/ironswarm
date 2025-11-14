<template>
  <div class="metrics-view">
    <div class="view-header panel-bracketed">
      <h2>◈ LIVE METRICS</h2>
      <div class="header-actions">
        <span :class="['status-badge', wsStore.isConnected ? 'live' : 'offline']">
          <span class="pulse-dot"></span>
          {{ wsStore.isConnected ? 'STREAMING' : 'DISCONNECTED' }}
        </span>
      </div>
    </div>

    <!-- Primary Metrics Grid -->
    <div class="metrics-grid">
      <div class="metric-card fade-in">
        <div class="metric-label">HTTP REQUESTS</div>
        <div class="metric-value">
          {{ formatNumber(metricsStore.totalRequests) }}
          <span class="metric-unit">total</span>
        </div>
        <div class="metric-footer">
          <span class="text-cyan">{{ metricsStore.throughput }}</span>
          <span class="metric-unit">req/s</span>
        </div>
      </div>

      <div class="metric-card fade-in">
        <div class="metric-label">ERROR RATE</div>
        <div :class="['metric-value', errorRateClass]">
          {{ metricsStore.errorRate }}
          <span class="metric-unit">%</span>
        </div>
        <div class="metric-footer">
          <span class="text-danger">{{ formatNumber(metricsStore.totalErrors) }}</span>
          <span class="metric-unit">errors</span>
        </div>
      </div>

      <div class="metric-card fade-in">
        <div class="metric-label">JOURNEYS</div>
        <div class="metric-value">
          {{ formatNumber(metricsStore.totalJourneys) }}
          <span class="metric-unit">executed</span>
        </div>
        <div class="metric-footer">
          <span class="text-amber">{{ formatNumber(metricsStore.journeyFailures) }}</span>
          <span class="metric-unit">failures</span>
        </div>
      </div>

      <div class="metric-card fade-in">
        <div class="metric-label">LATENCY P99</div>
        <div class="metric-value">
          {{ metricsStore.latencyP99 }}
          <span class="metric-unit">ms</span>
        </div>
        <div class="metric-footer">
          <span class="text-muted">P95:</span>
          <span class="text-cyan">{{ metricsStore.latencyP95 }}ms</span>
        </div>
      </div>
    </div>

    <!-- Latency Breakdown -->
    <div class="latency-panel panel scanning">
      <h3 class="section-title">◈ LATENCY DISTRIBUTION</h3>
      <div class="latency-bars">
        <div class="latency-bar-item">
          <div class="bar-label">
            <span>P50</span>
            <span class="text-success">{{ metricsStore.latencyP50 }} ms</span>
          </div>
          <div class="bar-track">
            <div
              class="bar-fill success"
              :style="{ width: `${calculateBarWidth(metricsStore.latencyP50)}%` }"
            ></div>
          </div>
        </div>

        <div class="latency-bar-item">
          <div class="bar-label">
            <span>P95</span>
            <span class="text-amber">{{ metricsStore.latencyP95 }} ms</span>
          </div>
          <div class="bar-track">
            <div
              class="bar-fill amber"
              :style="{ width: `${calculateBarWidth(metricsStore.latencyP95)}%` }"
            ></div>
          </div>
        </div>

        <div class="latency-bar-item">
          <div class="bar-label">
            <span>P99</span>
            <span class="text-danger">{{ metricsStore.latencyP99 }} ms</span>
          </div>
          <div class="bar-track">
            <div
              class="bar-fill danger"
              :style="{ width: `${calculateBarWidth(metricsStore.latencyP99)}%` }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Raw Metrics Data -->
    <div class="raw-metrics panel">
      <h3 class="section-title">◈ RAW SNAPSHOT DATA</h3>
      <div class="terminal-output">
        <pre class="mono">{{ formattedSnapshot }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useMetricsStore } from '../stores/metricsStore'
import { useWebSocketStore } from '../stores/websocketStore'

const metricsStore = useMetricsStore()
const wsStore = useWebSocketStore()

const errorRateClass = computed(() => {
  const rate = parseFloat(metricsStore.errorRate)
  if (rate === 0) return 'text-success'
  if (rate < 5) return 'text-amber'
  return 'text-danger'
})

const formattedSnapshot = computed(() => {
  if (!metricsStore.currentSnapshot) return 'NO DATA'
  return JSON.stringify(metricsStore.currentSnapshot, null, 2)
})

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(2) + 'K'
  return num.toString()
}

function calculateBarWidth(value) {
  // Normalize to 0-100 based on max value being around 2000ms
  const maxLatency = 2000
  const width = (parseFloat(value) / maxLatency) * 100
  return Math.min(width, 100)
}
</script>

<style scoped>
.metrics-view {
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
   METRICS GRID
   ═══════════════════════════════════════════════════════════════════ */

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-md);
}

.metric-card::before {
  background: var(--color-cyan);
}

.metric-footer {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: 14px;
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-color-dim);
}

/* ═══════════════════════════════════════════════════════════════════
   LATENCY PANEL
   ═══════════════════════════════════════════════════════════════════ */

.latency-panel {
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

.latency-bars {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.latency-bar-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.bar-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.bar-track {
  height: 24px;
  background: var(--color-bg-panel);
  border: 1px solid var(--border-color-dim);
  position: relative;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width 0.5s ease;
  position: relative;
}

.bar-fill::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  width: 4px;
  height: 100%;
  background: currentColor;
  box-shadow: 0 0 10px currentColor;
}

.bar-fill.success {
  background: linear-gradient(90deg,
    rgba(0, 255, 136, 0.2),
    rgba(0, 255, 136, 0.5)
  );
  color: var(--color-success);
}

.bar-fill.amber {
  background: linear-gradient(90deg,
    rgba(255, 176, 0, 0.2),
    rgba(255, 176, 0, 0.5)
  );
  color: var(--color-amber);
}

.bar-fill.danger {
  background: linear-gradient(90deg,
    rgba(255, 51, 102, 0.2),
    rgba(255, 51, 102, 0.5)
  );
  color: var(--color-danger);
}

/* ═══════════════════════════════════════════════════════════════════
   RAW METRICS
   ═══════════════════════════════════════════════════════════════════ */

.raw-metrics {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
}

.terminal-output {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-success);
  padding: var(--spacing-md);
  max-height: 400px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.6;
  box-shadow: inset 0 0 20px rgba(0, 255, 0, 0.1);
}

.terminal-output pre {
  margin: 0;
  color: var(--color-success);
  font-family: var(--font-mono);
  white-space: pre-wrap;
  word-wrap: break-word;
}

.terminal-output::-webkit-scrollbar {
  width: 8px;
}

.terminal-output::-webkit-scrollbar-track {
  background: var(--color-bg-panel);
}

.terminal-output::-webkit-scrollbar-thumb {
  background: var(--color-success);
}
</style>
