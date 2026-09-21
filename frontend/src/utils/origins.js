/**
 * Origin selection against GET /api/origins.
 * `originId` is the Cosmos document id (zagreb-hr). IATA codes stay in `iata`.
 */

export const ORIGIN_REQUIRED_MESSAGE = 'Choose your departure airport to continue'

export function parseOriginItem(item) {
  if (!item || typeof item.id !== 'string' || !item.id.trim()) return null
  const cityIata = Array.isArray(item.city_iata) ? item.city_iata.filter(Boolean) : []
  const airports = Array.isArray(item.airports) ? item.airports.filter(Boolean) : []
  const iata = cityIata[0] || airports[0] || null
  return {
    originId: item.id,
    selectionId: `${item.id}-${iata || 'origin'}`,
    city: item.city || '',
    country: item.country || '',
    countryCode: item.country_code || '',
    iata,
    cityIata,
    airports,
    photoUrl: item.photo_url ?? null,
    photoUrlSmall: item.photo_url_small ?? null,
    flightCount: Number.isFinite(Number(item.flight_count)) ? Number(item.flight_count) : null,
  }
}

export function parseOriginItems(item, query = '') {
  if (!item || typeof item.id !== 'string' || !item.id.trim()) return []
  const cityIata = Array.isArray(item.city_iata) ? item.city_iata.filter(Boolean) : []
  const airports = Array.isArray(item.airports) ? item.airports.filter(Boolean) : []
  const allCodes = [...new Set([...cityIata, ...airports])]
  const needle = String(query).trim().toUpperCase()
  const codes =
    /^[A-Z]{3}$/.test(needle) && allCodes.some((code) => String(code).toUpperCase() === needle)
      ? allCodes.filter((code) => String(code).toUpperCase() === needle)
      : allCodes
  if (!codes.length) {
    const parsed = parseOriginItem(item)
    return parsed ? [parsed] : []
  }
  return codes
    .map((iata) => parseOriginItem({ ...item, city_iata: [iata], airports: [] }))
    .filter(Boolean)
}

export function formatOriginLabel(origin) {
  if (!origin) return ''
  const place = [origin.city, origin.country].filter(Boolean).join(', ')
  if (place && origin.iata) return `${place} (${origin.iata})`
  return place || origin.iata || origin.originId || ''
}

export function originSearchText(origin) {
  return [origin?.city, origin?.country, origin?.iata, origin?.originId, ...(origin?.airports || [])]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

export function isValidOriginSelection(origin) {
  return Boolean(origin?.originId) && origin.originId !== origin?.iata
}

export function requireSelectedOrigin(origin) {
  if (isValidOriginSelection(origin)) return { ok: true }
  return { ok: false, message: ORIGIN_REQUIRED_MESSAGE }
}

export function shouldClearOriginSelection(selected, inputText) {
  if (!selected) return false
  return inputText.trim() !== formatOriginLabel(selected).trim()
}
