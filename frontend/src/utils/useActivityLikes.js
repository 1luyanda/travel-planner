import { useCallback, useContext, useEffect, useSyncExternalStore } from 'react'
import { AuthContext } from '../auth/AuthProvider'
import { RouteContext, ROUTES } from './routes.jsx'
import { ACTIVITY_LIKES_NOTE, activityLikesStore } from './activityLikes'

export function followActivityLikeResult(result, navigate) {
  if (result?.requiresAuth && typeof navigate === 'function') navigate(ROUTES.login)
  return result
}

export function useActivityLikes({ store = activityLikesStore } = {}) {
  const auth = useContext(AuthContext)
  const route = useContext(RouteContext)
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot)
  const userId = auth?.user?.id || null
  const navigate = route?.navigate

  useEffect(() => {
    store.loadUser(userId)
  }, [store, userId])

  const toggleLike = useCallback(
    (placeId, context) => followActivityLikeResult(store.toggle(placeId, context), navigate),
    [navigate, store],
  )

  return {
    likedIds: snapshot.likedIds,
    pendingIds: snapshot.pendingIds,
    likeError: snapshot.error,
    persistenceNote: userId ? ACTIVITY_LIKES_NOTE : '',
    isLiked: (placeId) => snapshot.likedIds.has(placeId),
    toggleLike,
  }
}
