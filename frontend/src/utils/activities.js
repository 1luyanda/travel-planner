/**
 * Destination activities helpers. Ranking stays on the backend. These
 * functions only map a selected trip onto POST /api/activities.
 */

export const ACTIVITIES_LIMIT = 8

const PRICE_LEVEL_LABELS = {
  PRICE_LEVEL_FREE: 'Free',
  PRICE_LEVEL_INEXPENSIVE: 'Inexpensive',
  PRICE_LEVEL_MODERATE: 'Moderate',
  PRICE_LEVEL_EXPENSIVE: 'Expensive',
  PRICE_LEVEL_VERY_EXPENSIVE: 'Very expensive',
}

const BUSINESS_STATUS_LABELS = {
  OPERATIONAL: 'Operational',
  CLOSED_TEMPORARILY: 'Temporarily closed',
  CLOSED_PERMANENTLY: 'Permanently closed',
}

function trimText(value) {
  if (value == null) return ''
  return String(value).trim()
}

function optionalText(value) {
  const text = trimText(value)
  return text || null
}

function optionalNumber(value) {
  if (value == null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function optionalInteger(value) {
  if (value == null || value === '') return null
  if (typeof value === 'number' && Number.isInteger(value)) return value
  if (typeof value === 'string' && /^-?\d+$/.test(value.trim())) return Number(value)
  const numeric = Number(value)
  return Number.isInteger(numeric) ? numeric : null
}

export function cleanMoods(moods) {
  if (!Array.isArray(moods)) return []
  return moods.map(trimText).filter(Boolean)
}

export function activitiesPayloadFromDestination(destination, moods) {
  const city = optionalText(destination?.destination?.city)
  if (!city) return null

  const payload = {
    city,
    moods: cleanMoods(moods),
    limit: ACTIVITIES_LIMIT,
  }

  const countryCode = optionalText(destination?.destination?.country_code)
  if (countryCode) payload.country_code = countryCode

  const destinationId = optionalText(destination?.id) || optionalText(destination?.destinationId)
  if (destinationId) payload.destination_id = destinationId

  return payload
}

export function activitiesRequestKey(payload) {
  if (!payload) return ''
  return JSON.stringify(payload)
}

export function normalizeActivityItem(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null
  const placeId = optionalText(item.place_id)
  const name = optionalText(item.name)
  if (!placeId || !name) return null

  const types = Array.isArray(item.types)
    ? item.types.map(trimText).filter(Boolean)
    : []

  return {
    place_id: placeId,
    name,
    types,
    address: optionalText(item.address),
    rating: optionalNumber(item.rating),
    user_ratings_total: optionalInteger(item.user_ratings_total),
    business_status: optionalText(item.business_status),
    price_level: optionalText(item.price_level),
    description: preserveEditorialText(item.description),
    description_language_code: optionalText(item.description_language_code),
    latitude: optionalNumber(item.latitude),
    longitude: optionalNumber(item.longitude),
  }
}

export function preserveEditorialText(value) {
  if (typeof value !== 'string' || !value.trim()) return null
  return value
}

export function normalizeActivitiesResponse(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return null
  }
  if (data.status !== 'ready' && data.status !== 'error') return null

  const issues = Array.isArray(data.issues)
    ? data.issues.filter((item) => typeof item === 'string' && item.trim())
    : []

  return {
    status: data.status,
    city: typeof data.city === 'string' ? data.city : '',
    destination_id: optionalText(data.destination_id),
    issues,
    activities:
      data.status === 'ready'
        ? (Array.isArray(data.activities) ? data.activities : [])
            .map(normalizeActivityItem)
            .filter(Boolean)
        : [],
  }
}

export function formatActivityPriceLevel(value) {
  const key = optionalText(value)
  if (!key) return null
  if (PRICE_LEVEL_LABELS[key]) return PRICE_LEVEL_LABELS[key]
  return key.replace(/^PRICE_LEVEL_/, '').replaceAll('_', ' ').toLowerCase()
}

export function formatActivityBusinessStatus(value) {
  const key = optionalText(value)
  if (!key) return null
  return BUSINESS_STATUS_LABELS[key] || key.replaceAll('_', ' ').toLowerCase()
}

export function formatActivityRating(rating, reviewCount) {
  const parts = []
  if (rating != null) parts.push(String(rating))
  if (reviewCount != null) {
    parts.push(reviewCount === 1 ? '1 review' : `${reviewCount} reviews`)
  }
  return parts.length ? parts.join(' · ') : null
}

export function activityErrorMessage(result, fallback = 'Activity data is temporarily unavailable.') {
  if (result?.issues?.length) return result.issues[0]
  return fallback
}

/**
 * Sequential loader that aborts the previous request and ignores stale
 * responses. Used by the trip-details hook and unit tests.
 */
export function createActivitiesLoader({ fetchActivities }) {
  let generation = 0
  let controller = null

  return {
    async run({ payload, enabled, onChange }) {
      generation += 1
      const current = generation
      controller?.abort()
      controller = null

      if (!enabled) {
        onChange({ status: 'idle', activities: [], error: '' })
        return
      }
      if (!payload) {
        onChange({ status: 'unavailable', activities: [], error: '' })
        return
      }

      controller = new AbortController()
      onChange({ status: 'loading', activities: [], error: '' })

      try {
        const result = await fetchActivities(payload, { signal: controller.signal })
        if (current !== generation) return
        if (!result || result.status === 'error') {
          onChange({
            status: 'error',
            activities: [],
            error: activityErrorMessage(result),
          })
          return
        }
        onChange({
          status: 'ready',
          activities: result.activities,
          error: '',
        })
      } catch (error) {
        if (error?.name === 'AbortError' || current !== generation) return
        onChange({
          status: 'error',
          activities: [],
          error: error?.message || 'Activity data is temporarily unavailable.',
        })
      }
    },
    cancel() {
      generation += 1
      controller?.abort()
      controller = null
    },
  }
}
