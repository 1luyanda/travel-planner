import { describe, expect, it } from 'vitest'
import {
  adaptRecommendations,
  attachDestinationCityPhotos,
  enrichRecommendations,
} from './adaptRecommendations'

const rome = {
  destination_id: 'ZAG-ROM-2026-09-18',
  destination_iata: 'FCO',
  city: 'Rome',
  rank: 1,
  price_eur: 65,
  changeover_count: 0,
  flight_duration_minutes: 170,
  average_max_temperature_c: 27.8,
  price_score: 1,
  weather_score: 0.4,
  stops_score: 1,
  duration_score: 0.8,
  final_score: 0.82,
  summary: 'Rome stays within budget and is a short hop from Zagreb.',
  evidence: [{ id: 'e1', code: 'within_budget', statement: 'Fare is EUR 65 against a EUR 400 budget.' }],
}

const lisbon = {
  destination_id: 'ZAG-LIS-2026-09-18',
  destination_iata: 'LIS',
  city: 'Lisbon',
  rank: 2,
  price_eur: 118,
  changeover_count: 1,
  flight_duration_minutes: 310,
  average_max_temperature_c: 24,
  price_score: 0.6,
  weather_score: 0.2,
  stops_score: 0.3,
  duration_score: 0.2,
  final_score: 0.41,
  summary: 'Lisbon is warmer than average for this shortlist.',
  evidence: [],
}

const flight = {
  id: 'ZAG-ROM-2026-09-18',
  origin_iata: 'ZAG',
  destination_city: 'Rome',
  destination_country: 'Italy',
  latitude: 41.794594,
  longitude: 12.250346,
  photo_url: 'https://img/rome.jpg',
  airline_code: 'FR',
}

describe('adaptRecommendations', () => {
  it('preserves server order, rank, summary and evidence', () => {
    const adapted = adaptRecommendations({
      status: 'ready',
      origin_id: 'zagreb-hr',
      request: { origin: 'ZAG' },
      recommendations: [rome, lisbon],
      rejected: [{ destination_id: 'ZAG-AGP-2026-09-18', reasons: [] }],
      data_source: 'cosmos://TravelPlaner/flights',
    })

    expect(adapted.results.map((item) => item.id)).toEqual([
      'ZAG-ROM-2026-09-18',
      'ZAG-LIS-2026-09-18',
    ])
    expect(adapted.results.map((item) => item.rank)).toEqual([1, 2])
    expect(adapted.results[0].explanation.summary).toBe(rome.summary)
    expect(adapted.results[0].explanation.evidence).toEqual(rome.evidence)
    expect(adapted.results[0].scores.total).toBe(0.82)
    expect(adapted.results[0].flight.price).toBe(65)
    expect(adapted.rejected).toHaveLength(1)
  })

  it('keeps origin and Cosmos weather aliases without inventing photos', () => {
    const adapted = adaptRecommendations({
      origin_id: 'zagreb-hr',
      origin: { id: 'zagreb-hr', city: 'Zagreb', country: 'Croatia', city_iata: ['ZAG'] },
      recommendations: [rome],
    })
    expect(adapted.results[0].originCity).toBe('Zagreb')
    expect(adapted.results[0].originCountry).toBe('Croatia')
    expect(adapted.results[0].originIata).toBe('ZAG')
    expect(adapted.results[0].photoUrl).toBeNull()
    expect(adapted.results[0].tripDurationDays).toBeNull()
  })

  it('does not invent coordinates or photos when enrichment is missing', () => {
    const adapted = adaptRecommendations({ recommendations: [rome] })
    expect(adapted.results[0].destination.latitude).toBeNull()
    expect(adapted.results[0].photoUrl).toBeNull()
    expect(adapted.results[0].flight.airline_code).toBeNull()
  })

  it('joins flights bundled on the recommend payload', () => {
    const adapted = adaptRecommendations({
      recommendations: [rome],
      flights: [flight],
    })
    expect(adapted.results[0].joinedFlight).toBe(true)
    expect(adapted.results[0].destination.latitude).toBe(41.794594)
    expect(adapted.results[0].photoUrl).toBe('https://img/rome.jpg')
    expect(adapted.results[0].flight.airline_code).toBe('FR')
  })
})

