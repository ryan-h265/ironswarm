import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useClusterStore } from './clusterStore'
import { useMetricsStore } from './metricsStore'

export const useWebSocketStore = defineStore('websocket', () => {
  // State
  const ws = ref(null)
  const isConnected = ref(false)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 10
  const reconnectDelay = 3000

  // Actions
  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    try {
      ws.value = new WebSocket(wsUrl)

      ws.value.onopen = () => {
        console.log('WebSocket connected')
        isConnected.value = true
        reconnectAttempts.value = 0
      }

      ws.value.onmessage = (event) => {
        handleMessage(JSON.parse(event.data))
      }

      ws.value.onerror = (error) => {
        console.error('WebSocket error:', error)
        isConnected.value = false
      }

      ws.value.onclose = () => {
        console.log('WebSocket closed')
        isConnected.value = false
        attemptReconnect()
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      isConnected.value = false
      attemptReconnect()
    }
  }

  function disconnect() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    isConnected.value = false
  }

  function attemptReconnect() {
    if (reconnectAttempts.value >= maxReconnectAttempts) {
      console.error('Max reconnect attempts reached')
      return
    }

    reconnectAttempts.value++
    console.log(`Reconnecting in ${reconnectDelay}ms (attempt ${reconnectAttempts.value})...`)

    setTimeout(() => {
      connect()
    }, reconnectDelay)
  }

  function handleMessage(message) {
    const clusterStore = useClusterStore()
    const metricsStore = useMetricsStore()

    switch (message.type) {
      case 'cluster_update':
        clusterStore.updateFromWebSocket(message.data)
        break

      case 'metrics_update':
        metricsStore.updateFromWebSocket(message.data)
        break

      case 'scenarios_update':
        // TODO: Handle scenarios update when we have a scenarios store
        break

      case 'pong':
        // Keep-alive response
        break

      default:
        console.warn('Unknown message type:', message.type)
    }
  }

  function sendMessage(type, data) {
    if (ws.value && isConnected.value) {
      ws.value.send(JSON.stringify({ type, data }))
    } else {
      console.error('WebSocket not connected')
    }
  }

  // Keep-alive ping
  let pingInterval
  function startPing() {
    pingInterval = setInterval(() => {
      if (isConnected.value) {
        sendMessage('ping', {})
      }
    }, 30000) // Every 30 seconds
  }

  function stopPing() {
    if (pingInterval) {
      clearInterval(pingInterval)
    }
  }

  return {
    // State
    isConnected,
    reconnectAttempts,
    // Actions
    connect,
    disconnect,
    sendMessage,
    startPing,
    stopPing,
  }
})
