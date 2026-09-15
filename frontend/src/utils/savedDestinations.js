const STORAGE_KEY = 'travel-planner:saved-ids'

export function loadSavedIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : []
  } catch {
    return []
  }
}

export function persistSavedIds(ids) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
}

export function toggleSavedId(ids, id) {
  if (!id) return ids
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]
}
