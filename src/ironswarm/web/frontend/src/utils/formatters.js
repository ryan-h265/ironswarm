/**
 * Utility functions for formatting data throughout the application
 */

/**
 * Format bytes to human-readable size (Bytes, KB, MB, GB)
 * @param {number} bytes - The number of bytes to format
 * @returns {string} Formatted string with unit
 */
export function formatBytes(bytes) {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

/**
 * Format Unix timestamp to localized date/time string
 * @param {number} timestamp - Unix timestamp in seconds
 * @returns {string} Localized date/time string
 */
export function formatDate(timestamp) {
  return new Date(timestamp * 1000).toLocaleString()
}

/**
 * Format large numbers with K/M suffixes
 * @param {number} num - The number to format
 * @returns {string} Formatted string with suffix
 */
export function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(2) + 'K'
  return num.toString()
}