describe('enrichRecommendations', () => {
  it('joins display fields without reordering or rescoring', () => {
    const adapted = adaptRecommendations({
      origin_id: 'zagreb-hr',
      recommendations: [rome, lisbon],
    })
    const originalOrder = adapted.results.map((item) => item.id)
    const originalScores = adapted.results.map((item) => item.scores.total)

    const enriched = enrichRecommendations(adapted.results, { flights: [flight] })

    expect(enriched.map((item) => item.id)).toEqual(originalOrder)
    expect(enriched.map((item) => item.scores.total)).toEqual(originalScores)
    expect(enriched).toHaveLength(2)
    expect(enriched[0].destination.latitude).toBe(41.794594)
    expect(enriched[0].photoUrl).toBe('https://img/rome.jpg')
    expect(enriched[1].destination.latitude).toBeNull()
  })

  it('maps Cosmos rain_pct and temp fields onto the view model', () => {
    const adapted = adaptRecommendations({ recommendations: [rome] })
    const enriched = enrichRecommendations(adapted.results, {
      flights: [{ ...flight, rain_pct: 12, temp_min_c: 18.5, sunshine_hours: 9 }],
    })
    expect(enriched[0].weather.average_precipitation_probability_percent).toBe(12)
    expect(enriched[0].weather.average_min_temperature_c).toBe(18.5)
    expect(enriched[0].weather.average_sunshine_hours).toBe(9)
  })

  it('does not drop recommendations when enrichment fails to match', () => {
    const adapted = adaptRecommendations({ recommendations: [rome, lisbon] })
    const enriched = enrichRecommendations(adapted.results, {
      flights: [{ ...flight, id: 'OTHER-ID', latitude: 1, longitude: 2 }],
    })
    expect(enriched.map((item) => item.id)).toEqual(adapted.results.map((item) => item.id))
    expect(enriched[0].destination.latitude).toBeNull()
  })
})

describe('attachDestinationCityPhotos', () => {
  const zagrebOrigin = {
    id: 'zagreb-hr',
    city: 'Zagreb',
    country_code: 'HR',
    photo_url: 'https://images.example/zagreb.jpg',
  }
  const romeOrigin = {
    id: 'rome-it',
    city: 'Rome',
    country_code: 'IT',
    photo_url: 'https://images.example/rome-origin.jpg',
    photo_url_small: 'https://images.example/rome-origin-small.jpg',
  }

  it('uses the destination city origin photo, not the departure city photo', () => {
    const adapted = adaptRecommendations({ recommendations: [rome, lisbon] })
    const withPhotos = attachDestinationCityPhotos(adapted.results, [zagrebOrigin, romeOrigin])

    expect(withPhotos.map((item) => item.id)).toEqual(adapted.results.map((item) => item.id))
    expect(withPhotos[0].photoUrl).toBe('https://images.example/rome-origin.jpg')
    expect(withPhotos[0].photoUrlSmall).toBe('https://images.example/rome-origin-small.jpg')
    expect(withPhotos[0].scores.total).toBe(adapted.results[0].scores.total)
    expect(withPhotos[1].photoUrl).toBeNull()
    expect(withPhotos.every((item) => item.photoUrl !== zagrebOrigin.photo_url)).toBe(true)
  })

  it('does not replace a flight photo_url with an origin photo', () => {
    const adapted = adaptRecommendations({ recommendations: [rome] })
    const fromFlight = enrichRecommendations(adapted.results, { flights: [flight] })
    const withPhotos = attachDestinationCityPhotos(fromFlight, [romeOrigin])
    expect(withPhotos[0].photoUrl).toBe('https://img/rome.jpg')
  })
})
