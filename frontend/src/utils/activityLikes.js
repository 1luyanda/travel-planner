/**
 * Per-user activity likes. Liking an activity snapshots it to the
 * authenticated user's `saved-activities` document in Cosmos DB via the
 * backend API; there is no local persistence.
 */

import { deleteSavedActivity, fetchSavedActivities, saveActivity } from '../services/travelApi'

export const ACTIVITY_LIKES_NOTE = 'Likes are saved to your account.'
export const ACTIVITY_LIKES_SAVE_ERROR = 'Could not save that like.'
export const ACTIVITY_LIKES_LOAD_ERROR = 'Could not load your liked activities.'

function trimText(value) {
  if (value == null) return ''
  return String(value).trim()
}

export function activityLikeId(value) {
  return trimText(value)
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

export function createActivityLikesStore({ api } = {}) {
  const backend = {
    fetchSavedActivities,
    saveActivity,
    deleteSavedActivity,
    ...api,
  }
  let snapshot = emptySnapshot()
  let loadToken = 0
  const listeners = new Set()

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
      const token = ++loadToken
      emit(emptySnapshot(id))
      if (!id) return undefined

      return backend
        .fetchSavedActivities()
        .then((data) => {
          if (token !== loadToken) return
          const ids = new Set(
            (data?.items || [])
              .map((item) => activityLikeId(item?.place_id))
              .filter(Boolean),
          )
          emit({ userId: id, likedIds: ids, pendingIds: new Set(), error: '' })
        })
        .catch(() => {
          if (token !== loadToken) return
          emit({ userId: id, likedIds: new Set(), pendingIds: new Set(), error: ACTIVITY_LIKES_LOAD_ERROR })
        })
    },
    toggle(placeId, context) {
      const id = activityLikeId(placeId)
      if (!snapshot.userId) return { requiresAuth: true }
      if (!id) return { ok: false, error: ACTIVITY_LIKES_SAVE_ERROR }
      if (snapshot.pendingIds.has(id)) return { ok: false, pending: true }

      const userId = snapshot.userId
      const wasLiked = snapshot.likedIds.has(id)
      const liked = !wasLiked
      if (liked && !context?.activity) {
        return { ok: false, error: ACTIVITY_LIKES_SAVE_ERROR }
      }

      const previousLiked = new Set(snapshot.likedIds)
      const likedIds = new Set(previousLiked)
      if (liked) likedIds.add(id)
      else likedIds.delete(id)

      const pendingIds = new Set(snapshot.pendingIds)
      pendingIds.add(id)
      emit({ userId, likedIds, pendingIds, error: '' })

      const request = liked
        ? backend.saveActivity({
            activity: context.activity,
            city: context.city,
            countryCode: context.countryCode,
            destinationId: context.destinationId,
          })
        : backend.deleteSavedActivity(id)

      const settled = request
        .then(() => {
          const nextPending = new Set(snapshot.pendingIds)
          nextPending.delete(id)
          emit({ userId, likedIds: snapshot.likedIds, pendingIds: nextPending, error: '' })
        })
        .catch(() => {
          const nextPending = new Set(snapshot.pendingIds)
          nextPending.delete(id)
          emit({ userId, likedIds: previousLiked, pendingIds: nextPending, error: ACTIVITY_LIKES_SAVE_ERROR })
        })

      return { ok: true, liked, settled }
    },
  }
}

export const activityLikesStore = createActivityLikesStore()
