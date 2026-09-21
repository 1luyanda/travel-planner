import { ApiError } from './travelApi'

async function parseBody(response) {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function messageFor(body, fallback) {
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

async function requestAuth(path, { method = 'GET', body } = {}) {
  let response
  try {
    response = await fetch(path, {
      method,
      credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Could not reach the authentication service. Check that the API is running.', {
      status: 0,
    })
  }

  if (response.status === 204) return null

  const payload = await parseBody(response)
  if (!response.ok) {
    const fallback =
      response.status === 401
        ? 'Invalid email or password.'
        : response.status === 409
          ? 'An account with that email already exists.'
          : 'Authentication failed. Please try again.'
    throw new ApiError(messageFor(payload, fallback), {
      status: response.status,
      body: payload,
    })
  }
  return payload
}

export async function registerUser({ email, password, display_name }) {
  const payload = await requestAuth('/api/auth/register', {
    method: 'POST',
    body: { email, password, display_name },
  })
  return payload?.user ?? null
}

export async function loginUser({ email, password }) {
  const payload = await requestAuth('/api/auth/login', {
    method: 'POST',
    body: { email, password },
  })
  return payload?.user ?? null
}

export async function logoutUser() {
  await requestAuth('/api/auth/logout', { method: 'POST' })
}

export async function fetchCurrentUser() {
  return requestAuth('/api/auth/me')
}
