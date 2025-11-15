import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useClusterStore = defineStore('cluster', () => {
  // State
  const self = ref(null)
  const nodes = ref([])
  const isConnected = ref(false)
  const lastUpdate = ref(null)

  // Getters
  const totalNodes = computed(() => nodes.value.length)
  const selfNode = computed(() => self.value)
  const activeNodes = computed(() =>
    nodes.value.filter(n => n.is_self || Date.now() - n.last_seen * 1000 < 10000)
  )

  // Actions
  async function fetchClusterInfo() {
    try {
      const response = await axios.get('/api/cluster')
      self.value = response.data.self
      nodes.value = response.data.nodes
      isConnected.value = true
      lastUpdate.value = new Date(response.data.timestamp)
    } catch (error) {
      console.error('Failed to fetch cluster info:', error)
      isConnected.value = false
    }
  }

  function updateFromWebSocket(data) {
    if (data.self_identity) {
      self.value = {
        identity: data.self_identity,
        ...self.value,
      }
    }
    if (data.nodes) {
      nodes.value = data.nodes
    }
    if (data.total_nodes) {
      // Could update a separate counter if needed
    }
    lastUpdate.value = new Date()
    isConnected.value = true
  }

  return {
    // State
    self,
    nodes,
    isConnected,
    lastUpdate,
    // Getters
    totalNodes,
    selfNode,
    activeNodes,
    // Actions
    fetchClusterInfo,
    updateFromWebSocket,
  }
})
