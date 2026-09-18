import { describe, expect, it } from 'vitest'
import { toggleSavedId } from './savedDestinations'

describe('toggleSavedId', () => {
  it('adds and removes an id without mutating the original list', () => {
    const start = ['a']
    const added = toggleSavedId(start, 'b')
    expect(added).toEqual(['a', 'b'])
    expect(start).toEqual(['a'])
    expect(toggleSavedId(added, 'a')).toEqual(['b'])
  })
})
