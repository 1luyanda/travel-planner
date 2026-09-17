const STORAGE_KEY = 'travel-planner:saved-ids'

function storageKey(userId = 'anonymous') {
  return `${STORAGE_KEY}:${userId || 'anonymous'}`
}

export function loadSavedIds(userId = 'anonymous') {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey(userId)) || '[]')
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string') : []
  } catch {
    return []
  }
}

export function persistSavedIds(userId, ids) {
  localStorage.setItem(storageKey(userId), JSON.stringify(ids))
}

export function toggleSavedId(ids, id) {
  if (!id) return ids
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]
}
