<template>
  <div class="historical-view">
    <div class="view-header panel-bracketed">
      <h2>◉ HISTORICAL ANALYSIS</h2>
    </div>

    <!-- Upload Section -->
    <div class="upload-panel panel fade-in">
      <h3 class="section-title">UPLOAD METRICS SNAPSHOT</h3>
      <div class="upload-area">
        <input
          ref="fileInput"
          type="file"
          accept=".json"
          @change="handleFileUpload"
          class="file-input"
        />
        <div class="upload-prompt" @click="$refs.fileInput.click()">
          <div class="upload-icon">📁</div>
          <div class="upload-text">
            <p class="text-cyan">CLICK TO SELECT FILE</p>
            <p class="text-muted">metrics_snapshot.json</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Snapshot Analysis -->
    <div v-if="snapshot" class="analysis-panel panel scanning fade-in">
      <h3 class="section-title">SNAPSHOT ANALYSIS</h3>

      <div class="analysis-grid">
        <!-- Summary Metrics -->
        <div class="metric-card">
          <div class="metric-label">TIMESTAMP</div>
          <div class="metric-value mono">
            {{ formatTimestamp(snapshot.timestamp) }}
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-label">HTTP REQUESTS</div>
          <div class="metric-value">
            {{ calculateTotalRequests() }}
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-label">ERRORS</div>
          <div class="metric-value text-danger">
            {{ calculateTotalErrors() }}
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-label">JOURNEYS</div>
          <div class="metric-value">
            {{ calculateTotalJourneys() }}
          </div>
        </div>
      </div>

      <!-- Raw JSON Viewer -->
      <div class="json-viewer">
        <div class="viewer-header">
          <span class="text-amber">RAW SNAPSHOT DATA</span>
          <button @click="downloadSnapshot">DOWNLOAD</button>
        </div>
        <div class="terminal-output">
          <pre class="mono">{{ JSON.stringify(snapshot, null, 2) }}</pre>
        </div>
      </div>
    </div>

    <!-- No Data Message -->
    <div v-if="!snapshot" class="empty-state panel">
      <div class="empty-icon">◉</div>
      <h3>NO SNAPSHOT LOADED</h3>
      <p class="text-muted">Upload a metrics_snapshot.json file to analyze historical data</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useMetricsStore } from '../stores/metricsStore'

const metricsStore = useMetricsStore()

const fileInput = ref(null)
const snapshot = ref(null)

async function handleFileUpload(event) {
  const file = event.target.files[0]
  if (!file) return

  try {
    const text = await file.text()
    const data = JSON.parse(text)

    // Upload to backend
    await metricsStore.uploadSnapshot(data)

    // Display locally
    snapshot.value = data
  } catch (error) {
    console.error('Failed to load snapshot:', error)
    alert('Failed to load snapshot: ' + error.message)
  }
}

function formatTimestamp(ts) {
  const date = new Date(ts * 1000)
  return date.toISOString().replace('T', ' ').split('.')[0] + ' UTC'
}

function calculateTotalRequests() {
  if (!snapshot.value?.counters?.ironswarm_http_requests_total) return 0
  const metric = snapshot.value.counters.ironswarm_http_requests_total
  if (!metric.samples || !Array.isArray(metric.samples)) return 0
  return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
}

function calculateTotalErrors() {
  if (!snapshot.value?.counters?.ironswarm_http_errors_total) return 0
  const metric = snapshot.value.counters.ironswarm_http_errors_total
  if (!metric.samples || !Array.isArray(metric.samples)) return 0
  return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
}

function calculateTotalJourneys() {
  if (!snapshot.value?.counters?.ironswarm_journey_executions_total) return 0
  const metric = snapshot.value.counters.ironswarm_journey_executions_total
  if (!metric.samples || !Array.isArray(metric.samples)) return 0
  return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
}

function downloadSnapshot() {
  if (!snapshot.value) return

  const dataStr = JSON.stringify(snapshot.value, null, 2)
  const blob = new Blob([dataStr], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `ironswarm_snapshot_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.historical-view {
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
   UPLOAD PANEL
   ═══════════════════════════════════════════════════════════════════ */

.upload-panel {
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

.upload-area {
  position: relative;
}

.file-input {
  display: none;
}

.upload-prompt {
  border: 2px dashed var(--color-cyan);
  padding: var(--spacing-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--color-bg-panel);
}

.upload-prompt:hover {
  border-color: var(--color-amber);
  background: rgba(0, 255, 255, 0.05);
}

.upload-icon {
  font-size: 64px;
  opacity: 0.5;
}

.upload-text {
  text-align: center;
}

.upload-text p {
  margin: 0;
}

/* ═══════════════════════════════════════════════════════════════════
   ANALYSIS PANEL
   ═══════════════════════════════════════════════════════════════════ */

.analysis-panel {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-md);
}

/* ═══════════════════════════════════════════════════════════════════
   JSON VIEWER
   ═══════════════════════════════════════════════════════════════════ */

.json-viewer {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--border-color-dim);
}

.terminal-output {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-success);
  padding: var(--spacing-md);
  max-height: 500px;
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

/* ═══════════════════════════════════════════════════════════════════
   EMPTY STATE
   ═══════════════════════════════════════════════════════════════════ */

.empty-state {
  background: var(--color-bg-surface);
  border: 1px dashed var(--border-color-dim);
  padding: var(--spacing-xl);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
}

.empty-icon {
  font-size: 64px;
  opacity: 0.3;
}

.empty-state h3 {
  margin: 0;
  color: var(--color-text-muted);
}
</style>
