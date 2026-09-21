/**
 * Saved-flight IDs are stored on the backend. This helper only toggles
 * local render state after an API success or while rolling back a failure.
 */

export function toggleSavedId(ids, id) {
  if (!id) return ids
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]
}
