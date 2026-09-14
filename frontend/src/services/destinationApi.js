/**
 * Load destination records from FastAPI.
 * In development Vite proxies `/api` to http://127.0.0.1:8000.
 * Returns only the `destinations` array used by filtering and ranking.
 */
export async function fetchDestinations() {
  const response = await fetch('/api/destinations')

  if (!response.ok) {
    throw new Error('Could not load destinations. Please try again.')
  }

  let data
  try {
    data = await response.json()
  } catch {
    throw new Error('Destination data could not be read. Please try again.')
  }

  if (!Array.isArray(data?.destinations)) {
    throw new Error('Destination data is missing or invalid.')
  }

  return data.destinations
}
