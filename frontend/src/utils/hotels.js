/** Display-only hotel data. The backend owns identifiers and ordering. */

export function officialWebsite(value) {
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null
  } catch {
    return null
  }
}

export function normalizeHotelsResponse(data) {
  if (!data || typeof data.destination_id !== 'string' || !Array.isArray(data.hotels)) return null
  // Keep only display fields, in precisely the order supplied by the backend.
  const hotels = data.hotels.map((item) => ({
    name: item?.name,
    osm_id: item?.osm_id ?? null,
    latitude: Number.isFinite(item?.latitude) ? item.latitude : null,
    longitude: Number.isFinite(item?.longitude) ? item.longitude : null,
    distance_km: item?.distance_km,
    stars: Number.isInteger(item?.stars) && item.stars > 0 ? item.stars : null,
    website: officialWebsite(item?.website),
  }))
  if (hotels.some((item) => typeof item.name !== 'string'
    || !Number.isFinite(item.distance_km) || item.distance_km < 0)) return null
  return {
    destination_id: data.destination_id,
    attribution: typeof data.attribution === 'string' ? data.attribution : null,
    hotels,
  }
}

export function formatHotelDistance(distance) {
  return Number.isFinite(distance) && distance >= 0 ? `${distance.toFixed(2)} km` : null
}

/** Selected-details loader: cancel old work and ignore late responses. */
export function createHotelsLoader({ fetchHotels }) {
  let generation = 0
  let controller = null
  return {
    async run({ destinationId, onChange }) {
      const current = ++generation
      controller?.abort()
      controller = null
      if (typeof destinationId !== 'string' || !destinationId.trim()) {
        onChange({ status: 'unavailable', hotels: [], attribution: null })
        return
      }
      controller = new AbortController()
      onChange({ status: 'loading', hotels: [], attribution: null })
      try {
        const result = await fetchHotels(destinationId, { signal: controller.signal })
        if (current !== generation) return
        onChange({ status: 'ready', hotels: result.hotels, attribution: result.attribution })
      } catch (error) {
        if (current !== generation || error?.name === 'AbortError') return
        onChange({ status: 'error', hotels: [], attribution: null })
      }
    },
    cancel() {
      generation += 1
      controller?.abort()
      controller = null
    },
  }
}
