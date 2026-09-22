import { useCallback, useState } from 'react'
import { hotelKey } from './hotelMarkers'

function initialState(scope) {
  return { scope, hotels: [], selectedHotelId: null, focusVersion: 0 }
}

/** Share already-fetched hotels between Trip Details and the map; never fetch. */
export function useHotelSelection(trip) {
  const scope = trip?.hotelDestinationId ? JSON.stringify([trip.id, trip.hotelDestinationId]) : null
  const [state, setState] = useState(() => initialState(scope))
  // Reset during render so a changed trip never paints stale selection/markers.
  if (state.scope !== scope) setState(initialState(scope))

  const onHotelsChange = useCallback((result) => {
    setState((current) => {
      if (!scope || current.scope !== scope) return current
      const hotels = result.status === 'ready' ? result.hotels : []
      return {
        ...current, hotels,
        selectedHotelId: hotels.some((hotel) => hotelKey(hotel) === current.selectedHotelId)
          ? current.selectedHotelId : null,
      }
    })
  }, [scope])
  const onSelectHotel = useCallback((id) => {
    setState((current) => current.scope === scope && current.hotels.some((hotel) => hotelKey(hotel) === id)
      ? { ...current, selectedHotelId: id, focusVersion: current.focusVersion + 1 } : current)
  }, [scope])
  const clearSelection = useCallback(() => {
    setState((current) => ({ ...current, selectedHotelId: null }))
  }, [])
  return { ...state, onHotelsChange, onSelectHotel, clearSelection }
}
