/** Browser-local lookup IDs supplement server-owned saved flights, per account. */
const PREFIX = 'travel-planner:saved-hotel-ids:v1:'

function storageKey(userId) {
  return typeof userId === 'string' && userId ? `${PREFIX}${encodeURIComponent(userId)}` : null
}

export function hotelIdOrNull(value) {
  return typeof value === 'string' && value.trim() ? value : null
}

export function readSavedHotelIds(userId) {
  const key = storageKey(userId)
  if (!key) return {}
  try {
    const data = JSON.parse(globalThis.localStorage.getItem(key))
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {}
    return Object.fromEntries(Object.entries(data).filter(([, id]) => hotelIdOrNull(id)))
  } catch {
    // Disabled storage and legacy/corrupt metadata must not break saved trips.
    return {}
  }
}

export function rememberSavedHotelId(userId, flightId, hotelId) {
  const key = storageKey(userId)
  if (!key || !flightId || !hotelIdOrNull(hotelId)) return
  try {
    globalThis.localStorage.setItem(key, JSON.stringify({ ...readSavedHotelIds(userId), [flightId]: hotelId }))
  } catch {
    // The save itself already succeeded on the server.
  }
}

export function forgetSavedHotelId(userId, flightId) {
  const key = storageKey(userId)
  if (!key) return
  try {
    const ids = readSavedHotelIds(userId)
    delete ids[flightId]
    if (Object.keys(ids).length) globalThis.localStorage.setItem(key, JSON.stringify(ids))
    else globalThis.localStorage.removeItem(key)
  } catch {
    // Storage errors must not turn a successful server deletion into a failure.
  }
}

export function restoreSavedHotelId(item, ids) {
  return {
    ...item,
    hotel_destination_id: hotelIdOrNull(item.hotel_destination_id)
      || (Object.hasOwn(ids, item.flight_id) ? ids[item.flight_id] : null),
  }
}
