/**
 * Keep trip-details selection in sync with the visible result list.
 * Lookups use destination.id only. Never invent a fallback trip.
 */

export function resolveSelectedTrip(results, selectedTrip) {
  if (!selectedTrip?.id) return null
  const list = Array.isArray(results) ? results : []
  return list.find((item) => item.id === selectedTrip.id) || null
}

export function selectionAfterPoolChange(pool, selectedTrip, selectedDestinationId) {
  const list = Array.isArray(pool) ? pool : []
  const ids = new Set(list.map((item) => item.id))
  return {
    selectedTrip: resolveSelectedTrip(list, selectedTrip),
    selectedDestinationId:
      selectedDestinationId && ids.has(selectedDestinationId) ? selectedDestinationId : null,
  }
}

export function clearTripSelection() {
  return {
    selectedTrip: null,
    selectedDestinationId: null,
    viewportMode: 'bounds',
  }
}

export function selectTripFromResult(destination) {
  if (!destination?.id) return null
  return {
    selectedTrip: destination,
    selectedDestinationId: destination.id,
    viewportMode: 'selected',
  }
}

export function tripFromMarkerId(pool, resultId) {
  if (!resultId) return null
  const list = Array.isArray(pool) ? pool : []
  return list.find((item) => item.id === resultId) || null
}
