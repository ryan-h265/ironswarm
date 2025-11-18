<template>
  <div class="datapool-view">
    <div class="view-header panel-bracketed">
      <h2>💾 DATAPOOLS</h2>
      <div class="header-actions">
        <button @click="refreshDatapools">REFRESH</button>
      </div>
    </div>

    <!-- Stats Summary -->
    <div class="stats-panel panel scanning">
      <div class="stats-grid">
        <div class="stat-card metric-card">
          <div class="stat-label uppercase tracking-wide">TOTAL DATAPOOLS</div>
          <div class="stat-value text-cyan">{{ datapoolStore.totalDatapools }}</div>
        </div>
        <div class="stat-card metric-card">
          <div class="stat-label uppercase tracking-wide">TOTAL LINES</div>
          <div class="stat-value text-amber">{{ datapoolStore.totalLines.toLocaleString() }}</div>
        </div>
        <div class="stat-card metric-card">
          <div class="stat-label uppercase tracking-wide">TOTAL SIZE</div>
          <div class="stat-value text-success">{{ datapoolStore.formattedTotalSize }}</div>
        </div>
      </div>
    </div>

    <!-- Upload Section -->
    <div class="section-panel panel scanning">
      <div class="section-header">
        <h3 class="section-title">UPLOAD DATAPOOL</h3>
      </div>

      <div class="upload-area">
        <input
          ref="fileInput"
          type="file"
          style="display: none"
          @change="handleFileSelect"
        />

        <div class="upload-zone" @click="$refs.fileInput.click()">
          <div class="upload-icon">📤</div>
          <p class="upload-text">CLICK TO UPLOAD DATAPOOL FILE</p>
          <p class="upload-hint text-muted">Any text-based file (.txt, .csv, .json, etc.)</p>
        </div>

        <div v-if="uploadStatus" :class="['upload-status', uploadStatus.type]">
          {{ uploadStatus.message }}
        </div>

        <div v-if="selectedFile" class="selected-file panel">
          <div class="file-info">
            <span class="file-name mono">{{ selectedFile.name }}</span>
            <span class="file-size text-muted">{{ formatBytes(selectedFile.size) }}</span>
          </div>
          <button @click="uploadFile" :disabled="datapoolStore.isLoading" class="upload-btn">
            {{ datapoolStore.isLoading ? 'UPLOADING...' : 'UPLOAD' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Datapools List -->
    <div class="section-panel panel scanning">
      <h3 class="section-title">AVAILABLE DATAPOOLS</h3>

      <div v-if="datapoolStore.error" class="error-panel panel">
        <div class="error-icon">⚠️</div>
        <div class="error-message">{{ datapoolStore.error }}</div>
        <button @click="datapoolStore.clearError">DISMISS</button>
      </div>

      <div v-if="datapoolStore.isLoading && datapoolStore.datapools.length === 0" class="loading-state panel">
        <div class="loading-spinner">⟳</div>
        <p>LOADING DATAPOOLS...</p>
      </div>

      <div v-else-if="datapoolStore.datapools.length === 0" class="empty-state panel">
        <div class="empty-icon">📁</div>
        <h3>NO DATAPOOLS UPLOADED</h3>
        <p class="text-muted">Upload a datapool file to get started</p>
      </div>

      <div v-else class="datapools-grid">
        <div
          v-for="datapool in datapoolStore.datapools"
          :key="datapool.name"
          class="datapool-card panel fade-in"
        >
          <div class="datapool-header">
            <h4 class="datapool-name mono">{{ datapool.name }}</h4>
            <span v-if="datapool.has_metadata" class="status-badge success" title="Has metadata file">
              META ✓
            </span>
          </div>

          <div class="datapool-stats">
            <div class="stat-row">
              <span class="label">LINES:</span>
              <span class="value text-cyan">{{ datapool.line_count.toLocaleString() }}</span>
            </div>
            <div class="stat-row">
              <span class="label">SIZE:</span>
              <span class="value text-amber">{{ formatBytes(datapool.size) }}</span>
            </div>
            <div class="stat-row">
              <span class="label">MODIFIED:</span>
              <span class="value text-muted mono">{{ formatDate(datapool.modified) }}</span>
            </div>
          </div>

          <div class="datapool-actions">
            <button @click="toggleInlinePreview(datapool.name)" class="view-btn">
              {{ expandedPreviews.has(datapool.name) ? '▼ HIDE' : '▶ PREVIEW' }}
            </button>
            <button @click="viewDatapool(datapool.name)" class="view-btn">
              FULL VIEW
            </button>
            <button @click="downloadDatapool(datapool.name)" class="download-btn">
              DOWNLOAD
            </button>
            <button @click="confirmDelete(datapool.name)" class="danger">
              DELETE
            </button>
          </div>

          <!-- Inline Preview -->
          <div v-if="expandedPreviews.has(datapool.name)" class="inline-preview">
            <div class="preview-title">PREVIEW (First 5 lines):</div>
            <div class="preview-lines mono">
              <div v-for="(line, idx) in getPreviewLines(datapool.name).slice(0, 5)" :key="idx" class="preview-line">
                {{ line }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Datapool Preview Modal -->
    <Modal
      :show="showPreview"
      :title="datapoolStore.selectedDatapool?.name || ''"
      @close="closePreview"
    >
      <div v-if="datapoolStore.selectedDatapool">
        <div class="preview-stats">
          <div class="stat-row">
            <span class="label">LINES:</span>
            <span class="value text-cyan">{{ datapoolStore.selectedDatapool.line_count.toLocaleString() }}</span>
          </div>
          <div class="stat-row">
            <span class="label">SIZE:</span>
            <span class="value text-amber">{{ formatBytes(datapoolStore.selectedDatapool.size) }}</span>
          </div>
          <div class="stat-row">
            <span class="label">MODIFIED:</span>
            <span class="value text-muted">{{ formatDate(datapoolStore.selectedDatapool.modified) }}</span>
          </div>
        </div>

        <div class="preview-content">
          <h4 class="preview-label">PREVIEW (FIRST 10 LINES):</h4>
          <pre class="preview-lines mono">{{ datapoolStore.selectedDatapool.preview?.join('\n') || 'No preview available' }}</pre>
        </div>
      </div>

      <template #actions>
        <button @click="downloadDatapool(datapoolStore.selectedDatapool?.name)">
          DOWNLOAD
        </button>
        <button @click="closePreview">CLOSE</button>
      </template>
    </Modal>

    <!-- Delete Confirmation Modal -->
    <Modal
      :show="showDeleteConfirm"
      title="⚠️ CONFIRM DELETE"
      title-class="text-danger"
      max-width="600px"
      @close="showDeleteConfirm = false"
    >
      <div class="confirm-modal-body">
        <p>Are you sure you want to delete this datapool?</p>
        <p class="datapool-name-confirm mono text-cyan">{{ datapoolToDelete }}</p>
        <p class="text-muted">This action cannot be undone.</p>
      </div>

      <template #actions>
        <button @click="deleteDatapool" class="danger" :disabled="datapoolStore.isLoading">
          {{ datapoolStore.isLoading ? 'DELETING...' : 'DELETE' }}
        </button>
        <button @click="showDeleteConfirm = false">CANCEL</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useDatapoolStore } from '../stores/datapoolStore'
import { formatBytes, formatDate } from '../utils/formatters'
import Modal from '../components/Modal.vue'

const datapoolStore = useDatapoolStore()

const fileInput = ref(null)
const selectedFile = ref(null)
const uploadStatus = ref(null)
const showPreview = ref(false)
const showDeleteConfirm = ref(false)
const datapoolToDelete = ref(null)
const expandedPreviews = ref(new Set())

onMounted(() => {
  datapoolStore.fetchDatapools()
})

function handleFileSelect(event) {
  const file = event.target.files[0]
  if (file) {
    selectedFile.value = file
    uploadStatus.value = null
  }
}

async function uploadFile() {
  if (!selectedFile.value) return

  try {
    uploadStatus.value = null
    await datapoolStore.uploadDatapool(selectedFile.value)
    uploadStatus.value = {
      type: 'success',
      message: `✓ Successfully uploaded ${selectedFile.value.name}`
    }
    selectedFile.value = null
    fileInput.value.value = ''
  } catch (error) {
    uploadStatus.value = {
      type: 'error',
      message: `✗ Upload failed: ${error.response?.data?.error || error.message}`
    }
  }
}

async function refreshDatapools() {
  await datapoolStore.fetchDatapools()
}

async function viewDatapool(name) {
  try {
    await datapoolStore.fetchDatapool(name)
    showPreview.value = true
  } catch (error) {
    console.error('Failed to load datapool preview:', error)
  }
}

function closePreview() {
  showPreview.value = false
  datapoolStore.selectedDatapool = null
}

async function toggleInlinePreview(datapoolName) {
  if (expandedPreviews.value.has(datapoolName)) {
    expandedPreviews.value.delete(datapoolName)
  } else {
    // Fetch preview data if not already loaded
    if (!datapoolStore.selectedDatapool || datapoolStore.selectedDatapool.name !== datapoolName) {
      try {
        await datapoolStore.fetchDatapool(datapoolName)
      } catch (error) {
        console.error('Failed to load datapool preview:', error)
        return
      }
    }
    expandedPreviews.value.add(datapoolName)
  }
}

function getPreviewLines(datapoolName) {
  if (datapoolStore.selectedDatapool && datapoolStore.selectedDatapool.name === datapoolName) {
    return datapoolStore.selectedDatapool.preview || []
  }
  return []
}

function downloadDatapool(name) {
  datapoolStore.downloadDatapool(name)
}

function confirmDelete(name) {
  datapoolToDelete.value = name
  showDeleteConfirm.value = true
}

async function deleteDatapool() {
  try {
    await datapoolStore.deleteDatapool(datapoolToDelete.value)
    showDeleteConfirm.value = false
    datapoolToDelete.value = null
  } catch (error) {
    console.error('Failed to delete datapool:', error)
  }
}
</script>

<style scoped>
.datapool-view {
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding: 1.5rem;
}

.view-header h2 {
  margin: 0;
  font-size: 2rem;
  letter-spacing: 0.1em;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

/* Stats Panel */
.stats-panel {
  margin-bottom: 2rem;
  padding: 1.5rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
}

.stat-card {
  padding: 1.5rem;
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 2rem;
  font-weight: bold;
  font-family: var(--font-mono);
}

/* Upload Section */
.section-panel {
  margin-bottom: 2rem;
  padding: 1.5rem;
}

.section-header {
  margin-bottom: 1.5rem;
}

.section-title {
  font-size: 1.25rem;
  letter-spacing: 0.1em;
  margin: 0 0 1rem 0;
  color: var(--cyan);
}

.upload-area {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.upload-zone {
  border: 2px dashed var(--cyan);
  padding: 3rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba(0, 255, 255, 0.05);
}

.upload-zone:hover {
  background: rgba(0, 255, 255, 0.1);
  border-color: var(--amber);
}

.upload-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.upload-text {
  font-size: 1.25rem;
  font-weight: bold;
  margin-bottom: 0.5rem;
}

.upload-hint {
  font-size: 0.875rem;
}

.selected-file {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--bg-secondary);
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.file-name {
  font-weight: bold;
}

.file-size {
  font-size: 0.875rem;
}

.upload-status {
  padding: 1rem;
  border-left: 4px solid;
  font-weight: bold;
}

.upload-status.success {
  border-color: var(--success);
  background: rgba(0, 255, 136, 0.1);
  color: var(--success);
}

.upload-status.error {
  border-color: var(--danger);
  background: rgba(255, 51, 102, 0.1);
  color: var(--danger);
}

/* Datapools Grid */
.datapools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.datapool-card {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  transition: all 0.3s ease;
}

.datapool-card:hover {
  border-color: var(--cyan);
  box-shadow: 0 0 20px rgba(0, 255, 255, 0.2);
}

.datapool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.datapool-name {
  margin: 0;
  font-size: 1.1rem;
  color: var(--cyan);
  word-break: break-all;
}

.datapool-stats {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
}

.stat-row .label {
  color: var(--text-muted);
  font-size: 0.75rem;
  letter-spacing: 0.05em;
}

.stat-row .value {
  font-weight: bold;
}

.datapool-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: auto;
  flex-wrap: wrap;
}

.datapool-actions button {
  flex: 1;
  min-width: 80px;
}

/* Inline Preview */
.inline-preview {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

.preview-title {
  font-size: 0.75rem;
  color: var(--text-muted);
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
  font-weight: bold;
}

.preview-lines {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  padding: 0.5rem;
  font-size: 0.875rem;
  max-height: 150px;
  overflow-y: auto;
}

.preview-line {
  padding: 0.125rem 0;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-line:nth-child(odd) {
  background: rgba(0, 255, 255, 0.02);
}

/* Empty/Loading States */
.empty-state,
.loading-state,
.error-panel {
  text-align: center;
  padding: 3rem;
}

.empty-icon,
.loading-spinner,
.error-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.loading-spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.error-panel {
  background: rgba(255, 51, 102, 0.1);
  border-left: 4px solid var(--danger);
}

.error-message {
  color: var(--danger);
  margin-bottom: 1rem;
}

/* Modal Content Styles */
.preview-stats {
  display: flex;
  gap: 2rem;
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border-left: 4px solid var(--cyan);
}

.preview-label {
  font-size: 0.875rem;
  letter-spacing: 0.1em;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

.preview-content {
  margin-top: 1.5rem;
}

.preview-lines {
  background: var(--bg-secondary);
  padding: 1rem;
  border-left: 4px solid var(--amber);
  overflow-x: auto;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--text-primary);
}

.confirm-modal-body {
  text-align: center;
}

.datapool-name-confirm {
  font-size: 1.25rem;
  margin: 1rem 0;
  padding: 0.5rem;
  background: var(--bg-secondary);
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
  opacity: 0.5;
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

button.upload-btn,
button.download-btn {
  border-color: var(--amber);
  color: var(--amber);
}

button.upload-btn:hover:not(:disabled),
button.download-btn:hover:not(:disabled) {
  background: var(--amber);
  color: var(--bg-primary);
}

button.view-btn {
  border-color: var(--success);
  color: var(--success);
}

button.view-btn:hover:not(:disabled) {
  background: var(--success);
  color: var(--bg-primary);
}

/* Animations */
.fade-in {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive */
@media (max-width: 768px) {
  .datapools-grid {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .preview-stats {
    flex-direction: column;
    gap: 0.5rem;
  }
}
</style>
