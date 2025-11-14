<template>
  <div class="scenarios-view">
    <div class="view-header panel-bracketed">
      <h2>⚡ SCENARIOS</h2>
      <div class="header-actions">
        <button @click="fetchAvailableScenarios">REFRESH AVAILABLE</button>
        <button @click="fetchScenarios">REFRESH ACTIVE</button>
      </div>
    </div>

    <!-- Available Scenarios Section -->
    <div class="section-panel panel scanning">
      <div class="section-header">
        <h3 class="section-title">AVAILABLE SCENARIOS</h3>
        <div class="upload-controls">
          <input
            ref="fileInput"
            type="file"
            accept=".py"
            style="display: none"
            @change="handleFileSelect"
          />
          <button @click="$refs.fileInput.click()" class="upload-btn">
            UPLOAD SCENARIO FILE
          </button>
        </div>
      </div>

      <div v-if="uploadStatus" :class="['upload-status', uploadStatus.type]">
        {{ uploadStatus.message }}
      </div>

      <div class="available-scenarios-grid">
        <div
          v-for="scenario in availableScenarios"
          :key="scenario.name"
          :class="['available-scenario-card', 'panel', scenario.valid ? '' : 'invalid']"
        >
          <div class="scenario-header">
            <h4 class="scenario-name mono">{{ scenario.name }}</h4>
            <span v-if="!scenario.valid" class="status-badge offline">
              INVALID
            </span>
          </div>

          <div v-if="scenario.error" class="error-message">
            {{ scenario.error }}
          </div>

          <div v-if="scenario.valid && scenario.metadata" class="scenario-metadata">
            <div class="meta-row">
              <span class="label">Journeys:</span>
              <span class="value text-cyan">{{ scenario.metadata.journey_count }}</span>
            </div>
            <div class="meta-row">
              <span class="label">Delay:</span>
              <span class="value">{{ scenario.metadata.delay }}s</span>
            </div>
            <div class="meta-row">
              <span class="label">Interval:</span>
              <span class="value">{{ scenario.metadata.interval }}s</span>
            </div>

            <div v-if="scenario.metadata.journeys" class="journeys-preview">
              <div class="journeys-label">Journeys:</div>
              <div
                v-for="(journey, idx) in scenario.metadata.journeys"
                :key="idx"
                class="journey-preview-item"
              >
                <span class="journey-spec mono">{{ journey.spec }}</span>
                <span class="text-muted">→</span>
                <span v-if="journey.volumemodel" class="text-cyan">
                  {{ journey.volumemodel.target }} req/s
                  ({{ journey.volumemodel.duration }}s)
                </span>
              </div>
            </div>
          </div>

          <div v-if="scenario.valid" class="scenario-actions">
            <button
              @click="startScenario(scenario.module_spec)"
              class="start-btn"
              :disabled="isScenarioRunning(scenario.module_spec)"
            >
              {{ isScenarioRunning(scenario.module_spec) ? 'RUNNING' : 'START SCENARIO' }}
            </button>
          </div>
        </div>

        <div v-if="availableScenarios.length === 0" class="empty-state panel">
          <div class="empty-icon">📁</div>
          <h3>NO SCENARIOS FOUND</h3>
          <p class="text-muted">Upload a scenario file or add .py files to {{ scenariosDir }}</p>
        </div>
      </div>
    </div>

    <!-- Running Scenarios -->
    <div class="section-panel panel scanning">
      <h3 class="section-title">RUNNING SCENARIOS</h3>

      <div class="scenarios-grid">
        <div
          v-for="(scenario, index) in scenarios"
          :key="scenario.id || index"
          class="scenario-card panel fade-in"
        >
          <div class="scenario-header">
            <h3 class="scenario-id mono">{{ scenario.id || 'Unknown' }}</h3>
          <span :class="['status-badge', scenario.active ? 'live' : 'offline']">
            <span class="pulse-dot"></span>
            {{ scenario.active ? 'ACTIVE' : 'STOPPED' }}
          </span>
        </div>

        <div class="scenario-body">
          <div class="scenario-meta">
            <span class="label">JOURNEYS:</span>
            <span class="value text-cyan">{{ getJourneyCount(scenario) }}</span>
          </div>

          <div v-if="scenario.data" class="scenario-details">
            <pre class="mono">{{ JSON.stringify(scenario.data, null, 2) }}</pre>
          </div>
        </div>

        <div class="scenario-actions">
          <button class="danger" @click="stopScenario(scenario.id)">
            STOP SCENARIO
          </button>
        </div>
      </div>

        <!-- No Scenarios Message -->
        <div v-if="scenarios.length === 0" class="empty-state panel">
          <div class="empty-icon">⚡</div>
          <h3>NO ACTIVE SCENARIOS</h3>
          <p class="text-muted">Start a scenario from the available scenarios above</p>
        </div>
      </div>
    </div>

    <!-- Scenario Manager Info -->
    <div v-if="scenarioManagers.length > 0" class="managers-panel panel scanning">
      <h3 class="section-title">SCENARIO MANAGERS</h3>
      <div class="managers-list">
        <div
          v-for="(manager, index) in scenarioManagers"
          :key="manager.index"
          class="manager-item"
        >
          <div class="manager-header">
            <span class="mono text-amber">Manager #{{ manager.index }}</span>
            <span :class="['status-badge', manager.running ? 'live' : 'offline']">
              {{ manager.running ? 'RUNNING' : 'STOPPED' }}
            </span>
          </div>

          <div v-if="manager.start_time" class="manager-meta">
            <span class="text-muted">Start Time:</span>
            <span class="mono">{{ formatTimestamp(manager.start_time) }}</span>
          </div>

          <div v-if="manager.journeys" class="journey-list">
            <div
              v-for="(journey, jIndex) in manager.journeys"
              :key="jIndex"
              class="journey-item"
            >
              <span class="journey-spec mono">{{ journey.spec }}</span>
              <span class="text-muted">→</span>
              <span class="text-cyan">{{ journey.volumemodel?.target || 0 }} req/s</span>
              <span v-if="journey.volumemodel?.duration" class="text-muted">
                ({{ journey.volumemodel.duration }}s)
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const scenarios = ref([])
const scenarioManagers = ref([])
const availableScenarios = ref([])
const scenariosDir = ref('./scenarios')
const uploadStatus = ref(null)
const fileInput = ref(null)

