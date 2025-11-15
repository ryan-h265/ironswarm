<template>
  <div class="scenario-builder">
    <!-- Header -->
    <div class="builder-header panel-bracketed">
      <div class="header-left">
        <h2>⚙️ SCENARIO BUILDER</h2>
        <div class="scenario-meta">
          <input
            v-model="store.scenarioName"
            placeholder="Scenario name"
            class="scenario-name-input mono"
          />
          <label class="delay-input-group">
            <span class="label">DELAY (s):</span>
            <input
              v-model.number="store.delay"
              type="number"
              min="0"
              class="delay-input mono"
            />
          </label>
        </div>
      </div>
      <div class="header-actions">
        <select
          v-model="selectedScenarioToLoad"
          @change="loadExistingScenario"
          class="load-scenario-select mono"
        >
          <option value="">Load Existing Scenario...</option>
          <option
            v-for="scenario in availableScenarios"
            :key="scenario.name"
            :value="scenario.name"
          >
            {{ scenario.name }}
          </option>
        </select>
        <button @click="showPreview" :disabled="!store.isValid">PREVIEW CODE</button>
        <button @click="saveScenario" :disabled="!store.isValid" class="primary">SAVE SCENARIO</button>
        <button @click="resetBuilder" class="danger">RESET</button>
      </div>
    </div>

    <!-- Main Layout -->
    <div class="builder-layout">
      <!-- Journey Sidebar -->
      <div class="journey-sidebar panel">
        <div class="sidebar-header">
          <h3>JOURNEYS ({{ store.journeys.length }})</h3>
          <button @click="store.addJourney()" class="add-btn">+ ADD</button>
        </div>

        <div class="journey-list">
          <div
            v-for="(journey, index) in store.journeys"
            :key="index"
            :class="['journey-item', { active: store.selectedJourneyIndex === index }]"
            @click="store.selectJourney(index)"
          >
            <div class="journey-item-header">
              <span class="journey-name mono">{{ journey.name }}</span>
              <span class="journey-badge">{{ journey.requests.length }} req</span>
            </div>
            <div class="journey-meta">
              <span class="text-muted">{{ journey.volumeModel.target }} req/s</span>
              <span v-if="journey.datapool" class="datapool-indicator" title="Uses datapool">💾</span>
            </div>
            <div class="journey-actions" @click.stop>
              <button @click="store.duplicateJourney(index)" title="Duplicate">📋</button>
              <button @click="store.moveJourney(index, 'up')" :disabled="index === 0" title="Move up">↑</button>
              <button @click="store.moveJourney(index, 'down')" :disabled="index === store.journeys.length - 1" title="Move down">↓</button>
              <button @click="store.deleteJourney(index)" class="danger" title="Delete">✕</button>
            </div>
          </div>

          <div v-if="store.journeys.length === 0" class="empty-state">
            <p class="text-muted">No journeys yet</p>
            <button @click="store.addJourney()">ADD FIRST JOURNEY</button>
          </div>
        </div>
      </div>

      <!-- Journey Detail Panel -->
      <div class="journey-detail">
        <div v-if="store.selectedJourney" class="detail-content">
          <!-- Journey Name -->
          <div class="detail-section panel">
            <h3 class="section-title">JOURNEY CONFIG</h3>
            <div class="config-grid">
              <div class="config-item">
                <label class="label">FUNCTION NAME:</label>
                <input
                  v-model="store.selectedJourney.name"
                  placeholder="journey_name"
                  class="mono"
                />
              </div>
              <div class="config-item">
                <label class="label">TARGET (req/s):</label>
                <input
                  v-model.number="store.selectedJourney.volumeModel.target"
                  type="number"
                  min="1"
                  class="mono"
                />
              </div>
              <div class="config-item">
                <label class="label">DURATION (s):</label>
                <input
                  v-model.number="store.selectedJourney.volumeModel.duration"
                  type="number"
                  min="1"
                  class="mono"
                />
              </div>
            </div>
          </div>

          <!-- Datapool Configuration -->
          <div class="detail-section panel">
            <div class="section-header">
              <h3 class="section-title">DATAPOOL</h3>
              <button
                v-if="!store.selectedJourney.datapool"
                @click="showDatapoolModal = true"
                class="add-btn"
              >
                + ADD DATAPOOL
              </button>
              <button
                v-else
                @click="store.removeDatapool(store.selectedJourneyIndex)"
                class="danger"
              >
                REMOVE
              </button>
            </div>

            <div v-if="store.selectedJourney.datapool" class="datapool-config">
              <div class="config-row">
                <span class="label">TYPE:</span>
                <span class="value text-cyan mono">{{ store.selectedJourney.datapool.type }}</span>
              </div>
              <div class="config-row">
                <span class="label">SOURCE:</span>
                <span class="value text-amber mono">{{ store.selectedJourney.datapool.source }}</span>
              </div>
            </div>
            <div v-else class="empty-datapool text-muted">
              No datapool configured
            </div>
          </div>

          <!-- HTTP Requests -->
          <div class="detail-section panel">
            <div class="section-header">
              <h3 class="section-title">HTTP REQUESTS ({{ store.selectedJourney.requests.length }})</h3>
              <div class="request-actions">
                <button @click="showCurlModal = true">📋 FROM CURL</button>
                <button @click="store.addRequest()" class="add-btn">+ ADD REQUEST</button>
              </div>
            </div>

            <div class="requests-list">
              <div
                v-for="(request, reqIndex) in store.selectedJourney.requests"
                :key="reqIndex"
                class="request-card panel"
              >
                <div class="request-header">
                  <div class="request-method-url">
                    <select v-model="request.method" class="method-select mono">
                      <option value="GET">GET</option>
                      <option value="POST">POST</option>
                      <option value="PUT">PUT</option>
                      <option value="PATCH">PATCH</option>
                      <option value="DELETE">DELETE</option>
                      <option value="HEAD">HEAD</option>
                      <option value="OPTIONS">OPTIONS</option>
                    </select>
                    <input
                      v-model="request.url"
                      placeholder="https://api.example.com/endpoint"
                      class="url-input mono"
                    />
                  </div>
                  <div class="request-actions-mini">
                    <button @click="toggleRequestDetails(reqIndex)" title="Toggle details">
                      {{ expandedRequests.has(reqIndex) ? '▼' : '▶' }}
                    </button>
                    <button @click="store.moveRequest(store.selectedJourneyIndex, reqIndex, 'up')" :disabled="reqIndex === 0" title="Move up">↑</button>
                    <button @click="store.moveRequest(store.selectedJourneyIndex, reqIndex, 'down')" :disabled="reqIndex === store.selectedJourney.requests.length - 1" title="Move down">↓</button>
                    <button @click="store.deleteRequest(store.selectedJourneyIndex, reqIndex)" class="danger" title="Delete">✕</button>
                  </div>
                </div>

                <div v-if="expandedRequests.has(reqIndex)" class="request-details">
                  <!-- Headers -->
                  <div class="request-section">
                    <h4 class="subsection-title">HEADERS</h4>
                    <div class="key-value-list">
                      <div
                        v-for="(value, key, index) in request.headers"
                        :key="index"
                        class="key-value-row"
                      >
                        <input v-model.lazy="Object.keys(request.headers)[index]" placeholder="Header-Name" class="key-input mono" />
                        <input v-model="request.headers[key]" placeholder="value" class="value-input mono" />
                        <button @click="deleteHeader(request, key)" class="delete-btn">✕</button>
                      </div>
                      <button @click="addHeader(request)" class="add-kv-btn">+ ADD HEADER</button>
                    </div>
                  </div>

                  <!-- Query Params -->
                  <div class="request-section">
                    <h4 class="subsection-title">QUERY PARAMS</h4>
                    <div class="key-value-list">
                      <div
                        v-for="(value, key, index) in request.query_params"
                        :key="index"
                        class="key-value-row"
                      >
                        <input v-model.lazy="Object.keys(request.query_params)[index]" placeholder="param" class="key-input mono" />
                        <input v-model="request.query_params[key]" placeholder="value" class="value-input mono" />
                        <button @click="deleteQueryParam(request, key)" class="delete-btn">✕</button>
                      </div>
                      <button @click="addQueryParam(request)" class="add-kv-btn">+ ADD PARAM</button>
                    </div>
                  </div>

                  <!-- Body -->
                  <div class="request-section">
                    <h4 class="subsection-title">BODY</h4>
                    <textarea
                      v-model="request.body"
                      placeholder='{"key": "value"} or raw text'
                      class="body-textarea mono"
                      rows="6"
                    ></textarea>
                  </div>
                </div>
              </div>

              <div v-if="store.selectedJourney.requests.length === 0" class="empty-requests">
                <p class="text-muted">No HTTP requests configured</p>
                <button @click="store.addRequest()">ADD FIRST REQUEST</button>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="no-selection panel">
          <div class="empty-icon">⚙️</div>
          <h3>NO JOURNEY SELECTED</h3>
          <p class="text-muted">Select a journey from the sidebar or create a new one</p>
          <button @click="store.addJourney()">CREATE JOURNEY</button>
        </div>
      </div>
    </div>

    <!-- Datapool Modal -->
    <div v-if="showDatapoolModal" class="modal-overlay" @click.self="showDatapoolModal = false">
      <div class="modal-content panel">
        <div class="modal-header">
          <h3 class="modal-title">CONFIGURE DATAPOOL</h3>
          <button @click="showDatapoolModal = false" class="close-btn">✕</button>
        </div>

        <div class="modal-body">
          <div class="config-item">
            <label class="label">DATAPOOL TYPE:</label>
            <select v-model="datapoolForm.type" class="mono">
              <option value="RecyclableDatapool">RecyclableDatapool (in-memory, wraps)</option>
              <option value="IterableDatapool">IterableDatapool (in-memory)</option>
              <option value="FileDatapool">FileDatapool (file-based)</option>
              <option value="RecyclableFileDatapool">RecyclableFileDatapool (file-based, wraps)</option>
            </select>
          </div>

          <div class="config-item">
            <label class="label">SOURCE:</label>
            <div v-if="datapoolForm.type.includes('File')">
              <select v-model="datapoolForm.source" class="mono">
                <option value="">Select a datapool file...</option>
                <option v-for="dp in datapoolStore.datapools" :key="dp.name" :value="dp.name">
                  {{ dp.name }} ({{ dp.line_count }} lines)
                </option>
              </select>
              <p class="text-muted">Select from uploaded datapool files</p>
            </div>
            <div v-else>
              <textarea
                v-model="datapoolForm.source"
                placeholder="[1, 2, 3, 4, 5] or range(1, 100)"
                class="mono"
                rows="3"
              ></textarea>
              <p class="text-muted">Python expression for iterable (e.g., [1,2,3] or range(10))</p>
            </div>
          </div>
        </div>

        <div class="modal-actions">
          <button @click="applyDatapool" :disabled="!datapoolForm.source">APPLY</button>
          <button @click="showDatapoolModal = false">CANCEL</button>
        </div>
      </div>
    </div>

    <!-- Curl Import Modal -->
    <div v-if="showCurlModal" class="modal-overlay" @click.self="showCurlModal = false">
      <div class="modal-content panel">
        <div class="modal-header">
          <h3 class="modal-title">IMPORT FROM CURL</h3>
          <button @click="showCurlModal = false" class="close-btn">✕</button>
        </div>

        <div class="modal-body">
          <textarea
            v-model="curlCommand"
            placeholder="curl -X POST https://api.example.com/endpoint -H &quot;Content-Type: application/json&quot; -d &quot;{\&quot;key\&quot;:\&quot;value\&quot;}&quot;"
            class="curl-textarea mono"
            rows="8"
          ></textarea>
        </div>

        <div class="modal-actions">
          <button @click="importCurl" :disabled="!curlCommand">IMPORT</button>
          <button @click="showCurlModal = false">CANCEL</button>
        </div>
      </div>
    </div>

    <!-- Code Preview Modal -->
    <div v-if="showCodePreview" class="modal-overlay" @click.self="showCodePreview = false">
      <div class="modal-content panel code-preview-modal">
        <div class="modal-header">
          <h3 class="modal-title">PYTHON CODE PREVIEW</h3>
          <button @click="showCodePreview = false" class="close-btn">✕</button>
        </div>

        <div class="modal-body">
          <div v-if="store.isLoading" class="loading-state">
            <div class="loading-spinner">⟳</div>
            <p>Generating code...</p>
          </div>
          <div v-else>
            <pre class="code-preview mono">{{ store.generatedCode }}</pre>
          </div>
        </div>

        <div class="modal-actions">
          <button @click="copyCode" class="copy-btn">📋 COPY</button>
          <button @click="saveFromPreview" class="primary">SAVE TO FILE</button>
          <button @click="showCodePreview = false">CLOSE</button>
        </div>
      </div>
    </div>

    <!-- Status Messages -->
    <div v-if="statusMessage" :class="['status-toast', statusMessage.type]">
      {{ statusMessage.text }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useScenarioBuilderStore } from '../stores/scenarioBuilderStore'
