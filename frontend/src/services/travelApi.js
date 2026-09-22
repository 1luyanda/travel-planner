/**
 * Frontend client for the Cosmos-backed FastAPI routes.
 * Uses the Vite `/api` proxy. Never talks to Cosmos or travel providers directly.
 */

import { ACTIVITIES_LIMIT, normalizeActivitiesResponse } from '../utils/activities'
import { normalizeHotelsResponse } from '../utils/hotels'
import {
  forgetSavedHotelId, hotelIdOrNull, readSavedHotelIds, rememberSavedHotelId, restoreSavedHotelId,
} from '../utils/savedHotelMetadata'

export class ApiError extends Error {
  constructor(message, { status = 0, body = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

const ORIGIN_Q_MAX = 100

function isBlank(value) {
  return value == null || value === '' || (typeof value === 'string' && !value.trim())
}

export function appendQuery(path, params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (isBlank(value)) continue
    search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

async function parseJsonBody(response) {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function detailMessage(body, fallback) {
  const detail = body?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item) => (typeof item === 'string' ? item : item?.msg))
      .filter(Boolean)
      .join(' ')
  }
  return fallback
}

const RECOMMEND_STATUSES = new Set(['ready', 'needs_input', 'error'])

async function requestJson(path, { signal, method = 'GET', body } = {}) {
  const options = { method, signal, credentials: 'include' }
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json', Accept: 'application/json' }
    options.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(path, options)
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError('Could not reach stored travel data. Check that the API is running.', {
      status: 0,
    })
  }

  const payload = response.status === 204 ? null : await parseJsonBody(response)

  if (!response.ok) {
    const fallback =
      response.status === 401
        ? 'The travel API authentication configuration is invalid.'
        : response.status === 503
          ? 'Stored travel data is temporarily unavailable.'
          : response.status === 404
            ? 'That stored origin was not found.'
            : response.status === 422
              ? 'The planner could not read that request. Please check the details and try again.'
              : response.status === 429
                ? 'Too many requests. Please wait and try again.'
                : 'Could not load stored travel data. Please try again.'
    throw new ApiError(detailMessage(payload, fallback), {
      status: response.status,
      body: payload,
    })
  }

  if (payload == null && response.status !== 204) {
    throw new ApiError('Stored travel data could not be read. Please try again.', {
      status: response.status,
    })
  }

  return payload
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null
}

function asList(value) {
  return Array.isArray(value) ? value : []
}

function normalizeRecommendationResponse(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new ApiError('The planner returned an unexpected response.')
  }
  if (!RECOMMEND_STATUSES.has(data.status)) {
    throw new ApiError('The planner returned an unexpected response.')
  }
  return {
    status: data.status,
    request: asObject(data.request),
    updated_request: asObject(data.updated_request),
    preferences: asObject(data.preferences),
    ranking_preferences: asObject(data.ranking_preferences),
    flexible_date_fallback_used: data.flexible_date_fallback_used === true,
    exact_match_count: Number.isInteger(data.exact_match_count) ? data.exact_match_count : null,
    fallback_count: Number.isInteger(data.fallback_count) ? data.fallback_count : null,
    origin: asObject(data.origin),
    origin_id: typeof data.origin_id === 'string' ? data.origin_id : null,
    recommendations: asList(data.recommendations),
    flights: asList(data.flights),
    rejected: asList(data.rejected),
    intents: asList(data.intents),
    changes: asList(data.changes),
    issues: asList(data.issues).filter((item) => typeof item === 'string' && item.trim()),
    clarification_questions: asList(data.clarification_questions).filter(
      (item) => typeof item === 'string' && item.trim(),
    ),
    data_source: typeof data.data_source === 'string' ? data.data_source : null,
    ranking_preferences: asObject(data.ranking_preferences),
  }
}

