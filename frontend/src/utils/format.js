export const NOT_AVAILABLE = 'Not available'

export function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

export function displayValue(value) {
  if (value == null || value === '') return NOT_AVAILABLE
  return value
}

export function formatDate(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatDuration(minutes) {
  if (minutes == null || Number.isNaN(Number(minutes))) return null
  const total = Math.round(Number(minutes))
  const hours = Math.floor(total / 60)
  const remaining = total % 60
  return `${hours}h ${remaining}m`
}

export function formatTripDays(days) {
  if (days == null || Number.isNaN(Number(days))) return null
  const total = Math.round(Number(days))
  return total === 1 ? '1 day' : `${total} days`
}

export function formatStops(stops) {
  if (stops == null) return null
  if (stops === 0) return 'Direct'
  return stops === 1 ? '1 stop' : `${stops} stops`
}

export function formatAirline(flight = {}) {
  return flight.airline_name || flight.airline_code || null
}

export function formatPrice(flight = {}) {
  if (flight.price == null) return null
  return `${flight.price} ${flight.currency || ''}`.trim()
}

export function formatTemperature(value) {
  if (value == null || Number.isNaN(Number(value))) return null
  return `${Number(value)}°C`
}

export function formatPrecipitation(value) {
  if (value == null || Number.isNaN(Number(value))) return null
  return `${Number(value)}%`
}

export function cityTone(city = '') {
  let hash = 0
  for (const character of city) {
    hash = (hash * 31 + character.charCodeAt(0)) % 360
  }
  return hash
}

/** Compact facts line from grounded fields only. */
export function tripFactsLine(destination = {}) {
  const flight = destination.flight || {}
  const weather = destination.weather || {}
  return [
    formatStops(flight.outbound_stops),
    formatDuration(flight.duration_minutes),
    formatTemperature(weather.average_max_temperature_c)
      ? `${formatTemperature(weather.average_max_temperature_c)} avg max`
      : null,
    formatPrecipitation(weather.average_precipitation_probability_percent)
      ? `${formatPrecipitation(weather.average_precipitation_probability_percent)} rain`
      : null,
  ].filter(Boolean).join(' · ')
}
