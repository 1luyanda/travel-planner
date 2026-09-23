/**
 * Nearby activity search for /explore.
 * Place ids match the planner activity cards so likes stay on one store.
 * Precise coordinates stay in memory for the current search only.
 */

import { activityLikeId } from './activityLikes'
import { preserveEditorialText } from './activities'

export const EXPLORE_RADIUS_METERS = 5000
export const EXPLORE_RESULT_LIMIT = 10
export const EXPLORE_PHOTO_HEIGHT = 400

export const EXPLORE_CATEGORIES = [
  {
    id: 'activities',
    label: 'Activities and attractions',
    types: ['tourist_attraction', 'museum', 'park', 'art_gallery', 'historical_landmark'],
  },
  { id: 'tourist_attraction', label: 'Attractions', types: ['tourist_attraction'] },
  { id: 'museum', label: 'Museums', types: ['museum'] },
  { id: 'park', label: 'Parks', types: ['park'] },
  { id: 'historical_landmark', label: 'Landmarks', types: ['historical_landmark'] },
  { id: 'art_gallery', label: 'Galleries', types: ['art_gallery'] },
]

const PHOTO_NAME = /^places\/[A-Za-z0-9_-]{1,255}\/photos\/[A-Za-z0-9_-]{1,900}$/
const HIDDEN_TYPES = new Set(['point_of_interest', 'establishment', 'premise'])

function trimText(value) {
  if (value == null) return ''
  return String(value).trim()
}

function optionalText(value) {
  const text = trimText(value)
  return text || null
}

function finiteInRange(value, min, max) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric < min || numeric > max) return null
  return numeric
}

export function isValidLatitude(value) {
  return finiteInRange(value, -90, 90) != null
}

export function isValidLongitude(value) {
  return finiteInRange(value, -180, 180) != null
}

export function coordinatePair(latitude, longitude) {
  const lat = finiteInRange(latitude, -90, 90)
  const lng = finiteInRange(longitude, -180, 180)
  if (lat == null || lng == null) return null
  return { latitude: lat, longitude: lng }
}

export function exploreSeedFromTrip(trip) {
  const city = optionalText(trip?.destination?.city)
  if (!city) return null
  const centre = coordinatePair(trip?.destination?.latitude, trip?.destination?.longitude)
  return {
    city,
    countryCode: optionalText(trip?.destination?.country_code) || '',
    centre: centre ? { source: 'trip', ...centre } : null,
  }
}

export function exploreCategory(id) {
  return EXPLORE_CATEGORIES.find((item) => item.id === id) || EXPLORE_CATEGORIES[0]
}

export function exploreHeading({ source, city }) {
  if (source === 'device') return 'Activities near your location'
  const name = optionalText(city)
  if (name) return `Activities near ${name}`
  return 'Nearby activities'
}

export function formatSearchRadius(meters) {
  const value = Number(meters)
  if (!Number.isFinite(value) || value <= 0) return null
  if (value % 1000 === 0) return `${value / 1000} km`
  return `${value} m`
}

export function nearbyActivitiesPayload({
  city,
  countryCode,
  latitude,
  longitude,
  types,
  radiusMeters = EXPLORE_RADIUS_METERS,
} = {}) {
  const centre = coordinatePair(latitude, longitude)
  const name = optionalText(city)
  if (!centre && !name) return null
  const payload = {
    radius_meters: radiusMeters,
    limit: EXPLORE_RESULT_LIMIT,
    included_types: Array.isArray(types) && types.length ? types : exploreCategory('activities').types,
  }
  if (centre) {
    payload.latitude = centre.latitude
    payload.longitude = centre.longitude
  }
  if (name && !centre) payload.city = name
  const country = optionalText(countryCode)
  if (country && !centre) payload.country_code = country
  return payload
}

export function locationErrorMessage(error) {
  if (error?.code === 1) {
    return 'Location permission was denied. Choose a city to search instead.'
  }
  if (error?.code === 3) {
    return 'Finding your location timed out. Choose a city to search instead.'
  }
  return 'Your location is unavailable. Choose a city to search instead.'
}

export function activityPhotoUrl(name) {
  if (!PHOTO_NAME.test(optionalText(name) || '')) return null
  const params = new URLSearchParams({
    name: optionalText(name),
    max_height_px: String(EXPLORE_PHOTO_HEIGHT),
  })
  return `/api/activities/photo?${params.toString()}`
}

export function formatActivityTypes(types) {
  if (!Array.isArray(types)) return []
  return types
    .map((item) => optionalText(item))
    .filter((item) => item && !HIDDEN_TYPES.has(item))
    .slice(0, 2)
    .map((item) => {
      const words = item.replaceAll('_', ' ')
      return words.charAt(0).toUpperCase() + words.slice(1)
    })
}

function toRadians(value) {
  return (value * Math.PI) / 180
}

