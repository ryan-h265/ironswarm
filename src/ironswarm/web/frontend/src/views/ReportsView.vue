<template>
  <div class="reports-view">
    <div class="view-header panel-bracketed">
      <h2>▣ REPORTS & EXPORTS</h2>
    </div>

    <!-- Export Options -->
    <div class="export-grid">
      <!-- Text Report -->
      <div class="export-card panel fade-in">
        <div class="export-icon">📄</div>
        <h3>TEXT REPORT</h3>
        <p class="text-muted">
          Generate comprehensive text report with journey statistics,
          HTTP metrics, and performance summaries.
        </p>
        <div class="export-actions">
          <button @click="exportTextReport" :disabled="exporting">
            {{ exporting ? 'GENERATING...' : 'GENERATE REPORT' }}
          </button>
        </div>
      </div>

      <!-- Graphs Bundle -->
      <div class="export-card panel fade-in">
        <div class="export-icon">📊</div>
        <h3>GRAPHS BUNDLE</h3>
        <p class="text-muted">
          Download all performance graphs (latency, throughput, errors)
          as a ZIP archive containing PNG images.
        </p>
        <div class="export-actions">
          <button @click="exportGraphs" :disabled="exporting">
            {{ exporting ? 'GENERATING...' : 'DOWNLOAD GRAPHS' }}
          </button>
        </div>
      </div>

      <!-- Raw Metrics -->
      <div class="export-card panel fade-in">
        <div class="export-icon">📋</div>
        <h3>RAW METRICS JSON</h3>
        <p class="text-muted">
          Export current metrics snapshot as JSON file for
          offline analysis or archival.
        </p>
        <div class="export-actions">
          <button @click="exportMetricsJSON" :disabled="exporting">
            EXPORT JSON
          </button>
        </div>
      </div>

      <!-- Cluster Config -->
      <div class="export-card panel fade-in">
        <div class="export-icon">⚙️</div>
        <h3>CLUSTER CONFIG</h3>
        <p class="text-muted">
          Export current cluster topology and node configuration
          for documentation or reproducibility.
        </p>
        <div class="export-actions">
          <button @click="exportClusterConfig" :disabled="exporting">
            EXPORT CONFIG
          </button>
        </div>
      </div>
    </div>

    <!-- Export History -->
    <div v-if="exportHistory.length > 0" class="history-panel panel scanning">
      <h3 class="section-title">EXPORT HISTORY</h3>
      <div class="history-list">
        <div
          v-for="(item, index) in exportHistory"
          :key="index"
          class="history-item"
        >
          <span class="history-icon">{{ item.icon }}</span>
          <span class="history-type">{{ item.type }}</span>
          <span class="history-time mono text-muted">{{ item.timestamp }}</span>
          <span :class="['status-badge', item.success ? 'live' : 'error']">
            {{ item.success ? 'SUCCESS' : 'FAILED' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Help Section -->
    <div class="help-panel panel">
      <h3 class="section-title">ABOUT EXPORTS</h3>
      <div class="help-content">
        <div class="help-item">
          <strong class="text-cyan">Text Report:</strong>
          <p>
            Generates a human-readable summary including journey execution counts,
            failure rates, HTTP request statistics, and top endpoints by volume and latency.
          </p>
        </div>

        <div class="help-item">
          <strong class="text-cyan">Graphs Bundle:</strong>
          <p>
            Creates latency distribution (P50/P95/P99), throughput (req/s by endpoint),
            and error rate graphs using matplotlib. Downloaded as PNG images in a ZIP file.
          </p>
        </div>

        <div class="help-item">
          <strong class="text-cyan">Raw Metrics:</strong>
          <p>
            Complete metrics snapshot in JSON format containing counters, histograms,
            and event streams. Use for offline analysis or comparison between test runs.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { useMetricsStore } from '../stores/metricsStore'
import { useClusterStore } from '../stores/clusterStore'

const metricsStore = useMetricsStore()
const clusterStore = useClusterStore()

const exporting = ref(false)
const exportHistory = ref([])

async function exportTextReport() {
  exporting.value = true

  try {
    const response = await axios.get('/api/export/report', {
      responseType: 'blob',
    })

    downloadFile(response.data, 'ironswarm_report.txt', 'text/plain')

    addToHistory('Text Report', '📄', true)
  } catch (error) {
    console.error('Failed to export report:', error)
    alert('Failed to export report: ' + error.message)
    addToHistory('Text Report', '📄', false)
  } finally {
    exporting.value = false
  }
}

async function exportGraphs() {
  exporting.value = true

  try {
    const response = await axios.get('/api/export/graphs', {
      responseType: 'blob',
    })

    downloadFile(response.data, 'ironswarm_graphs.zip', 'application/zip')

    addToHistory('Graphs Bundle', '📊', true)
  } catch (error) {
    console.error('Failed to export graphs:', error)
    alert('Failed to export graphs: ' + error.message)
    addToHistory('Graphs Bundle', '📊', false)
  } finally {
    exporting.value = false
  }
}

async function exportMetricsJSON() {
  exporting.value = true

  try {
    const snapshot = metricsStore.currentSnapshot

    if (!snapshot) {
      alert('No metrics available to export')
      return
    }

    const dataStr = JSON.stringify(snapshot, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    downloadFile(blob, 'ironswarm_metrics.json', 'application/json')

    addToHistory('Raw Metrics', '📋', true)
  } catch (error) {
    console.error('Failed to export metrics:', error)
    alert('Failed to export metrics: ' + error.message)
    addToHistory('Raw Metrics', '📋', false)
  } finally {
    exporting.value = false
  }
}

async function exportClusterConfig() {
  exporting.value = true

  try {
    const config = {
      self: clusterStore.self,
      nodes: clusterStore.nodes,
      totalNodes: clusterStore.totalNodes,
      exportedAt: new Date().toISOString(),
    }

    const dataStr = JSON.stringify(config, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    downloadFile(blob, 'ironswarm_cluster_config.json', 'application/json')

    addToHistory('Cluster Config', '⚙️', true)
  } catch (error) {
    console.error('Failed to export config:', error)
    alert('Failed to export config: ' + error.message)
    addToHistory('Cluster Config', '⚙️', false)
  } finally {
    exporting.value = false
  }
}

function downloadFile(data, filename, mimeType) {
  const blob = data instanceof Blob ? data : new Blob([data], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function addToHistory(type, icon, success) {
  exportHistory.value.unshift({
    type,
    icon,
    success,
    timestamp: new Date().toLocaleTimeString(),
  })

  // Keep only last 10 items
  if (exportHistory.value.length > 10) {
    exportHistory.value = exportHistory.value.slice(0, 10)
  }
}
</script>

<style scoped>
.reports-view {
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
   EXPORT GRID
   ═══════════════════════════════════════════════════════════════════ */

.export-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-md);
}

.export-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  text-align: center;
  transition: all 0.2s ease;
}

.export-card:hover {
  border-color: var(--color-cyan);
  transform: translateY(-4px);
}

.export-icon {
  font-size: 48px;
  opacity: 0.7;
}

.export-card h3 {
  margin: 0;
  font-size: 16px;
  color: var(--color-cyan);
}

.export-card p {
  flex: 1;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}

.export-actions {
  width: 100%;
}

.export-actions button {
  width: 100%;
}

/* ═══════════════════════════════════════════════════════════════════
   HISTORY PANEL
   ═══════════════════════════════════════════════════════════════════ */

.history-panel {
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

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-panel);
  border: 1px solid var(--border-color-dim);
  font-size: 12px;
}

.history-icon {
  font-size: 18px;
}

.history-type {
  flex: 1;
  color: var(--color-text-primary);
}

.history-time {
  font-size: 11px;
}

/* ═══════════════════════════════════════════════════════════════════
   HELP PANEL
   ═══════════════════════════════════════════════════════════════════ */

.help-panel {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
}

.help-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.help-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.help-item strong {
  font-size: 13px;
  letter-spacing: 0.05em;
}

.help-item p {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-muted);
}
</style>
