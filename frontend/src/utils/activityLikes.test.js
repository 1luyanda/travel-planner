import { describe, expect, it } from 'vitest'
import {
  ACTIVITY_LIKES_NOTE,
  ACTIVITY_LIKES_SAVE_ERROR,
  activityLikesStorageKey,
  createActivityLikesStore,
  parseActivityLikeIds,
  readActivityLikes,
  writeActivityLikes,
} from './activityLikes'

function memoryStorage(initial = {}) {
  const data = { ...initial }
  return {
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null
    },
    setItem(key, value) {
      data[key] = String(value)
    },
    removeItem(key) {
      delete data[key]
    },
    data,
  }
}

describe('activity like ids', () => {
  it('parses only stable place ids and ignores malformed JSON', () => {
    expect(parseActivityLikeIds('["ChIJA","ChIJA"," "]')).toEqual(['ChIJA'])
    expect(parseActivityLikeIds('{not json')).toEqual([])
    expect(parseActivityLikeIds('{"place_id":"ChIJA"}')).toEqual([])
    expect(parseActivityLikeIds(null)).toEqual([])
    expect(activityLikesStorageKey(' user-1 ')).toBe('tp:activity-likes:user-1')
    expect(activityLikesStorageKey('')).toBeNull()
  })

  it('treats invalid stored JSON as no likes', () => {
    const storage = memoryStorage({ 'tp:activity-likes:user-a': '{bad' })
    const store = createActivityLikesStore({ storage })
    store.loadUser('user-a')
    expect(store.getSnapshot().likedIds.size).toBe(0)
  })
})

describe('activity like persistence', () => {
  it('stores only ids for that user and survives a reload', () => {
    const storage = memoryStorage()
    const store = createActivityLikesStore({ storage })
    store.loadUser('user-a')
    expect(store.toggle('ChIJA')).toEqual({ ok: true, liked: true })
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(storage.getItem('tp:activity-likes:user-a')).toBe('["ChIJA"]')
    expect(JSON.parse(storage.getItem('tp:activity-likes:user-a'))).not.toContain('token')

    const reloaded = createActivityLikesStore({ storage })
    reloaded.loadUser('user-a')
    expect(reloaded.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(reloaded.toggle('ChIJA')).toEqual({ ok: true, liked: false })
    expect(reloaded.getSnapshot().likedIds.has('ChIJA')).toBe(false)
  })

  it('does not share likes across accounts and clears memory on logout', () => {
    const storage = memoryStorage()
    const store = createActivityLikesStore({ storage })
    store.loadUser('user-a')
    store.toggle('ChIJA')
    store.loadUser('user-b')
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(false)
    store.toggle('park')
    expect(readActivityLikes(storage, 'user-a')).toEqual(['ChIJA'])
    expect(readActivityLikes(storage, 'user-b')).toEqual(['park'])
    store.loadUser(null)
    expect(store.getSnapshot().likedIds.size).toBe(0)
    expect(store.getSnapshot().userId).toBeNull()
    expect(store.toggle('park')).toEqual({ requiresAuth: true })
  })

  it('reverts the previous state when storage writes fail', () => {
    const storage = {
      getItem: () => '["ChIJA"]',
      setItem: () => {
        throw new Error('quota')
      },
      removeItem: () => {},
    }
    const store = createActivityLikesStore({ storage })
    store.loadUser('user-a')
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(store.toggle('park')).toEqual({ ok: false, error: ACTIVITY_LIKES_SAVE_ERROR })
    expect(store.getSnapshot().likedIds.has('park')).toBe(false)
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(store.getSnapshot().error).toBe(ACTIVITY_LIKES_SAVE_ERROR)
    expect(store.getSnapshot().pendingIds.size).toBe(0)
  })

  it('ignores a nested toggle of the same id while saving', () => {
    const store = createActivityLikesStore({
      storage: {
        getItem: () => '[]',
        setItem() {
          nested = store.toggle('ChIJA')
        },
        removeItem: () => {},
      },
    })
    store.loadUser('user-a')
    let nested
    const first = store.toggle('ChIJA')
    expect(first).toEqual({ ok: true, liked: true })
    expect(nested).toEqual({ ok: false, pending: true })
    expect(store.getSnapshot().likedIds.has('ChIJA')).toBe(true)
    expect(store.getSnapshot().pendingIds.size).toBe(0)
  })
})

describe('writeActivityLikes', () => {
  it('does not throw when storage is missing', () => {
    expect(writeActivityLikes(null, 'user-a', ['ChIJA'])).toEqual({
      ok: false,
      error: ACTIVITY_LIKES_SAVE_ERROR,
    })
    expect(ACTIVITY_LIKES_NOTE).toMatch(/this browser only/i)
  })
})
