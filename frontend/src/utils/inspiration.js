/**
 * Destination inspiration for the planner explore view.
 * Generic cards use bundled city photos. Origin cards reuse GET /api/flights.
 * Does not rank, invent fares, or call recommend/refine.
 */

import { bundledInspirationCities } from '../data/destinationImages'
import { fetchFlights } from '../services/travelApi'
import { formatDate, formatPrice } from './format'
import { buildCandidateQuery, buildFlightQuery } from './searchQuery'
import { selectTripFromResult } from './tripDetailsSelection'

export const INSPIRATION_LIMIT = 4
export const INSPIRATION_GENERIC_HEADING = 'Travel inspiration'
export const INSPIRATION_HINT_GENERIC =
  'Browse destinations, then choose a departure city to search.'
export const INSPIRATION_HINT_STORED =
  'Inspiration from stored flights. These are not confirmed matches for selected dates.'
export const INSPIRATION_HINT_DATED = 'Stored flights that match the selected dates.'

const flightCache = new Map()

function textOrNull(value) {
  if (value == null) return null
  const text = String(value).trim()
  return text ? text : null
}

function numberOrNull(value) {
  if (value == null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function titleCity(key) {
  return key.charAt(0).toUpperCase() + key.slice(1)
}

export function clearInspirationFlightCache() {
  flightCache.clear()
}

export function inspirationCacheKey(query) {
  return JSON.stringify({
    origin_id: query?.origin_id || '',
    departure_date: query?.departure_date || '',
    return_date: query?.return_date || '',
  })
}

export function inspirationFlightQuery({ origin, departureDate, returnDate } = {}) {
  if (!origin?.originId) return null
  return buildFlightQuery(
    buildCandidateQuery({
      originId: origin.originId,
      departureDate,
      returnDate,
    }),
  )
}

export function inspirationHasDateFilter(query) {
  return Boolean(query?.departure_date || query?.return_date)
}

export function inspirationHeading(origin) {
  const city = textOrNull(origin?.city)
  if (city) return `Explore from ${city}`
  return INSPIRATION_GENERIC_HEADING
}

export function inspirationHint({ origin, query } = {}) {
  if (!origin?.originId) return INSPIRATION_HINT_GENERIC
  if (inspirationHasDateFilter(query)) return INSPIRATION_HINT_DATED
  return INSPIRATION_HINT_STORED
}

export function inspirationEmptyMessage({ origin, query } = {}) {
  const city = textOrNull(origin?.city) || 'this origin'
  if (inspirationHasDateFilter(query)) {
    return `No stored flights from ${city} for the selected dates.`
  }
  return `No stored destinations from ${city} yet.`
}

export function staticInspirationDestinations() {
  return bundledInspirationCities()
    .map((key) => ({
      id: `inspiration:${key}`,
      originId: null,
      documentId: null,
      destination: { city: titleCity(key) },
      country: { common_name: null },
      flight: {},
    }))
    .slice(0, INSPIRATION_LIMIT)
}

function destinationKey(flight) {
  return (
    textOrNull(flight?.destination_iata)?.toUpperCase() ||
    textOrNull(flight?.destination_city)?.toLowerCase() ||
    textOrNull(flight?.id)
  )
}

export function adaptInspirationFlights(flights = [], { originId = null, limit = INSPIRATION_LIMIT } = {}) {
  const seen = new Set()
  const results = []
  const list = Array.isArray(flights) ? flights : []

  for (const flight of list) {
    const id = textOrNull(flight?.id)
    const city = textOrNull(flight?.destination_city)
    const key = destinationKey(flight)
    if (!id || !city || !key || seen.has(key)) continue
    seen.add(key)

    const price = numberOrNull(flight?.price_eur)
    results.push({
      id,
      destinationId: id,
      originId: textOrNull(flight?.origin_id) || textOrNull(originId),
      originIata: textOrNull(flight?.origin_iata),
      documentId: id,
      photoUrl: textOrNull(flight?.photo_url),
      photoUrlSmall: textOrNull(flight?.photo_url_small),
      destination: {
        city,
        airport: textOrNull(flight?.airport_name),
        country_code: textOrNull(flight?.destination_country_code),
        latitude: numberOrNull(flight?.latitude),
        longitude: numberOrNull(flight?.longitude),
      },
      country: {
        common_name: textOrNull(flight?.destination_country),
      },
      flight: {
        origin_iata: textOrNull(flight?.origin_iata),
        origin_airport: textOrNull(flight?.origin_airport),
        destination_iata: textOrNull(flight?.destination_iata),
        destination_airport: textOrNull(flight?.destination_airport),
        price,
        currency: textOrNull(flight?.currency),
        departure_at: textOrNull(flight?.departure_at),
        return_at: textOrNull(flight?.return_at),
        outbound_stops: numberOrNull(flight?.outbound_stops),
        return_stops: numberOrNull(flight?.return_stops),
        duration_minutes: numberOrNull(flight?.duration_minutes),
        airline_code: textOrNull(flight?.airline_code),
        airline_name: textOrNull(flight?.airline_name),
        flight_number: textOrNull(flight?.flight_number),
      },
    })
    if (results.length >= limit) break
  }

  return results
}

export function inspirationFare(destination) {
  const flight = destination?.flight || {}
  const priceText = formatPrice(flight)
  const departure = textOrNull(flight.departure_at)
  const returning = textOrNull(flight.return_at)
  if (!priceText || !flight.currency || !departure || !returning) return null
  return {
    priceText,
    departureText: formatDate(departure),
    returnText: formatDate(returning),
  }
}

export function canOpenTripDetails(destination) {
  if (!selectTripFromResult(destination)) return false
  if (String(destination.id).startsWith('inspiration:')) return false
  return Boolean(destination.documentId && destination.originId)
}

export function applyInspirationDraft({ draft, city }) {
  const place = textOrNull(city)
  const current = typeof draft === 'string' ? draft : ''
  const trimmed = current.trim()
  if (!place) {
    return { draft: current, hint: '', focusComposer: true }
  }
  if (!trimmed) {
    return { draft: `A getaway to ${place}`, hint: '', focusComposer: true }
  }
  if (trimmed.toLowerCase().includes(place.toLowerCase())) {
    return { draft: current, hint: '', focusComposer: true }
  }
  return {
    draft: current,
    hint: `Add ${place} to your request, then search.`,
    focusComposer: true,
  }
}

export async function loadInspirationFlights(
  query,
  { signal, fetchFlightsFn = fetchFlights, cache = flightCache } = {},
) {
  const key = inspirationCacheKey(query)
  if (cache.has(key)) return cache.get(key)
  const payload = await fetchFlightsFn(query, { signal })
  const destinations = adaptInspirationFlights(payload?.flights, {
    originId: payload?.origin_id || query.origin_id,
  })
  cache.set(key, destinations)
  return destinations
}

export async function runInspirationFetch({
  query,
  seq,
  isCurrent,
  signal,
  fetchFlightsFn = fetchFlights,
  cache = flightCache,
} = {}) {
  if (!query) {
    return { status: 'static', destinations: staticInspirationDestinations() }
  }
  try {
    const destinations = await loadInspirationFlights(query, { signal, fetchFlightsFn, cache })
    if (!isCurrent(seq)) return { status: 'stale' }
    return { status: 'ready', destinations }
  } catch (error) {
    if (error?.name === 'AbortError') return { status: 'aborted' }
    if (!isCurrent(seq)) return { status: 'stale' }
    return {
      status: 'error',
      destinations: [],
      message: error?.message || 'Could not load destinations.',
    }
  }
}