export async function recommendTrip(payload = {}, { signal } = {}) {
  const body = {
    text: typeof payload.text === 'string' ? payload.text : '',
  }
  if (payload.form_fields && typeof payload.form_fields === 'object' && !Array.isArray(payload.form_fields)) {
    body.form_fields = payload.form_fields
  }
  if (
    payload.ranking_preferences &&
    typeof payload.ranking_preferences === 'object' &&
    !Array.isArray(payload.ranking_preferences)
  ) {
    body.ranking_preferences = payload.ranking_preferences
  }
  if (payload.preserve_ranking_preferences === true && body.ranking_preferences) {
    body.preserve_ranking_preferences = true
  }
  const data = await requestJson('/api/recommend', { method: 'POST', body, signal })
  return normalizeRecommendationResponse(data)
}

export async function refineTrip(payload = {}, { signal } = {}) {
  const text = typeof payload.text === 'string' ? payload.text.trim() : ''
  if (!text) {
    throw new ApiError('Feedback text is required to refine this trip.')
  }
  const request = asObject(payload.request)
  if (!request) {
    throw new ApiError('A saved trip request is required to refine results.')
  }
  const body = { text, request }
  if (
    payload.ranking_preferences &&
    typeof payload.ranking_preferences === 'object' &&
    !Array.isArray(payload.ranking_preferences)
  ) {
    body.ranking_preferences = payload.ranking_preferences
  }
  const data = await requestJson('/api/refine', { method: 'POST', body, signal })
  return normalizeRecommendationResponse(data)
}

export async function searchOrigins(query, { country, signal } = {}) {
  const q = typeof query === 'string' ? query.trim() : ''
  if (!q) {
    throw new ApiError('Type at least one character to search origins.')
  }
  const path = appendQuery('/api/origins', {
    q: q.slice(0, ORIGIN_Q_MAX),
    country,
  })
  const data = await requestJson(path, { signal })
  if (!Array.isArray(data)) {
    throw new ApiError('Origin search returned an unexpected response.')
  }
  return data
}

export async function fetchOrigin(originId, { signal } = {}) {
  const id = typeof originId === 'string' ? originId.trim() : ''
  if (!id) {
    throw new ApiError('origin_id is required.')
  }
  const data = await requestJson(`/api/origins/${encodeURIComponent(id)}`, { signal })
  if (!data || typeof data !== 'object' || typeof data.id !== 'string') {
    throw new ApiError('Origin details returned an unexpected response.')
  }
  return data
}

export async function fetchCandidates(params, { signal } = {}) {
  const path = appendQuery('/api/candidates', params)
  const data = await requestJson(path, { signal })
  if (
    !data ||
    typeof data !== 'object' ||
    typeof data.origin_id !== 'string' ||
    !Array.isArray(data.candidates)
  ) {
    throw new ApiError('Candidate search returned an unexpected response.')
  }
  return {
    origin_id: data.origin_id,
    candidates: data.candidates,
    rejected: Array.isArray(data.rejected) ? data.rejected : [],
    data_source: typeof data.data_source === 'string' ? data.data_source : null,
  }
}

export async function fetchSavedFlights({ signal, userId } = {}) {
  const data = await requestJson('/api/saved-flights', { signal })
  if (!data || typeof data !== 'object' || !Array.isArray(data.items)) {
    throw new ApiError('Saved flights returned an unexpected response.')
  }
  const hotelIds = readSavedHotelIds(userId)
  return {
    items: data.items.filter((item) => item && typeof item === 'object')
      .map((item) => restoreSavedHotelId(item, hotelIds)),
  }
}

export async function saveFlight(flight, { signal, userId } = {}) {
  const flightId = typeof flight?.flight_id === 'string' ? flight.flight_id.trim() : ''
  if (!flightId) {
    throw new ApiError('A flight id is required to save this trip.')
  }
  const body = { flight_id: flightId }
  const data = await requestJson('/api/saved-flights', { method: 'POST', body, signal })
  if (!data || typeof data !== 'object' || typeof data.flight_id !== 'string') {
    throw new ApiError('Saving that flight returned an unexpected response.')
  }
  const hotelId = hotelIdOrNull(flight.hotelDestinationId)
  rememberSavedHotelId(userId, data.flight_id, hotelId)
  // Keep the immediate saved view usable even when browser storage is disabled.
  return restoreSavedHotelId(data, {
    ...readSavedHotelIds(userId),
    ...(hotelId ? { [data.flight_id]: hotelId } : {}),
  })
}

