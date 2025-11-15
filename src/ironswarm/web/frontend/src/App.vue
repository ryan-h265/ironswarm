<template>
  <div class="command-center">
    <!-- Top Bar -->
    <header class="top-bar">
      <div class="top-bar-left">
        <h1 class="title">
          <span class="hex-symbol">⬡</span>
          IRONSWARM COMMAND CENTER
        </h1>
      </div>

      <div class="top-bar-center">
        <div class="cluster-status">
          <span class="label">CLUSTER STATUS</span>
          <span :class="['status-badge', clusterStore.isConnected ? 'live' : 'offline']">
            <span class="pulse-dot"></span>
            {{ clusterStore.isConnected ? 'LIVE' : 'OFFLINE' }}
          </span>
          <span class="node-count">{{ clusterStore.totalNodes }} NODES</span>
        </div>
      </div>

      <div class="top-bar-right">
        <span class="timestamp mono">{{ currentTime }}</span>
      </div>
    </header>

    <!-- Main Layout -->
    <div class="main-layout">
      <!-- Side Navigation -->
      <nav class="sidebar">
        <router-link
          v-for="route in routes"
          :key="route.path"
          :to="route.path"
          class="nav-item"
          :class="{ active: $route.name === route.name }"
        >
          <span class="nav-icon">{{ route.icon }}</span>
          <span class="nav-label">{{ route.name }}</span>
        </router-link>
      </nav>

      <!-- Content Area -->
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useClusterStore } from './stores/clusterStore'
import { useMetricsStore } from './stores/metricsStore'
import { useWebSocketStore } from './stores/websocketStore'

const clusterStore = useClusterStore()
const metricsStore = useMetricsStore()
const wsStore = useWebSocketStore()

const currentTime = ref('')

const routes = [
  { path: '/', name: 'Cluster', icon: '⬢' },
  { path: '/scenarios', name: 'Scenarios', icon: '⚡' },
  { path: '/scenario-builder', name: 'Builder', icon: '⚙️' },
  { path: '/datapools', name: 'Datapools', icon: '💾' },
  { path: '/metrics', name: 'Metrics', icon: '◈' },
  { path: '/graphs', name: 'Graphs', icon: '▲' },
  { path: '/historical', name: 'Historical', icon: '◉' },
  { path: '/reports', name: 'Reports', icon: '▣' },
]

// Update time display
let timeInterval
onMounted(() => {
  updateTime()
  timeInterval = setInterval(updateTime, 1000)

  // Initialize WebSocket connection
  wsStore.connect()

  // Fetch initial data
  clusterStore.fetchClusterInfo()
  metricsStore.fetchCurrentMetrics()
})

onUnmounted(() => {
  if (timeInterval) clearInterval(timeInterval)
  wsStore.disconnect()
})

function updateTime() {
  const now = new Date()
  currentTime.value = now.toISOString().replace('T', ' ').split('.')[0] + ' UTC'
}
</script>

<style scoped>
.command-center {
  width: 100%;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ═══════════════════════════════════════════════════════════════════
   TOP BAR
   ═══════════════════════════════════════════════════════════════════ */

.top-bar {
  height: 60px;
  background: var(--color-bg-surface);
  border-bottom: 2px solid var(--color-cyan);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--spacing-lg);
  position: relative;
}

.top-bar::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg,
    transparent,
    var(--color-cyan) 20%,
    var(--color-cyan) 80%,
    transparent
  );
  animation: scan-horizontal 3s linear infinite;
}

@keyframes scan-horizontal {
  0%, 100% {
    opacity: 0.5;
  }
  50% {
    opacity: 1;
  }
}

.top-bar-left,
.top-bar-center,
.top-bar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.title {
  font-size: 18px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.hex-symbol {
  font-size: 24px;
}

.cluster-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-panel);
  border: 1px solid var(--border-color-dim);
}

.label {
  font-size: 10px;
  color: var(--color-text-muted);
  letter-spacing: 0.15em;
}

.node-count {
  font-size: 12px;
  color: var(--color-amber);
  font-weight: 600;
  padding: 2px 8px;
  border: 1px solid var(--color-amber);
  background: rgba(255, 176, 0, 0.1);
}

.timestamp {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* ═══════════════════════════════════════════════════════════════════
   MAIN LAYOUT
   ═══════════════════════════════════════════════════════════════════ */

.main-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* ═══════════════════════════════════════════════════════════════════
   SIDEBAR NAVIGATION
   ═══════════════════════════════════════════════════════════════════ */

.sidebar {
  width: 200px;
  background: var(--color-bg-surface);
  border-right: 1px solid var(--border-color-dim);
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  position: relative;
}

.sidebar::before {
  content: '';
  position: absolute;
  top: 0;
  right: -1px;
  width: 1px;
  height: 100%;
  background: linear-gradient(180deg,
    transparent,
    var(--color-cyan) 20%,
    var(--color-cyan) 80%,
    transparent
  );
  opacity: 0.5;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  color: var(--color-text-muted);
  text-decoration: none;
  border: 1px solid transparent;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  position: relative;
}

.nav-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 0;
  background: var(--color-cyan);
  transition: height 0.2s ease;
}

.nav-item:hover {
  color: var(--color-cyan);
  background: rgba(0, 255, 255, 0.05);
  border-color: var(--border-color-dim);
}

.nav-item:hover::before {
  height: 100%;
}

.nav-item.active {
  color: var(--color-cyan);
  background: rgba(0, 255, 255, 0.1);
  border-color: var(--color-cyan);
}

.nav-item.active::before {
  height: 100%;
}

.nav-icon {
  font-size: 16px;
}

/* ═══════════════════════════════════════════════════════════════════
   CONTENT AREA
   ═══════════════════════════════════════════════════════════════════ */

.content {
  flex: 1;
  overflow-y: auto;
  background: var(--color-bg-primary);
  position: relative;
}

/* Custom scrollbar */
.content::-webkit-scrollbar {
  width: 8px;
}

.content::-webkit-scrollbar-track {
  background: var(--color-bg-panel);
}

.content::-webkit-scrollbar-thumb {
  background: var(--color-cyan);
  border-radius: 0;
}

.content::-webkit-scrollbar-thumb:hover {
  background: var(--color-amber);
}
</style>