onMounted(() => {
  fetchScenarios()
  fetchAvailableScenarios()
})

async function fetchScenarios() {
  try {
    const response = await axios.get('/api/scenarios')
    scenarios.value = response.data.scenarios || []
    scenarioManagers.value = response.data.scenario_managers || []
  } catch (error) {
    console.error('Failed to fetch scenarios:', error)
  }
}

async function fetchAvailableScenarios() {
  try {
    const response = await axios.get('/api/scenarios/available')
    availableScenarios.value = response.data.scenarios || []
    scenariosDir.value = response.data.scenarios_dir || './scenarios'
  } catch (error) {
    console.error('Failed to fetch available scenarios:', error)
  }
}

async function handleFileSelect(event) {
  const file = event.target.files[0]
  if (!file) return

  uploadStatus.value = { type: 'info', message: 'Uploading...' }

  try {
    const formData = new FormData()
    formData.append('file', file)

    const response = await axios.post('/api/scenarios/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })

    uploadStatus.value = {
      type: 'success',
      message: `Successfully uploaded ${response.data.filename}`
    }

    // Refresh available scenarios
    await fetchAvailableScenarios()

    // Clear file input
    event.target.value = ''

    // Clear status after 3 seconds
    setTimeout(() => {
      uploadStatus.value = null
    }, 3000)

  } catch (error) {
    uploadStatus.value = {
      type: 'error',
      message: `Upload failed: ${error.response?.data?.error || error.message}`
    }
  }
}

async function startScenario(scenarioSpec) {
  if (!confirm(`Start scenario ${scenarioSpec}?`)) return

  try {
    await axios.post('/api/scenarios', {
      scenario_spec: scenarioSpec
    })

    uploadStatus.value = {
      type: 'success',
      message: `Started scenario: ${scenarioSpec}`
    }

    // Refresh running scenarios
    await fetchScenarios()

    // Clear status after 3 seconds
    setTimeout(() => {
      uploadStatus.value = null
    }, 3000)

  } catch (error) {
    uploadStatus.value = {
      type: 'error',
      message: `Failed to start scenario: ${error.response?.data?.error || error.message}`
    }
  }
}

async function stopScenario(scenarioId) {
  if (!confirm(`Stop scenario ${scenarioId}?`)) return

  try {
    await axios.delete(`/api/scenarios/${scenarioId}`)
    await fetchScenarios()
  } catch (error) {
    console.error('Failed to stop scenario:', error)
    uploadStatus.value = {
      type: 'error',
      message: `Failed to stop scenario: ${error.response?.data?.error || error.message}`
    }
  }
}

function isScenarioRunning(moduleSpec) {
  return scenarios.value.some(s => s.id === moduleSpec)
}

function getJourneyCount(scenario) {
  if (scenario.data?.journeys) {
    return scenario.data.journeys.length
  }
  return 0
}

function formatTimestamp(ts) {
  const date = new Date(ts * 1000)
  return date.toLocaleTimeString()
}
</script>

<style scoped>
.scenarios-view {
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

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

/* ═══════════════════════════════════════════════════════════════════
   SECTION PANEL
   ═══════════════════════════════════════════════════════════════════ */

.section-panel {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color-dim);
}

.upload-controls {
  display: flex;
  gap: var(--spacing-sm);
}

.upload-btn {
  background: var(--color-cyan);
  color: var(--color-bg-main);
  border: none;
  padding: var(--spacing-xs) var(--spacing-md);
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  transition: all 0.2s ease;
}

.upload-btn:hover {
  background: var(--color-amber);
  transform: translateY(-2px);
}

.upload-status {
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  border-left: 3px solid;
  font-size: 12px;
}

.upload-status.info {
  background: rgba(0, 255, 255, 0.1);
  border-color: var(--color-cyan);
  color: var(--color-cyan);
}

.upload-status.success {
  background: rgba(0, 255, 0, 0.1);
  border-color: #00ff00;
  color: #00ff00;
}

.upload-status.error {
  background: rgba(255, 0, 0, 0.1);
  border-color: #ff0000;
  color: #ff0000;
}

/* ═══════════════════════════════════════════════════════════════════
   AVAILABLE SCENARIOS
   ═══════════════════════════════════════════════════════════════════ */

.available-scenarios-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: var(--spacing-md);
}