import { useDatapoolStore } from '../stores/datapoolStore'

const store = useScenarioBuilderStore()
const datapoolStore = useDatapoolStore()

const showDatapoolModal = ref(false)
const showCurlModal = ref(false)
const showCodePreview = ref(false)
const expandedRequests = ref(new Set())
const curlCommand = ref('')
const statusMessage = ref(null)
const availableScenarios = ref([])
const selectedScenarioToLoad = ref('')

const datapoolForm = ref({
  type: 'RecyclableDatapool',
  source: ''
})

onMounted(async () => {
  // Load available datapools
  datapoolStore.fetchDatapools()

  // Load available scenarios
  await fetchAvailableScenarios()

  // Initialize with one journey if empty
  if (store.journeys.length === 0) {
    store.addJourney()
  }
})

function toggleRequestDetails(index) {
  if (expandedRequests.value.has(index)) {
    expandedRequests.value.delete(index)
  } else {
    expandedRequests.value.add(index)
  }
}

function addHeader(request) {
  const key = `Header-${Object.keys(request.headers).length + 1}`
  request.headers[key] = ''
}

function deleteHeader(request, key) {
  delete request.headers[key]
}

function addQueryParam(request) {
  const key = `param${Object.keys(request.query_params).length + 1}`
  request.query_params[key] = ''
}

