/**
 * Frontend client for the Cosmos-backed FastAPI routes.
 * Uses the Vite `/api` proxy. Never talks to Cosmos or travel providers directly.
 */

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

async function requestJson(path, { signal } = {}) {
  let response
  try {
    response = await fetch(path, { signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError('Could not reach stored travel data. Check that the API is running.', {
      status: 0,
    })
  }

  const body = await parseJsonBody(response)

  if (!response.ok) {
    const fallback =
      response.status === 401
        ? 'The travel API authentication configuration is invalid.'
        : response.status === 503
          ? 'Stored travel data is temporarily unavailable.'
          : response.status === 404
            ? 'That stored origin was not found.'
            : response.status === 429
              ? 'Too many requests. Please wait and try again.'
              : 'Could not load stored travel data. Please try again.'
    throw new ApiError(detailMessage(body, fallback), {
      status: response.status,
      body,
    })
  }

  if (body == null) {
    throw new ApiError('Stored travel data could not be read. Please try again.', {
      status: response.status,
    })
  }

  return body
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
