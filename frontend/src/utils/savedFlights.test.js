import { describe, expect, it } from 'vitest'
import { attachDestinationCityPhotos } from './adaptRecommendations'
import {
  adaptSavedFlights,
  destinationsForView,
  flightReferenceFromDestination,
  keepSavedFlightPhotos,
  savedFlightIds,
  showPlannerComposer,
  showPlannerConversation,
  showPlannerFilters,
} from './savedFlights'

const apiPayload = {
  items: [
    {
      flight_id: 'ZAG-ROM-2026-09-18',
      origin_id: 'zagreb-hr',
      saved_at: '2026-09-18T12:40:00Z',
      last_checked_at: '2026-09-19T08:00:00Z',
      saved_price: 65,
      last_checked_price: 70,
      price_changed: true,
      availability: 'available',
      flight: {
        id: 'ZAG-ROM-2026-09-18',
        origin_id: 'zagreb-hr',
        origin_iata: 'ZAG',
        destination_city: 'Rome',
        destination_country: 'Italy',
        destination_country_code: 'IT',
        price_eur: 70,
        currency: 'EUR',
        latitude: 41.79,
        longitude: 12.25,
      },
    },
    {
      flight_id: 'ZAG-LIS-2026-09-18',
      origin_id: 'zagreb-hr',
      saved_at: '2026-09-17T09:00:00Z',
      last_checked_at: '2026-09-17T09:00:00Z',
      saved_price: 189,
      last_checked_price: 189,
      price_changed: false,
      availability: 'unavailable',
      flight: {
        id: 'ZAG-LIS-2026-09-18',
        origin_id: 'zagreb-hr',
        origin_iata: 'ZAG',
        destination_city: 'Lisbon',
        destination_country: 'Portugal',
        destination_country_code: 'PT',
        price_eur: 189,
        currency: 'EUR',
        temp_max_c: 24,
      },
    },
  ],
}

describe('adaptSavedFlights', () => {
  it('maps relationship metadata onto the destination view model', () => {
    const [rome, lisbon] = adaptSavedFlights(apiPayload)
    expect(rome.id).toBe('ZAG-ROM-2026-09-18')
    expect(rome.originId).toBe('zagreb-hr')
    expect(rome.flight.price).toBe(70)
    expect(rome.destination.city).toBe('Rome')
    expect(rome.priceChanged).toBe(true)
    expect(rome.savedAt).toBe('2026-09-18T12:40:00Z')
    expect(lisbon.availability).toBe('unavailable')
    expect(lisbon.destination.city).toBe('Lisbon')
    expect(lisbon.flight.price).toBe(189)
    expect(lisbon.weather.average_max_temperature_c).toBe(24)
  })
})

describe('saved view independence', () => {
  const results = [{ id: 'search-only' }]
  const savedItems = adaptSavedFlights(apiPayload)

  it('uses server-backed saved items instead of current recommendation results', () => {
    expect(destinationsForView('saved', { results, savedItems })).toEqual(savedItems)
    expect(destinationsForView('explore', { results, savedItems })).toEqual(results)
    expect(savedFlightIds(savedItems)).toEqual(['ZAG-ROM-2026-09-18', 'ZAG-LIS-2026-09-18'])
  })

  it('clears previous saved flights when the authenticated user changes', () => {
    const previousUserItems = adaptSavedFlights(apiPayload)
    const nextUserPayload = { items: [] }
    expect(previousUserItems).toHaveLength(2)
    expect(adaptSavedFlights(nextUserPayload)).toEqual([])
  })

  it('does not show chat, composer, or filters in Saved', () => {
    expect(showPlannerConversation('saved', true)).toBe(false)
    expect(showPlannerComposer('saved')).toBe(false)
    expect(showPlannerFilters('saved')).toBe(false)
    expect(showPlannerConversation('explore', true)).toBe(true)
    expect(showPlannerComposer('explore')).toBe(true)
    expect(showPlannerFilters('explore')).toBe(true)
  })
})

describe('saved flight photos', () => {
  it('joins destination-city origin photos when the flight has none', () => {
    const [rome] = adaptSavedFlights(apiPayload)
    expect(rome.photoUrl).toBeNull()
    const withPhotos = attachDestinationCityPhotos([rome], [
      {
        city: 'Rome',
        country_code: 'IT',
        photo_url: 'https://images.example/rome-origin.jpg',
        photo_url_small: 'https://images.example/rome-origin-small.jpg',
      },
    ])
    expect(withPhotos[0].photoUrl).toBe('https://images.example/rome-origin.jpg')
    expect(withPhotos[0].destination.city).toBe('Rome')
  })

  it('keeps explore photos when the save response has no image urls', () => {
    const [rome] = adaptSavedFlights(apiPayload)
    const merged = keepSavedFlightPhotos(rome, {
      photoUrl: 'https://images.example/rome.jpg',
      photoUrlSmall: 'https://images.example/rome-small.jpg',
    })
    expect(merged.photoUrl).toBe('https://images.example/rome.jpg')
    expect(merged.photoUrlSmall).toBe('https://images.example/rome-small.jpg')
  })
})

describe('flightReferenceFromDestination', () => {
  it('sends only the flight id', () => {
    expect(
      flightReferenceFromDestination({
        id: 'ZAG-ROM-2026-09-18',
        documentId: 'ZAG-ROM-2026-09-18',
        originId: 'zagreb-hr',
        flight: { price: 65 },
      }),
    ).toEqual({
      flight_id: 'ZAG-ROM-2026-09-18',
    })
  })
})
