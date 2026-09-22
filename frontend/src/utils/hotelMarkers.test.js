import { describe, expect, it } from 'vitest'
import { buildHotelMarkers, hotelKey, hotelPosition } from './hotelMarkers'
import { buildMapMarkers } from './mapMarkers'
import { normalizeHotelsResponse } from './hotels'

describe('hotel map markers', () => {
  it('preserves backend order and uses OSM identity across reordered lists', () => {
    const hotels = [
      { name: 'Zulu', osm_id: 'node/2', latitude: 22.346, longitude: 31.618 },
      { name: 'Alpha', osm_id: 'node/1', latitude: 22.345, longitude: 31.617 },
    ]
    const markers = buildHotelMarkers(hotels)
    expect(markers.map((marker) => marker.key)).toEqual(['node/2', 'node/1'])
    expect(markers[0].position).toEqual([22.346, 31.618])
    expect(buildHotelMarkers([...hotels].reverse())[1].key).toBe(markers[0].key)
    expect(hotelKey({ name: 'No OSM', latitude: 1, longitude: 2 }))
      .toBe(hotelKey({ name: 'No OSM', latitude: 1, longitude: 2, stars: 4 }))
  })

  it.each([
    [null, 1], [1, undefined], [NaN, 1], [1, Infinity], [91, 1], [1, -181],
    ['', 1], [true, 1], ['22.3', 1],
  ])('skips invalid hotel coordinates %s, %s', (latitude, longitude) => {
    expect(buildHotelMarkers([{ name: 'Invalid', latitude, longitude }])).toEqual([])
  })

  it('accepts numeric bounds and zero coordinates without changing destination placeholder policy', () => {
    expect(hotelPosition({ latitude: 0, longitude: 0 })).toEqual([0, 0])
    expect(hotelPosition({ latitude: -90, longitude: 180 })).toEqual([-90, 180])
    expect(buildMapMarkers([{ id: 'placeholder', destination: { latitude: 0, longitude: 0 } }])).toEqual([])
  })

  it('retains invalid-location hotels in the list but omits their markers', () => {
    const { hotels } = normalizeHotelsResponse({ destination_id: 'rome-it', hotels: [
      { name: 'Missing', distance_km: 0.1 },
      { name: 'Mapped', distance_km: 0.2, latitude: 41.9, longitude: 12.5 },
      { name: 'Invalid', distance_km: 0.3, latitude: 200, longitude: 12 },
    ] })
    expect(hotels).toHaveLength(3)
    expect(buildHotelMarkers(hotels).map((marker) => marker.hotel.name)).toEqual(['Mapped'])
  })
})
