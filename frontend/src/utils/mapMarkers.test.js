import { describe, expect, it } from 'vitest'
import { buildMapMarkers, isValidCoordinatePair } from './mapMarkers'

describe('isValidCoordinatePair', () => {
  it('accepts destination airport coordinates', () => {
    expect(isValidCoordinatePair(41.794594, 12.250346)).toBe(true)
  })

  it('rejects missing, 0,0, and out-of-range values', () => {
    expect(isValidCoordinatePair(null, 12)).toBe(false)
    expect(isValidCoordinatePair(0, 0)).toBe(false)
    expect(isValidCoordinatePair(91, 10)).toBe(false)
    expect(isValidCoordinatePair(10, 190)).toBe(false)
  })
})

describe('buildMapMarkers', () => {
  const rome = {
    id: 'ZAG-ROM-1',
    destination: { city: 'Rome', airport: 'Fiumicino', latitude: 41.79, longitude: 12.25 },
    country: { common_name: 'Italy' },
    flight: { price: 65, currency: 'EUR' },
  }

  it('uses destination coordinates and never origin fields', () => {
    const markers = buildMapMarkers([
      {
        ...rome,
        latitude: 99,
        flight: { ...rome.flight, origin_iata: 'ZAG' },
        origin: { latitude: 45.8, longitude: 16 },
      },
    ])
    expect(markers).toHaveLength(1)
    expect(markers[0].position).toEqual([41.79, 12.25])
  })

  it('deduplicates by airport and keeps every trip id on the shared marker', () => {
    const markers = buildMapMarkers([
      rome,
      { ...rome, id: 'ZAG-ROM-2', flight: { price: 80, currency: 'EUR' } },
    ])
    expect(markers).toHaveLength(1)
    expect(markers[0].resultIds).toEqual(['ZAG-ROM-1', 'ZAG-ROM-2'])
  })

  it('skips records without valid pins', () => {
    expect(buildMapMarkers([{ id: 'x', destination: { latitude: 0, longitude: 0 } }])).toEqual([])
  })
})
