import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useMetricsStore = defineStore('metrics', () => {
  // State
  const currentSnapshot = ref(null)
  const uploadedSnapshot = ref(null)
  const history = ref([])
  const maxHistoryLength = 300 // 5 minutes at 1 update/second

  // Getters (handle collector format with samples arrays)
  const totalRequests = computed(() => {
    if (!currentSnapshot.value?.counters?.ironswarm_http_requests_total) return 0
    const metric = currentSnapshot.value.counters.ironswarm_http_requests_total
    if (!metric.samples || !Array.isArray(metric.samples)) return 0
    return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
  })

  const totalErrors = computed(() => {
    if (!currentSnapshot.value?.counters?.ironswarm_http_errors_total) return 0
    const metric = currentSnapshot.value.counters.ironswarm_http_errors_total
    if (!metric.samples || !Array.isArray(metric.samples)) return 0
    return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
  })

  const errorRate = computed(() => {
    const total = totalRequests.value
    const errors = totalErrors.value
    if (total === 0) return 0
    return ((errors / total) * 100).toFixed(2)
  })

  const totalJourneys = computed(() => {
    if (!currentSnapshot.value?.counters?.ironswarm_journey_executions_total) return 0
    const metric = currentSnapshot.value.counters.ironswarm_journey_executions_total
    if (!metric.samples || !Array.isArray(metric.samples)) return 0
    return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
  })

  const journeyFailures = computed(() => {
    if (!currentSnapshot.value?.counters?.ironswarm_journey_failures_total) return 0
    const metric = currentSnapshot.value.counters.ironswarm_journey_failures_total
    if (!metric.samples || !Array.isArray(metric.samples)) return 0
    return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
  })

  const latencyP50 = computed(() => {
    if (!currentSnapshot.value?.histograms?.ironswarm_http_request_duration_seconds) return 0
    return calculatePercentile(currentSnapshot.value.histograms.ironswarm_http_request_duration_seconds, 0.50)
  })

  const latencyP95 = computed(() => {
    if (!currentSnapshot.value?.histograms?.ironswarm_http_request_duration_seconds) return 0
    return calculatePercentile(currentSnapshot.value.histograms.ironswarm_http_request_duration_seconds, 0.95)
  })

  const latencyP99 = computed(() => {
    if (!currentSnapshot.value?.histograms?.ironswarm_http_request_duration_seconds) return 0
    return calculatePercentile(currentSnapshot.value.histograms.ironswarm_http_request_duration_seconds, 0.99)
  })

  const throughput = computed(() => {
    if (history.value.length < 2) return 0

    // Calculate requests per second from last 2 data points
    const recent = history.value.slice(-2)
    const timeDiff = recent[1].timestamp - recent[0].timestamp
    if (timeDiff === 0) return 0

    const reqDiff = calculateTotalFromCounter(recent[1].counters?.ironswarm_http_requests_total) -
                    calculateTotalFromCounter(recent[0].counters?.ironswarm_http_requests_total)

    return (reqDiff / timeDiff).toFixed(2)
  })

  // Helpers
  function calculateTotalFromCounter(metric) {
    if (!metric?.samples || !Array.isArray(metric.samples)) return 0
    return metric.samples.reduce((sum, sample) => sum + (sample.value || 0), 0)
  }

  function calculatePercentile(histogram, percentile) {
    // Handle collector format with samples array
    // histogram structure: { name, description, buckets: [...], samples: [{labels, sum, count, buckets: [{le, count}]}] }
    if (!histogram?.samples || !Array.isArray(histogram.samples)) return 0

    // Aggregate all samples across labels
    let totalCount = 0
    const bucketMap = new Map() // le -> cumulative count

    for (const sample of histogram.samples) {
      if (!sample.buckets || !Array.isArray(sample.buckets)) continue

      for (const bucket of sample.buckets) {
        const le = bucket.le
        const count = bucket.count || 0
        bucketMap.set(le, (bucketMap.get(le) || 0) + count)
      }

      totalCount += sample.count || 0
    }

    if (totalCount === 0) return 0

    // Convert map to sorted array
    const buckets = Array.from(bucketMap.entries())
      .sort((a, b) => {
        // Handle +Inf
        if (a[0] === '+Inf') return 1
        if (b[0] === '+Inf') return -1
        return a[0] - b[0]
      })

    const targetCount = totalCount * percentile

    for (const [le, cumulativeCount] of buckets) {
      if (cumulativeCount >= targetCount) {
        // Convert to ms (le is in seconds)
        const leValue = le === '+Inf' ? Infinity : le
        return (leValue * 1000).toFixed(2)
      }
    }

    return 0
  }

  // Actions
  async function fetchCurrentMetrics() {
    try {
      const response = await axios.get('/api/metrics/current?scope=cluster')
      currentSnapshot.value = response.data
      addToHistory(response.data)
    } catch (error) {
      console.error('Failed to fetch metrics:', error)
    }
  }

  async function fetchHistoricalMetrics(duration = 60) {
    try {
      const response = await axios.get(`/api/metrics/history?duration=${duration}`)
      // TODO: Handle historical data when backend implements it
    } catch (error) {
      console.error('Failed to fetch historical metrics:', error)
    }
  }

  async function uploadSnapshot(snapshotData) {
    try {
      await axios.post('/api/metrics/snapshot', snapshotData)
      uploadedSnapshot.value = snapshotData
    } catch (error) {
      console.error('Failed to upload snapshot:', error)
      throw error
    }
  }

  function updateFromWebSocket(data) {
    // Debug: Log the structure we're receiving
    console.log('WebSocket metrics update received:', {
      hasCounters: !!data?.counters,
      hasHistograms: !!data?.histograms,
      counterKeys: Object.keys(data?.counters || {}),
      histogramKeys: Object.keys(data?.histograms || {}),
      sampleStructure: data?.counters?.ironswarm_http_requests_total?.samples?.[0]
    })

    currentSnapshot.value = data
    addToHistory(data)
  }

  function addToHistory(snapshot) {
    history.value.push(snapshot)
    if (history.value.length > maxHistoryLength) {
      history.value = history.value.slice(-maxHistoryLength)
    }
  }

  function clearHistory() {
    history.value = []
  }

  return {
    // State
    currentSnapshot,
    uploadedSnapshot,
    history,
    // Getters
    totalRequests,
    totalErrors,
    errorRate,
    totalJourneys,
    journeyFailures,
    latencyP50,
    latencyP95,
    latencyP99,
    throughput,
    // Actions
    fetchCurrentMetrics,
    fetchHistoricalMetrics,
    uploadSnapshot,
    updateFromWebSocket,
    clearHistory,
  }
})
