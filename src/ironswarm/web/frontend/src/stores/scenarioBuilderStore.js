import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useScenarioBuilderStore = defineStore('scenarioBuilder', () => {
  // State
  const scenarioName = ref('my_scenario')
  const delay = ref(0)
  const journeys = ref([])
  const globals = ref([
    {
      name: 'base_url',
      value: 'os.getenv("MY_SCENARIO_BASE_URL", "http://127.0.0.1:8080").rstrip("/")'
    }
  ])
  const selectedJourneyIndex = ref(null)
  const generatedCode = ref('')
  const isLoading = ref(false)
  const error = ref(null)

  // Getters
  const selectedJourney = computed(() => {
    if (selectedJourneyIndex.value !== null && journeys.value[selectedJourneyIndex.value]) {
      return journeys.value[selectedJourneyIndex.value]
    }
    return null
  })

  const hasJourneys = computed(() => journeys.value.length > 0)

  const isValid = computed(() => {
    return scenarioName.value.trim() !== '' && journeys.value.length > 0
  })

  // Journey template
  function createJourney() {
    return {
      name: `journey_${journeys.value.length + 1}`,
      requests: [],
      datapool: null,
      volumeModel: {
        target: 10,
        duration: 60
      }
    }
  }

  // HTTP Request template
  function createRequest() {
    return {
      method: 'GET',
      url: '',
      headers: {},
      body: '',
      query_params: {}
    }
  }

  // Actions - Journey Management
  function addJourney() {
    const newJourney = createJourney()
    journeys.value.push(newJourney)
    selectedJourneyIndex.value = journeys.value.length - 1
  }

  function duplicateJourney(index) {
    if (index >= 0 && index < journeys.value.length) {
      const original = journeys.value[index]
      const duplicate = JSON.parse(JSON.stringify(original))
      duplicate.name = `${original.name}_copy`
      journeys.value.splice(index + 1, 0, duplicate)
      selectedJourneyIndex.value = index + 1
    }
  }

  function deleteJourney(index) {
    if (index >= 0 && index < journeys.value.length) {
      journeys.value.splice(index, 1)
      if (selectedJourneyIndex.value === index) {
        selectedJourneyIndex.value = journeys.value.length > 0 ? 0 : null
      } else if (selectedJourneyIndex.value > index) {
        selectedJourneyIndex.value--
      }
    }
  }

  function moveJourney(index, direction) {
    if (direction === 'up' && index > 0) {
      const temp = journeys.value[index]
      journeys.value[index] = journeys.value[index - 1]
      journeys.value[index - 1] = temp
      if (selectedJourneyIndex.value === index) {
        selectedJourneyIndex.value = index - 1
      }
    } else if (direction === 'down' && index < journeys.value.length - 1) {
      const temp = journeys.value[index]
      journeys.value[index] = journeys.value[index + 1]
      journeys.value[index + 1] = temp
      if (selectedJourneyIndex.value === index) {
        selectedJourneyIndex.value = index + 1
      }
    }
  }

  function selectJourney(index) {
    if (index >= 0 && index < journeys.value.length) {
      selectedJourneyIndex.value = index
    }
  }

  // Actions - Request Management
  function addRequest(journeyIndex = null) {
    const index = journeyIndex !== null ? journeyIndex : selectedJourneyIndex.value
    if (index !== null && journeys.value[index]) {
      const newRequest = createRequest()
      journeys.value[index].requests.push(newRequest)
    }
  }

  function updateRequest(journeyIndex, requestIndex, updatedRequest) {
    if (journeys.value[journeyIndex] && journeys.value[journeyIndex].requests[requestIndex]) {
      journeys.value[journeyIndex].requests[requestIndex] = updatedRequest
    }
  }

  function deleteRequest(journeyIndex, requestIndex) {
    if (journeys.value[journeyIndex] && journeys.value[journeyIndex].requests[requestIndex]) {
      journeys.value[journeyIndex].requests.splice(requestIndex, 1)
    }
  }

  function moveRequest(journeyIndex, requestIndex, direction) {
    const requests = journeys.value[journeyIndex]?.requests
    if (!requests) return

    if (direction === 'up' && requestIndex > 0) {
      const temp = requests[requestIndex]
      requests[requestIndex] = requests[requestIndex - 1]
      requests[requestIndex - 1] = temp
    } else if (direction === 'down' && requestIndex < requests.length - 1) {
      const temp = requests[requestIndex]
      requests[requestIndex] = requests[requestIndex + 1]
      requests[requestIndex + 1] = temp
    }
  }

  // Actions - Curl Parser
  async function parseCurl(curlCommand) {
    isLoading.value = true
    error.value = null
    try {
      const response = await axios.post('/api/scenario-builder/parse-curl', {
        curl_command: curlCommand
      })
      return response.data
    } catch (err) {
      console.error('Failed to parse curl command:', err)
      error.value = err.response?.data?.error || 'Failed to parse curl command'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function addRequestFromCurl(curlCommand, journeyIndex = null) {
    try {
      const parsedRequest = await parseCurl(curlCommand)
      const index = journeyIndex !== null ? journeyIndex : selectedJourneyIndex.value
      if (index !== null && journeys.value[index]) {
        journeys.value[index].requests.push(parsedRequest)
      }
    } catch (err) {
      console.error('Failed to add request from curl:', err)
      throw err
    }
  }

  // Actions - Code Generation
  async function generatePreview() {
    isLoading.value = true
    error.value = null
    try {
      const response = await axios.post('/api/scenario-builder/preview', {
        name: scenarioName.value,
        delay: delay.value,
        journeys: journeys.value,
        globals: globals.value
      })
      generatedCode.value = response.data.code
      return response.data.code
    } catch (err) {
      console.error('Failed to generate preview:', err)
      error.value = err.response?.data?.error || 'Failed to generate preview'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function saveScenario(customCode = null) {
    isLoading.value = true
    error.value = null
    try {
      const response = await axios.post('/api/scenario-builder/save', {
        name: scenarioName.value,
        delay: delay.value,
        journeys: journeys.value,
        globals: globals.value,
        custom_code: customCode
      })
      generatedCode.value = response.data.code
      return response.data
    } catch (err) {
      console.error('Failed to save scenario:', err)
      error.value = err.response?.data?.error || 'Failed to save scenario'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  // Actions - Datapool Management
  function setDatapool(journeyIndex, datapoolConfig) {
    if (journeys.value[journeyIndex]) {
      journeys.value[journeyIndex].datapool = datapoolConfig
    }
  }

  function removeDatapool(journeyIndex) {
    if (journeys.value[journeyIndex]) {
      journeys.value[journeyIndex].datapool = null
    }
  }

  // Actions - Volume Model
  function updateVolumeModel(journeyIndex, volumeModel) {
    if (journeys.value[journeyIndex]) {
      journeys.value[journeyIndex].volumeModel = volumeModel
    }
  }

  // Actions - Reset
  function reset() {
    scenarioName.value = 'my_scenario'
    delay.value = 0
    journeys.value = []
    globals.value = [
      {
        name: 'base_url',
        value: 'os.getenv("MY_SCENARIO_BASE_URL", "http://127.0.0.1:8080").rstrip("/")'
      }
    ]
    selectedJourneyIndex.value = null
    generatedCode.value = ''
    error.value = null
  }

  function clearError() {
    error.value = null
  }

  // Actions - Global Variables
  function addGlobal() {
    globals.value.push({
      name: `var_${globals.value.length + 1}`,
      value: '""'
    })
  }

  function updateGlobal(index, name, value) {
    if (globals.value[index]) {
      globals.value[index].name = name
      globals.value[index].value = value
    }
  }

  function deleteGlobal(index) {
    globals.value.splice(index, 1)
  }

  function addGlobalPreset(presetName) {
    const presets = {
      base_url: {
        name: 'base_url',
        value: 'os.getenv("MY_SCENARIO_BASE_URL", "http://127.0.0.1:8080").rstrip("/")'
      },
      api_key: {
        name: 'api_key',
        value: 'os.getenv("API_KEY", "")'
      },
      timeout: {
        name: 'timeout',
        value: '30'
      },
      max_retries: {
        name: 'max_retries',
        value: '3'
      }
    }

    if (presets[presetName]) {
      // Check if this preset already exists
      const exists = globals.value.some(g => g.name === presets[presetName].name)
      if (!exists) {
        globals.value.push(presets[presetName])
      }
    }
  }

  // Load scenario from existing file
  async function loadScenario(scenarioNameToLoad) {
    isLoading.value = true
    error.value = null
    try {
      const response = await axios.get(`/api/scenario-builder/load/${encodeURIComponent(scenarioNameToLoad)}`)
      const config = response.data

      // Populate builder state
      scenarioName.value = config.name
      delay.value = config.delay
      journeys.value = config.journeys
      globals.value = config.globals || []
      selectedJourneyIndex.value = journeys.value.length > 0 ? 0 : null
      generatedCode.value = ''

      return config
    } catch (err) {
      console.error('Failed to load scenario:', err)
      error.value = err.response?.data?.error || 'Failed to load scenario'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  return {
    // State
    scenarioName,
    delay,
    journeys,
    globals,
    selectedJourneyIndex,
    generatedCode,
    isLoading,
    error,
    // Getters
    selectedJourney,
    hasJourneys,
    isValid,
    // Journey actions
    addJourney,
    duplicateJourney,
    deleteJourney,
    moveJourney,
    selectJourney,
    // Request actions
    addRequest,
    updateRequest,
    deleteRequest,
    moveRequest,
    // Curl parser
    parseCurl,
    addRequestFromCurl,
    // Code generation
    generatePreview,
    saveScenario,
    // Datapool
    setDatapool,
    removeDatapool,
    // Volume model
    updateVolumeModel,
    // Global variables
    addGlobal,
    updateGlobal,
    deleteGlobal,
    addGlobalPreset,
    // Utility
    reset,
    clearError,
    loadScenario,
    // Templates
    createJourney,
    createRequest,
  }
})
