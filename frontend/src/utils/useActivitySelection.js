import { useCallback, useState } from 'react'

function initialState(scope) {
  return { scope, activities: [], selectedActivityId: null, focusVersion: 0 }
}

/** Share already-fetched activities between Trip Details and the map; never fetch. */
export function useActivitySelection(trip) {
  const scope = trip?.id ?? null
  const [state, setState] = useState(() => initialState(scope))
  // Reset during render so a changed trip never paints stale selection/markers.
  if (state.scope !== scope) setState(initialState(scope))

  const onActivitiesChange = useCallback((result) => {
    setState((current) => {
      if (!scope || current.scope !== scope) return current
      const activities = result.status === 'ready' ? result.activities : []
      return {
        ...current, activities,
        selectedActivityId: activities.some((item) => item.place_id === current.selectedActivityId)
          ? current.selectedActivityId : null,
      }
    })
  }, [scope])
  const onSelectActivity = useCallback((id) => {
    setState((current) => current.scope === scope && current.activities.some((item) => item.place_id === id)
      ? { ...current, selectedActivityId: id, focusVersion: current.focusVersion + 1 } : current)
  }, [scope])
  const clearSelection = useCallback(() => {
    setState((current) => ({ ...current, selectedActivityId: null }))
  }, [])
  return { ...state, onActivitiesChange, onSelectActivity, clearSelection }
}