export function straightLineKm(from, to) {
  const start = coordinatePair(from?.latitude, from?.longitude)
  const end = coordinatePair(to?.latitude, to?.longitude)
  if (!start || !end) return null
  const earthKm = 6371
  const latitudeDelta = toRadians(end.latitude - start.latitude)
  const longitudeDelta = toRadians(end.longitude - start.longitude)
  const a =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(toRadians(start.latitude)) *
      Math.cos(toRadians(end.latitude)) *
      Math.sin(longitudeDelta / 2) ** 2
  const km = earthKm * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)))
  return Number.isFinite(km) ? km : null
}

export function formatStraightLineDistance(km) {
  if (km == null || !Number.isFinite(km) || km < 0) return null
  if (km < 0.1) return 'Under 0.1 km in a straight line'
  const amount = km < 10 ? km.toFixed(1) : String(Math.round(km))
  return `About ${amount} km in a straight line`
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

function httpsUrl(value) {
  const text = optionalText(value)
  if (!text) return null
  try {
    const url = new URL(text)
    if (url.protocol !== 'https:' || url.username || url.password) return null
    return url.toString()
  } catch {
    return null
  }
}

function mapsUrl(value) {
  const text = httpsUrl(value)
  if (!text) return null
  const url = new URL(text)
  const host = url.hostname.toLowerCase()
  if (host === 'maps.google.com' || host === 'maps.app.goo.gl') return text
  if ((host === 'www.google.com' || host === 'google.com') && url.pathname.startsWith('/maps')) return text
  return null
}

function googleImageUrl(value) {
  const text = httpsUrl(value)
  if (!text) return null
  const host = new URL(text).hostname.toLowerCase()
  if (host === 'googleusercontent.com' || host.endsWith('.googleusercontent.com')) return text
  if (host === 'ggpht.com' || host.endsWith('.ggpht.com')) return text
  return null
}

function normalizePhoto(photo) {
  const name = optionalText(photo?.name)
  if (!name || !PHOTO_NAME.test(name)) return null
  const authors = Array.isArray(photo.author_attributions)
    ? photo.author_attributions
        .map((author) => {
          const displayName = optionalText(author?.display_name)
          const uri = httpsUrl(author?.uri)
          const photoUri = googleImageUrl(author?.photo_uri)
          if (!displayName && !uri && !photoUri) return null
          return { display_name: displayName, uri, photo_uri: photoUri }
        })
        .filter(Boolean)
    : []
  return {
    name,
    author_attributions: authors,
    google_maps_uri: mapsUrl(photo.google_maps_uri),
  }
}

export function normalizeNearbyActivity(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null
  const placeId = activityLikeId(item.place_id)
  const name = optionalText(item.name)
  if (!placeId || !name) return null
  const centre = coordinatePair(item.latitude, item.longitude)
  return {
    place_id: placeId,
    name,
    types: Array.isArray(item.types) ? item.types.map((type) => optionalText(type)).filter(Boolean) : [],
    address: optionalText(item.address),
    rating: optionalNumber(item.rating),
    user_ratings_total: optionalInteger(item.user_ratings_total),
    business_status: optionalText(item.business_status),
    latitude: centre?.latitude ?? null,
    longitude: centre?.longitude ?? null,
    google_maps_uri: mapsUrl(item.google_maps_uri),
    photo: normalizePhoto(item.photo),
    description: preserveEditorialText(item.description),
    description_language_code: optionalText(item.description_language_code),
  }
}

export function normalizeNearbyResponse(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null
  if (data.status !== 'ready' && data.status !== 'error') return null
  const centre = coordinatePair(data.search_center?.latitude, data.search_center?.longitude)
  const issues = Array.isArray(data.issues)
    ? data.issues.filter((item) => typeof item === 'string' && item.trim())
    : []
  return {
    status: data.status,
    city: optionalText(data.city),
    radius_meters: Number.isFinite(Number(data.radius_meters)) ? Number(data.radius_meters) : null,
    search_center: centre,
    attribution: data.attribution === 'Google Maps' ? 'Google Maps' : null,
    issues,
    activities:
      data.status === 'ready'
        ? (Array.isArray(data.activities) ? data.activities : []).map(normalizeNearbyActivity).filter(Boolean)
        : [],
  }
}

export function createExploreSearch({ fetchNearby }) {
  let generation = 0
  let controller = null

  return {
    async run(payload, onChange) {
      generation += 1
      const current = generation
      controller?.abort()
      controller = new AbortController()
      onChange({ status: 'loading' })
      try {
        const result = await fetchNearby(payload, { signal: controller.signal })
        if (current !== generation) return
        if (!result || result.status === 'error') {
          onChange({
            status: 'error',
            activities: [],
            error: result?.issues?.[0] || 'Activity data is temporarily unavailable.',
            searchCenter: null,
          })
          return
        }
        onChange({
          status: 'ready',
          activities: result.activities,
          error: '',
          issues: result.issues,
          radiusMeters: result.radius_meters,
          searchCenter: result.search_center,
          attribution: result.attribution,
        })
      } catch (error) {
        if (error?.name === 'AbortError' || current !== generation) return
        onChange({
          status: 'error',
          activities: [],
          error: error?.message || 'Activity data is temporarily unavailable.',
          searchCenter: null,
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
