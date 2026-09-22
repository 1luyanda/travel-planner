import { describe, expect, it, vi } from 'vitest'
import {
  ACTIVITY_LIKES_LOAD_ERROR,
  ACTIVITY_LIKES_NOTE,
  ACTIVITY_LIKES_SAVE_ERROR,
  activityLikeId,
  createActivityLikesStore,
} from './activityLikes'

const colosseum = { place_id: 'ChIJA', name: 'Colosseum' }

function fakeApi(overrides = {}) {
  return {
    fetchSavedActivities: vi.fn().mockResolvedValue({ items: [] }),
    saveActivity: vi.fn().mockResolvedValue({ place_id: 'ChIJA' }),
    deleteSavedActivity: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('activityLikeId', () => {
  it('trims and stringifies', () => {
    expect(activityLikeId(' ChIJA ')).toBe('ChIJA')
    expect(activityLikeId(null)).toBe('')
  })
})

describe('activity likes store', () => {
  it('loads the authenticated user liked place ids from the backend', async () => {
    const api = fakeApi({
      fetchSavedActivities: vi.fn().mockResolvedValue({ items: [{ place_id: 'ChIJA' }] }),
    })
    const store = createActivityLikesStore({ api })
    await store.loadUser('user-a')
    expect(api.fetchSavedActivities).toHaveBeenCalledTimes(1)
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(store.getSnapshot().userId).toBe('user-a')
  })

  it('clears likes and skips fetching when logged out', async () => {
    const api = fakeApi()
    const store = createActivityLikesStore({ api })
    await store.loadUser(null)
    expect(api.fetchSavedActivities).not.toHaveBeenCalled()
    expect(store.getSnapshot().likedIds.size).toBe(0)
    expect(store.getSnapshot().userId).toBeNull()
  })

  it('surfaces a load error without throwing', async () => {
    const api = fakeApi({ fetchSavedActivities: vi.fn().mockRejectedValue(new Error('down')) })
    const store = createActivityLikesStore({ api })
    await store.loadUser('user-a')
    expect(store.getSnapshot().error).toBe(ACTIVITY_LIKES_LOAD_ERROR)
    expect(store.getSnapshot().likedIds.size).toBe(0)
  })

  it('requires auth before toggling', () => {
    const store = createActivityLikesStore({ api: fakeApi() })
    expect(store.toggle('ChIJA', { activity: colosseum, city: 'Rome' })).toEqual({ requiresAuth: true })
  })

  it('optimistically likes then confirms via saveActivity', async () => {
    const api = fakeApi()
    const store = createActivityLikesStore({ api })
    await store.loadUser('user-a')

    const result = store.toggle('ChIJA', { activity: colosseum, city: 'Rome', countryCode: 'IT', destinationId: 'dest-1' })
    expect(result.ok).toBe(true)
    expect(result.liked).toBe(true)
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(store.getSnapshot().pendingIds.has('ChIJA')).toBe(true)

    await result.settled
    expect(api.saveActivity).toHaveBeenCalledWith({
      activity: colosseum,
      city: 'Rome',
      countryCode: 'IT',
      destinationId: 'dest-1',
    })
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(store.getSnapshot().pendingIds.size).toBe(0)
  })

  it('optimistically unlikes then confirms via deleteSavedActivity', async () => {
    const api = fakeApi({ fetchSavedActivities: vi.fn().mockResolvedValue({ items: [{ place_id: 'ChIJA' }] }) })
    const store = createActivityLikesStore({ api })
    await store.loadUser('user-a')

    const result = store.toggle('ChIJA')
    expect(result.ok).toBe(true)
    expect(result.liked).toBe(false)
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(false)

    await result.settled
    expect(api.deleteSavedActivity).toHaveBeenCalledWith('ChIJA')
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(false)
  })

  it('rejects a like with no activity context', async () => {
    const store = createActivityLikesStore({ api: fakeApi() })
    await store.loadUser('user-a')
    expect(store.toggle('ChIJA')).toEqual({ ok: false, error: ACTIVITY_LIKES_SAVE_ERROR })
  })

  it('reverts the optimistic update when the backend call fails', async () => {
    const api = fakeApi({ saveActivity: vi.fn().mockRejectedValue(new Error('boom')) })
    const store = createActivityLikesStore({ api })
    await store.loadUser('user-a')

    const result = store.toggle('ChIJA', { activity: colosseum, city: 'Rome' })
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)

    await result.settled
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(false)
    expect(store.getSnapshot().error).toBe(ACTIVITY_LIKES_SAVE_ERROR)
    expect(store.getSnapshot().pendingIds.size).toBe(0)
  })

  it('ignores a nested toggle of the same id while a request is pending', async () => {
    const api = fakeApi()
    const store = createActivityLikesStore({ api })
    await store.loadUser('user-a')

    const first = store.toggle('ChIJA', { activity: colosseum, city: 'Rome' })
    const nested = store.toggle('ChIJA', { activity: colosseum, city: 'Rome' })
    expect(first.ok).toBe(true)
    expect(nested).toEqual({ ok: false, pending: true })
    await first.settled
  })

  it('does not leak likes between accounts', async () => {
    const api = fakeApi()
    const store = createActivityLikesStore({ api })
    await store.loadUser('user-a')
    const result = store.toggle('ChIJA', { activity: colosseum, city: 'Rome' })
    await result.settled
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)

    await store.loadUser('user-b')
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(false)
  })
})

describe('constants', () => {
  it('describes account-backed persistence', () => {
    expect(ACTIVITY_LIKES_NOTE).toMatch(/account/i)
  })
})
