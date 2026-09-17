import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadSavedIds, persistSavedIds, toggleSavedId } from './savedDestinations'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('toggleSavedId', () => {
  it('adds and removes an id without mutating the original list', () => {
    const start = ['a']
    const added = toggleSavedId(start, 'b')
    expect(added).toEqual(['a', 'b'])
    expect(start).toEqual(['a'])
    expect(toggleSavedId(added, 'a')).toEqual(['b'])
  })
})

it('keeps saved destinations separate for each authenticated user', () => {
  const values = new Map()
  vi.stubGlobal('localStorage', {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  })

  persistSavedIds('user-a', ['rome'])
  persistSavedIds('user-b', ['lisbon'])

  expect(loadSavedIds('user-a')).toEqual(['rome'])
  expect(loadSavedIds('user-b')).toEqual(['lisbon'])
})
