/**
 * Build Leaflet pins from visible results.
 * Coordinates are destination airport/city WGS84 values as [latitude, longitude].
 * Origin/departure locations are never used.
 */

function readPinFields(result = {}) {
  const place = result.destination || {}
  return {
    id: result.id,
    latitude: place.latitude,
    longitude: place.longitude,
    destination_city: place.city ?? result.destination_city ?? null,
    destination_country: result.country?.common_name ?? result.destination_country ?? null,
    destination_airport: place.airport ?? result.airport_name ?? result.destination_airport ?? null,
    price_eur: result.flight?.price ?? result.price_eur ?? null,
    currency: result.flight?.currency ?? result.currency ?? null,
  }
}

export function isValidCoordinatePair(latitude, longitude) {
  if (latitude == null || longitude == null) return false
  const lat = Number(latitude)
  const lng = Number(longitude)
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false
  // 0,0 is treated as a missing placeholder, not a real destination.
  if (lat === 0 && lng === 0) return false
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return false
  return true
}

/** Leaflet expects [lat, lng]. Never swap this order. */
export function toLatLng(latitude, longitude) {
  return [Number(latitude), Number(longitude)]
}

export function formatPopupPrice(price, currency) {
  if (price == null || price === '') return null
  const symbol = currency === 'EUR' ? '€' : ''
  const code = currency ? ` ${currency}` : ''
  return `${symbol}${price}${code}`.trim()
}

export function buildMapMarkers(results = []) {
  const byKey = new Map()

  for (const result of results) {
    const pin = readPinFields(result)
    if (!isValidCoordinatePair(pin.latitude, pin.longitude)) continue

    const position = toLatLng(pin.latitude, pin.longitude)
    const dedupeKey = pin.destination_airport || `${position[0]},${position[1]}`
    const existing = byKey.get(dedupeKey)

    if (existing) {
      existing.resultIds.push(result.id)
      continue
    }

    byKey.set(dedupeKey, {
      key: dedupeKey,
      id: result.id,
      resultIds: [result.id],
      position,
      destination_city: pin.destination_city,
      destination_country: pin.destination_country,
      airport_name: pin.destination_airport,
      priceLine: formatPopupPrice(pin.price_eur, pin.currency),
    })
  }

  return [...byKey.values()]
}

export function findMarkerForSelection(markers, selectedId) {
  if (!selectedId) return null
  return markers.find((marker) => marker.resultIds.includes(selectedId)) || null
}
