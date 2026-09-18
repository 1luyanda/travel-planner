import { describe, expect, it } from 'vitest'
import { destinationPhotoAlt, resolveDestinationPhoto } from './photos'

describe('resolveDestinationPhoto', () => {
  it('prefers a stored API URL over bundled city assets', () => {
    const resolved = resolveDestinationPhoto({
      photoUrl: 'https://images.example/malta.jpg',
      destination: { city: 'Malta' },
    })
    expect(resolved).toEqual({ kind: 'api', src: 'https://images.example/malta.jpg' })
  })

  it('uses bundled Rome/Malta/Lisbon/Athens assets only when no API URL exists', () => {
    const resolved = resolveDestinationPhoto({
      photoUrl: null,
      destination: { city: 'Rome' },
    })
    expect(resolved.kind).toBe('bundled')
    expect(resolved.src).toBeTruthy()
  })

  it('falls back to a placeholder for unmapped cities', () => {
    const resolved = resolveDestinationPhoto({
      photoUrl: null,
      destination: { city: 'Namangan' },
    })
    expect(resolved).toEqual({ kind: 'fallback', src: null })
    expect(destinationPhotoAlt({ destination: { city: 'Namangan' } }, resolved)).toBe(
      'Photo of Namangan',
    )
  })
})