function deleteQueryParam(request, key) {
  delete request.query_params[key]
}

function applyDatapool() {
  if (store.selectedJourneyIndex !== null && datapoolForm.value.source) {
    store.setDatapool(store.selectedJourneyIndex, {
      type: datapoolForm.value.type,
      source: datapoolForm.value.source
    })
    showDatapoolModal.value = false
    datapoolForm.value = { type: 'RecyclableDatapool', source: '' }
  }
}

async function importCurl() {
  try {
    await store.addRequestFromCurl(curlCommand.value)
    showStatus('Curl command imported successfully', 'success')
    curlCommand.value = ''
    showCurlModal.value = false
  } catch (error) {
    showStatus(`Import failed: ${error.message}`, 'error')
  }
}

async function showPreview() {
  try {
    await store.generatePreview()
    showCodePreview.value = true
  } catch (error) {
    showStatus(`Failed to generate preview: ${error.message}`, 'error')
  }
}

async function saveScenario() {
  try {
    const result = await store.saveScenario()
    showStatus(`Scenario saved as ${result.filename}`, 'success')
  } catch (error) {
    showStatus(`Save failed: ${error.message}`, 'error')
  }
}

async function saveFromPreview() {
  try {
    const result = await store.saveScenario()
    showStatus(`Scenario saved as ${result.filename}`, 'success')
    showCodePreview.value = false
  } catch (error) {
    showStatus(`Save failed: ${error.message}`, 'error')
  }
}

