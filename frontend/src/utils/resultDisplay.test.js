import { describe, expect, it } from 'vitest'
import { NOT_AVAILABLE, displayValue, formatPrice, tripFactsLine } from './format'
import { resolveDestinationPhoto } from './photos'
import { buildMapMarkers } from './mapMarkers'

describe('displayValue', () => {
  it('renders Not available for missing optional card fields', () => {
    expect(displayValue(null)).toBe(NOT_AVAILABLE)
    expect(displayValue('')).toBe(NOT_AVAILABLE)
    expect(displayValue('Rome')).toBe('Rome')
    expect(formatPrice({})).toBeNull()
    expect(tripFactsLine({ flight: {}, weather: {} })).toBe('')
  })
})

describe('resolveDestinationPhoto', () => {
  it('prefers an API photo, then an exact bundled city, then a fallback', () => {
    expect(resolveDestinationPhoto({ photoUrl: 'https://img/rome.jpg', destination: { city: 'Rome' } }).kind).toBe('api')
    expect(resolveDestinationPhoto({ destination: { city: 'Rome' } }).kind).toBe('bundled')
    expect(resolveDestinationPhoto({ destination: { city: 'Valencia' } })).toEqual({ kind: 'fallback', src: null })
  })

  it('does not reuse another city’s bundled photo', () => {
    const photo = resolveDestinationPhoto({ destination: { city: 'Lisbon' } })
    const rome = resolveDestinationPhoto({ destination: { city: 'Rome' } })
    expect(photo.src).not.toBe(rome.src)
  })
})

describe('map with no valid pins', () => {
  it('keeps unmapped trips out of markers while list data remains', () => {
    const results = [
      {
        id: 'ZAG-ROM-1',
        destination: { city: 'Rome', latitude: null, longitude: null },
        flight: { price: 65, currency: 'EUR' },
      },
    ]
    expect(buildMapMarkers(results)).toEqual([])
    expect(results).toHaveLength(1)
  })
})
