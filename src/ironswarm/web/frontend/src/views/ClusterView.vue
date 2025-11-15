<template>
  <div class="cluster-view">
    <div class="view-header panel-bracketed">
      <h2>⬢ CLUSTER TOPOLOGY</h2>
      <div class="header-meta">
        <span class="meta-item">
          <span class="label">TOTAL NODES:</span>
          <span class="value text-cyan">{{ clusterStore.totalNodes }}</span>
        </span>
        <span class="meta-item">
          <span class="label">ACTIVE:</span>
          <span class="value text-success">{{ clusterStore.activeNodes.length }}</span>
        </span>
        <span class="meta-item">
          <span class="label">SELF:</span>
          <span class="value mono text-amber">{{ clusterStore.selfNode?.identity?.substring(0, 8) || 'N/A' }}</span>
        </span>
      </div>
    </div>

    <!-- Node Registry Table -->
    <div class="node-details panel scanning">
      <h3 class="section-title">NODE REGISTRY</h3>
      <div class="node-table">
        <div class="table-header">
          <div class="table-cell">INDEX</div>
          <div class="table-cell">IDENTITY</div>
          <div class="table-cell">HOST</div>
          <div class="table-cell">PORT</div>
          <div class="table-cell">STATUS</div>
        </div>
        <div
          v-for="node in clusterStore.nodes"
          :key="node.identity"
          :class="['table-row', { 'is-self': node.is_self }]"
        >
          <div class="table-cell text-cyan">{{ node.index }}</div>
          <div class="table-cell mono">{{ node.identity.substring(0, 16) }}...</div>
          <div class="table-cell mono text-muted">{{ node.host }}</div>
          <div class="table-cell text-amber">{{ node.port }}</div>
          <div class="table-cell">
            <span :class="['status-badge', node.is_self ? 'live' : 'offline']">
              <span class="pulse-dot"></span>
              {{ node.is_self ? 'SELF' : 'PEER' }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useClusterStore } from '../stores/clusterStore'

const clusterStore = useClusterStore()

onMounted(() => {
  clusterStore.fetchClusterInfo()
})
</script>

<style scoped>
.cluster-view {
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

.header-meta {
  display: flex;
  gap: var(--spacing-lg);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.meta-item .label {
  font-size: 10px;
  color: var(--color-text-muted);
  letter-spacing: 0.1em;
}

.meta-item .value {
  font-size: 16px;
  font-weight: 700;
}

/* ═══════════════════════════════════════════════════════════════════
   SECTION TITLE
   ═══════════════════════════════════════════════════════════════════ */

.section-title {
  font-size: 14px;
  color: var(--color-amber);
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color-dim);
  letter-spacing: 0.15em;
}

/* ═══════════════════════════════════════════════════════════════════
   NODE REGISTRY TABLE
   ═══════════════════════════════════════════════════════════════════ */

.node-details {
  background: var(--color-bg-surface);
  border: 1px solid var(--border-color-dim);
  padding: var(--spacing-lg);
  position: relative;
  overflow: hidden;
}

.node-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
}

.table-header {
  display: grid;
  grid-template-columns: 60px 1fr 200px 80px 120px;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-panel);
  border-bottom: 2px solid var(--color-cyan);
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
}

.table-row {
  display: grid;
  grid-template-columns: 60px 1fr 200px 80px 120px;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-panel);
  border: 1px solid transparent;
  transition: all 0.2s ease;
}

.table-row:hover {
  background: rgba(0, 255, 255, 0.05);
  border-color: var(--color-cyan);
  transform: translateX(4px);
}

.table-row.is-self {
  background: rgba(0, 255, 255, 0.1);
  border-color: var(--color-cyan);
  box-shadow: inset 3px 0 0 var(--color-cyan);
}

.table-cell {
  display: flex;
  align-items: center;
}
</style>
