/**
 * Per-user activity likes. There is no activities-like API, so likes are
 * stored in localStorage as place_id strings only.
 */

export const ACTIVITY_LIKES_NOTE = 'Likes are saved on this browser only.'
export const ACTIVITY_LIKES_SAVE_ERROR = 'Could not save that like.'
export const ACTIVITY_LIKES_STORAGE_PREFIX = 'tp:activity-likes:'

function trimText(value) {
  if (value == null) return ''
  return String(value).trim()
}

export function activityLikeId(value) {
  return trimText(value)
}

export function activityLikesStorageKey(userId) {
  const id = trimText(userId)
  if (!id) return null
  return `${ACTIVITY_LIKES_STORAGE_PREFIX}${id}`
}

export function parseActivityLikeIds(raw) {
  if (raw == null || raw === '') return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(parsed)) return []
    const seen = new Set()
    const ids = []
    for (const item of parsed) {
      const id = activityLikeId(item)
      if (!id || seen.has(id)) continue
      seen.add(id)
      ids.push(id)
    }
    return ids
  } catch {
    return []
  }
}

export function getBrowserStorage() {
  try {
    const storage = globalThis.localStorage
    if (!storage) return null
    const probe = `${ACTIVITY_LIKES_STORAGE_PREFIX}probe`
    storage.setItem(probe, '1')
    storage.removeItem(probe)
    return storage
  } catch {
    return null
  }
}

export function readActivityLikes(storage, userId) {
  const key = activityLikesStorageKey(userId)
  if (!key) return []
  if (!storage) return []
  try {
    return parseActivityLikeIds(storage.getItem(key))
  } catch {
    return []
  }
}

export function writeActivityLikes(storage, userId, ids) {
  const key = activityLikesStorageKey(userId)
  if (!key) return { ok: false, error: ACTIVITY_LIKES_SAVE_ERROR }
  if (!storage) return { ok: false, error: ACTIVITY_LIKES_SAVE_ERROR }
  try {
    storage.setItem(key, JSON.stringify([...parseActivityLikeIds(ids)].sort()))
    return { ok: true }
  } catch {
    return { ok: false, error: ACTIVITY_LIKES_SAVE_ERROR }
  }
}

function emptySnapshot(userId = null) {
  return {
    userId: trimText(userId) || null,
    likedIds: new Set(),
    pendingIds: new Set(),
    error: '',
  }
}

const SERVER_SNAPSHOT = emptySnapshot()

export function createActivityLikesStore({ storage } = {}) {
  let snapshot = emptySnapshot()
  const listeners = new Set()

  function resolveStorage() {
    if (typeof storage === 'function') return storage()
    if (storage) return storage
    return getBrowserStorage()
  }

  function emit(next) {
    snapshot = {
      userId: next.userId || null,
      likedIds: new Set(next.likedIds),
      pendingIds: new Set(next.pendingIds),
      error: next.error || '',
    }
    listeners.forEach((listener) => listener())
  }

  return {
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    getSnapshot() {
      return snapshot
    },
    getServerSnapshot() {
      return SERVER_SNAPSHOT
    },
    loadUser(userId) {
      const id = trimText(userId) || null
      emit({
        ...emptySnapshot(id),
        likedIds: new Set(id ? readActivityLikes(resolveStorage(), id) : []),
      })
    },
    toggle(placeId) {
      const id = activityLikeId(placeId)
      if (!snapshot.userId) return { requiresAuth: true }
      if (!id) return { ok: false, error: ACTIVITY_LIKES_SAVE_ERROR }
      if (snapshot.pendingIds.has(id)) return { ok: false, pending: true }

      const previous = new Set(snapshot.likedIds)
      const likedIds = new Set(previous)
      const liked = !likedIds.has(id)
      if (liked) likedIds.add(id)
      else likedIds.delete(id)

      const pendingIds = new Set(snapshot.pendingIds)
      pendingIds.add(id)
      emit({
        userId: snapshot.userId,
        likedIds,
        pendingIds,
        error: '',
      })

      const written = writeActivityLikes(resolveStorage(), snapshot.userId, [...likedIds])
      pendingIds.delete(id)
      if (!written.ok) {
        emit({
          userId: snapshot.userId,
          likedIds: previous,
          pendingIds: new Set(pendingIds),
          error: written.error,
        })
        return { ok: false, error: written.error }
      }

      emit({
        userId: snapshot.userId,
        likedIds,
        pendingIds: new Set(pendingIds),
        error: '',
      })
      return { ok: true, liked }
    },
  }
}

export const activityLikesStore = createActivityLikesStore()
