import { describe, expect, it } from 'vitest'
import { NOT_AVAILABLE, displayValue, formatPrice, tripFactItems, tripFactsLine } from './format'
import { destinationPhotoAlt, resolveDestinationPhoto } from './photos'
import { buildMapMarkers } from './mapMarkers'

describe('displayValue', () => {
  it('renders Not available for missing optional card fields', () => {
    expect(displayValue(null)).toBe(NOT_AVAILABLE)
    expect(displayValue('')).toBe(NOT_AVAILABLE)
    expect(displayValue('Rome')).toBe('Rome')
    expect(formatPrice({})).toBeNull()
    expect(tripFactsLine({ flight: {}, weather: {} })).toBe('')
    expect(tripFactItems({ flight: {}, weather: {} })).toEqual([])
    expect(tripFactItems({
      flight: {
        outbound_stops: 0,
        duration_minutes: 170,
        outbound_duration_minutes: 85,
        return_duration_minutes: 85,
      },
      weather: { average_max_temperature_c: 27.8, average_precipitation_probability_percent: 13 },
    })).toEqual([
      'Direct',
      'Total flight time: 2h 50m',
      '27.8°C avg max',
      '13% rain',
    ])
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

  it('builds descriptive alt text from city and country', () => {
    expect(
      destinationPhotoAlt(
        { destination: { city: 'Valencia' }, country: { common_name: 'Spain' } },
        { kind: 'fallback' },
      ),
    ).toBe('Photo of Valencia, Spain')
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