.available-scenario-card {
  background: var(--color-bg-panel);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  transition: all 0.2s ease;
}

.available-scenario-card:hover {
  border-color: var(--color-cyan);
  transform: translateY(-2px);
}

.available-scenario-card.invalid {
  border-color: #ff0000;
  opacity: 0.7;
}

.scenario-name {
  font-size: 14px;
  color: var(--color-cyan);
  margin: 0;
}

.error-message {
  font-size: 11px;
  color: #ff0000;
  padding: var(--spacing-xs);
  background: rgba(255, 0, 0, 0.1);
  border-left: 2px solid #ff0000;
}

.scenario-metadata {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.meta-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: 11px;
}

.meta-row .label {
  color: var(--color-text-muted);
  min-width: 60px;
}

.meta-row .value {
  font-weight: 700;
}

.journeys-preview {
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-color-dim);
}

.journeys-label {
  font-size: 10px;
  color: var(--color-text-muted);
  letter-spacing: 0.1em;
  margin-bottom: var(--spacing-xs);
}

.journey-preview-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: 10px;
  padding: var(--spacing-xs) 0;
}

.start-btn {
  background: var(--color-cyan);
  color: var(--color-bg-main);
  border: none;
  padding: var(--spacing-xs) var(--spacing-md);
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  transition: all 0.2s ease;
  width: 100%;
}

.start-btn:hover:not(:disabled) {
  background: var(--color-amber);
  transform: translateY(-2px);
}

.start-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ═══════════════════════════════════════════════════════════════════
   SCENARIOS GRID
   ═══════════════════════════════════════════════════════════════════ */

.scenarios-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: var(--spacing-md);
}

.scenario-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  transition: all 0.2s ease;
}

.scenario-card:hover {
  border-color: var(--color-cyan);
  transform: translateY(-2px);
}

.scenario-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color-dim);
}

.scenario-id {
  font-size: 14px;
  color: var(--color-cyan);
  margin: 0;
}

.scenario-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.scenario-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.scenario-meta .label {
  font-size: 10px;
  color: var(--color-text-muted);
  letter-spacing: 0.1em;
}

.scenario-meta .value {
  font-size: 16px;
  font-weight: 700;
}

.scenario-details {
  background: var(--color-bg-panel);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-sm);
  font-size: 10px;
  max-height: 200px;
  overflow: auto;
}

.scenario-details pre {
  margin: 0;
  color: var(--color-text-muted);
}

.scenario-actions {
  display: flex;
  gap: var(--spacing-sm);
}

/* ═══════════════════════════════════════════════════════════════════
   EMPTY STATE
   ═══════════════════════════════════════════════════════════════════ */

.empty-state {
  grid-column: 1 / -1;
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

/* ═══════════════════════════════════════════════════════════════════
   MANAGERS PANEL
   ═══════════════════════════════════════════════════════════════════ */

.managers-panel {
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

.managers-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.manager-item {
  background: var(--color-bg-panel);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color-dim);
}

.manager-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: 11px;
  padding: var(--spacing-xs) 0;
}

.journey-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  font-size: 12px;
}

.journey-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) 0;
}

.journey-spec {
  color: var(--color-text-primary);
}
</style>