export async function deleteSavedFlight(flightId, { signal, userId } = {}) {
  const id = typeof flightId === 'string' ? flightId.trim() : ''
  if (!id) {
    throw new ApiError('flight_id is required.')
  }
  await requestJson(`/api/saved-flights/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    signal,
  })
  forgetSavedHotelId(userId, id)
}

export async function fetchFlights(params, { signal } = {}) {
  const path = appendQuery('/api/flights', params)
  const data = await requestJson(path, { signal })
  if (
    !data ||
    typeof data !== 'object' ||
    typeof data.origin_id !== 'string' ||
    !Array.isArray(data.flights)
  ) {
    throw new ApiError('Flight lookup returned an unexpected response.')
  }
  return {
    origin_id: data.origin_id,
    flights: data.flights,
    count: Number.isFinite(Number(data.count)) ? Number(data.count) : data.flights.length,
    data_source: typeof data.data_source === 'string' ? data.data_source : null,
  }
}

export async function fetchHotels(destinationId, { signal } = {}) {
  if (typeof destinationId !== 'string' || !destinationId.trim()) {
    throw new ApiError('A hotel destination id is required to load hotels.')
  }
  const data = await requestJson(appendQuery('/api/hotels', {
    destination_id: destinationId,
    limit: 5,
  }), { signal })
  const normalized = normalizeHotelsResponse(data)
  if (!normalized || normalized.destination_id !== destinationId) {
    throw new ApiError('Hotel data returned an unexpected response.')
  }
  return normalized
}

export async function fetchActivities(payload, { signal } = {}) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new ApiError('A destination city is required to load activities.')
  }
  const city = typeof payload.city === 'string' ? payload.city.trim() : ''
  if (!city) {
    throw new ApiError('A destination city is required to load activities.')
  }

  const body = {
    city,
    moods: Array.isArray(payload.moods) ? payload.moods : [],
    limit: Number.isInteger(payload.limit) ? payload.limit : ACTIVITIES_LIMIT,
  }
  if (typeof payload.country_code === 'string' && payload.country_code.trim()) {
    body.country_code = payload.country_code.trim()
  }
  if (typeof payload.destination_id === 'string' && payload.destination_id.trim()) {
    body.destination_id = payload.destination_id.trim()
  }

  const data = await requestJson('/api/activities', { method: 'POST', body, signal })
  const normalized = normalizeActivitiesResponse(data)
  if (!normalized) {
    throw new ApiError('Activity data returned an unexpected response.')
  }
  return normalized
}

export async function fetchSavedActivities({ signal } = {}) {
  const data = await requestJson('/api/saved-activities', { signal })
  if (!data || typeof data !== 'object' || !Array.isArray(data.items)) {
    throw new ApiError('Saved activities returned an unexpected response.')
  }
  return {
    items: data.items.filter((item) => item && typeof item === 'object'),
  }
}

// There is no activities container to re-read later, so the full activity
// item plus its destination context is sent and stored as a snapshot at
// like time.
export async function saveActivity(
  { activity, city, countryCode, destinationId },
  { signal } = {},
) {
  const placeId = typeof activity?.place_id === 'string' ? activity.place_id.trim() : ''
  if (!placeId) {
    throw new ApiError('An activity place_id is required to save it.')
  }
  const cleanCity = typeof city === 'string' ? city.trim() : ''
  if (!cleanCity) {
    throw new ApiError('A destination city is required to save an activity.')
  }
  const body = { activity, city: cleanCity }
  if (typeof countryCode === 'string' && countryCode.trim()) {
    body.country_code = countryCode.trim()
  }
  if (typeof destinationId === 'string' && destinationId.trim()) {
    body.destination_id = destinationId.trim()
  }
  const data = await requestJson('/api/saved-activities', { method: 'POST', body, signal })
  if (!data || typeof data !== 'object' || typeof data.place_id !== 'string') {
    throw new ApiError('Saving that activity returned an unexpected response.')
  }
  return data
}

export async function deleteSavedActivity(placeId, { signal } = {}) {
  const id = typeof placeId === 'string' ? placeId.trim() : ''
  if (!id) {
    throw new ApiError('place_id is required.')
  }
  await requestJson(`/api/saved-activities/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    signal,
  })
}