function copyCode() {
  navigator.clipboard.writeText(store.generatedCode)
  showStatus('Code copied to clipboard', 'success')
}

function resetBuilder() {
  if (confirm('Are you sure you want to reset the builder? All unsaved changes will be lost.')) {
    store.reset()
    store.addJourney()
    showStatus('Builder reset', 'success')
  }
}

function showStatus(text, type = 'success') {
  statusMessage.value = { text, type }
  setTimeout(() => {
    statusMessage.value = null
  }, 3000)
}

async function fetchAvailableScenarios() {
  try {
    const response = await fetch('/api/scenarios/available')
    const data = await response.json()
    availableScenarios.value = data.scenarios || []
  } catch (error) {
    console.error('Failed to fetch available scenarios:', error)
  }
}

async function loadExistingScenario() {
  if (!selectedScenarioToLoad.value) {
    return
  }

  try {
    await store.loadScenario(selectedScenarioToLoad.value)
    showStatus(`Loaded scenario: ${selectedScenarioToLoad.value}`, 'success')
    selectedScenarioToLoad.value = ''
  } catch (error) {
    showStatus(`Failed to load scenario: ${error.message}`, 'error')
  }
}
</script>

<style scoped>
.scenario-builder {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

/* Header */
.builder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 2px solid var(--cyan);
  background: var(--bg-surface);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.header-left h2 {
  margin: 0;
  font-size: 1.75rem;
  letter-spacing: 0.1em;
}

.scenario-meta {
  display: flex;
  gap: 1.5rem;
  align-items: center;
}

.scenario-name-input {
  padding: 0.5rem 1rem;
  background: var(--bg-secondary);
  border: 1px solid var(--cyan);
  color: var(--text-primary);
  font-size: 1rem;
  min-width: 250px;
}

.delay-input-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.delay-input {
  padding: 0.5rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  width: 80px;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

.load-scenario-select {
  padding: 0.5rem 1rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 0.875rem;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.2s ease;
}

.load-scenario-select:hover {
  border-color: var(--color-cyan);
  background: rgba(0, 255, 255, 0.05);
}

.load-scenario-select:focus {
  outline: none;
  border-color: var(--color-cyan);
  box-shadow: 0 0 0 2px rgba(0, 255, 255, 0.1);
}

/* Main Layout */
.builder-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* Journey Sidebar */
.journey-sidebar {
  width: 320px;
  border-right: 2px solid var(--border-color);
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 1rem;
  letter-spacing: 0.1em;
}

.journey-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.journey-item {
  padding: 1rem;
  margin-bottom: 0.5rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: all 0.2s ease;
}

.journey-item:hover {
  border-color: var(--cyan);
  background: rgba(0, 255, 255, 0.05);
}

.journey-item.active {
  border-color: var(--cyan);
  background: rgba(0, 255, 255, 0.1);
  border-left: 4px solid var(--cyan);
}

.journey-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.journey-name {
  font-weight: bold;
  color: var(--cyan);
}

.journey-badge {
  background: var(--amber);
  color: var(--bg-primary);
  padding: 0.125rem 0.5rem;
  font-size: 0.75rem;
  font-weight: bold;
}

.journey-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.875rem;
  margin-bottom: 0.5rem;
}

.datapool-indicator {
  font-size: 1.25rem;
}

.journey-actions {
  display: flex;
  gap: 0.25rem;
  margin-top: 0.5rem;
}

.journey-actions button {
  flex: 1;
  padding: 0.25rem;
  font-size: 0.75rem;
}

/* Detail Panel */
.journey-detail {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.detail-content {
  max-width: 1200px;
  margin: 0 auto;
}

.detail-section {
  margin-bottom: 1.5rem;
  padding: 1.5rem;
}

.section-title {
  font-size: 1.25rem;
  letter-spacing: 0.1em;
  margin: 0 0 1rem 0;
  color: var(--cyan);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.config-item label {
  font-size: 0.75rem;
  color: var(--text-muted);
  letter-spacing: 0.05em;
}

.config-item input,
.config-item select,
.config-item textarea {
  padding: 0.75rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.config-item input:focus,
.config-item select:focus,
.config-item textarea:focus {
  outline: none;
  border-color: var(--cyan);
}

.datapool-config {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.config-row {
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-color);
}

.config-row .label {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.empty-datapool {
  padding: 2rem;
  text-align: center;
}

/* HTTP Requests */
.request-actions {
  display: flex;
  gap: 0.5rem;
}

.requests-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.request-card {
  padding: 1rem;
  background: var(--bg-secondary);
}

.request-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.request-method-url {
  flex: 1;
  display: flex;
  gap: 0.5rem;
}

.method-select {
  padding: 0.5rem;
  background: var(--bg-primary);
  border: 1px solid var(--amber);
  color: var(--amber);
  font-weight: bold;
  min-width: 100px;
}

.url-input {
  flex: 1;
  padding: 0.5rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.request-actions-mini {
  display: flex;
  gap: 0.25rem;
}

.request-actions-mini button {
  padding: 0.25rem 0.5rem;
  font-size: 0.875rem;
}

.request-details {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

.request-section {
  margin-bottom: 1.5rem;
}

.subsection-title {
  font-size: 0.875rem;
  letter-spacing: 0.1em;
  margin: 0 0 0.75rem 0;
  color: var(--text-muted);
}

.key-value-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.key-value-row {
  display: grid;
  grid-template-columns: 1fr 2fr auto;
  gap: 0.5rem;
  align-items: center;
}

.key-input,
.value-input {
  padding: 0.5rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.delete-btn {
  padding: 0.5rem 0.75rem;
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
}

.add-kv-btn {
  margin-top: 0.5rem;
  padding: 0.5rem 1rem;
  background: transparent;
  border: 1px dashed var(--border-color);
  color: var(--text-muted);
}

.body-textarea {
  width: 100%;
  padding: 0.75rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-family: var(--font-mono);
  resize: vertical;
}

.empty-requests {
  text-align: center;
  padding: 3rem;
}

/* No Selection State */
.no-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 3rem;
}

.empty-icon {
  font-size: 5rem;
  margin-bottom: 1rem;
}

/* Modals */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal-content {
  max-width: 800px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  padding: 2rem;
  background: var(--bg-primary);
  border: 2px solid var(--cyan);
}

.code-preview-modal {
  max-width: 1200px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--cyan);
}

.modal-title {
  margin: 0;
  font-size: 1.5rem;
  color: var(--cyan);
}

.close-btn {
  background: transparent;
  border: none;
  font-size: 2rem;
  cursor: pointer;
  color: var(--text-muted);
  padding: 0;
  width: 40px;
  height: 40px;
}

.close-btn:hover {
  color: var(--danger);
}

.modal-body {
  margin-bottom: 1.5rem;
}

.modal-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
}

.curl-textarea {
  width: 100%;
  padding: 1rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-family: var(--font-mono);
  resize: vertical;
}

.code-preview {
  background: var(--bg-secondary);
  padding: 1.5rem;
  border-left: 4px solid var(--cyan);
  overflow-x: auto;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--text-primary);
  max-height: 60vh;
  overflow-y: auto;
}

.loading-state {
  text-align: center;
  padding: 3rem;
}

.loading-spinner {
  font-size: 3rem;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Status Toast */
.status-toast {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  padding: 1rem 2rem;
  background: var(--bg-surface);
  border: 2px solid;
  font-weight: bold;
  z-index: 2000;
  animation: slideIn 0.3s ease;
}

.status-toast.success {
  border-color: var(--success);
  color: var(--success);
}

.status-toast.error {
  border-color: var(--danger);
  color: var(--danger);
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

/* Buttons */
button {
  padding: 0.75rem 1.5rem;
  background: var(--bg-secondary);
  border: 1px solid var(--cyan);
  color: var(--cyan);
  font-family: var(--font-mono);
  font-size: 0.875rem;
  font-weight: bold;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: uppercase;
}

button:hover:not(:disabled) {
  background: var(--cyan);
  color: var(--bg-primary);
  box-shadow: 0 0 10px rgba(0, 255, 255, 0.5);
}

button:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

button.danger {
  border-color: var(--danger);
  color: var(--danger);
}

button.danger:hover:not(:disabled) {
  background: var(--danger);
  color: var(--bg-primary);
}

button.primary {
  border-color: var(--success);
  color: var(--success);
}

button.primary:hover:not(:disabled) {
  background: var(--success);
  color: var(--bg-primary);
}

button.add-btn {
  border-color: var(--amber);
  color: var(--amber);
  padding: 0.5rem 1rem;
  font-size: 0.75rem;
}

button.add-btn:hover:not(:disabled) {
  background: var(--amber);
  color: var(--bg-primary);
}

.empty-state {
  text-align: center;
  padding: 3rem 1rem;
}

/* Responsive */
@media (max-width: 1024px) {
  .journey-sidebar {
    width: 250px;
  }
}

@media (max-width: 768px) {
  .builder-layout {
    flex-direction: column;
  }

  .journey-sidebar {
    width: 100%;
    max-height: 300px;
    border-right: none;
    border-bottom: 2px solid var(--border-color);
  }

  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
