import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import { formatBytes, formatDate } from '../utils/formatters'

export const useDatapoolStore = defineStore('datapools', () => {
  // State
  const datapools = ref([])
  const selectedDatapool = ref(null)
  const isLoading = ref(false)
  const error = ref(null)

  // Getters
  const totalDatapools = computed(() => datapools.value.length)

  const totalLines = computed(() => {
    return datapools.value.reduce((sum, dp) => sum + (dp.line_count || 0), 0)
  })

  const totalSize = computed(() => {
    return datapools.value.reduce((sum, dp) => sum + (dp.size || 0), 0)
  })

  const formattedTotalSize = computed(() => {
    return formatBytes(totalSize.value)
  })

  // Actions
  async function fetchDatapools() {
    isLoading.value = true
    error.value = null
    try {
      const response = await axios.get('/api/datapools')
      datapools.value = response.data.datapools
    } catch (err) {
      console.error('Failed to fetch datapools:', err)
      error.value = err.response?.data?.error || 'Failed to fetch datapools'
    } finally {
      isLoading.value = false
    }
  }

  async function fetchDatapool(name) {
    isLoading.value = true
    error.value = null
    try {
      const response = await axios.get(`/api/datapools/${encodeURIComponent(name)}`)
      selectedDatapool.value = response.data
      return response.data
    } catch (err) {
      console.error('Failed to fetch datapool:', err)
      error.value = err.response?.data?.error || 'Failed to fetch datapool'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function uploadDatapool(file) {
    isLoading.value = true
    error.value = null
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await axios.post('/api/datapools/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      })

      // Refresh the list after upload
      await fetchDatapools()

      return response.data
    } catch (err) {
      console.error('Failed to upload datapool:', err)
      error.value = err.response?.data?.error || 'Failed to upload datapool'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function deleteDatapool(name) {
    isLoading.value = true
    error.value = null
    try {
      await axios.delete(`/api/datapools/${encodeURIComponent(name)}`)

      // Remove from local state
      datapools.value = datapools.value.filter(dp => dp.name !== name)

      if (selectedDatapool.value?.name === name) {
        selectedDatapool.value = null
      }
    } catch (err) {
      console.error('Failed to delete datapool:', err)
      error.value = err.response?.data?.error || 'Failed to delete datapool'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  function downloadDatapool(name) {
    // Trigger browser download
    window.location.href = `/api/datapools/${encodeURIComponent(name)}/download`
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    datapools,
    selectedDatapool,
    isLoading,
    error,
    // Getters
    totalDatapools,
    totalLines,
    totalSize,
    formattedTotalSize,
    // Actions
    fetchDatapools,
    fetchDatapool,
    uploadDatapool,
    deleteDatapool,
    downloadDatapool,
    clearError,
    // Helper functions (for use in components)
    formatBytes,
    formatDate,
  }
})
