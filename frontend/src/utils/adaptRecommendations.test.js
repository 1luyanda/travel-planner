import { describe, expect, it } from 'vitest'
import { adaptRecommendations, enrichRecommendations } from './adaptRecommendations'

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

  it('does not invent coordinates or photos when enrichment is missing', () => {
    const adapted = adaptRecommendations({ recommendations: [rome] })
    expect(adapted.results[0].destination.latitude).toBeNull()
    expect(adapted.results[0].photoUrl).toBeNull()
    expect(adapted.results[0].flight.airline_code).toBeNull()
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

  it('does not drop recommendations when enrichment fails to match', () => {
    const adapted = adaptRecommendations({ recommendations: [rome, lisbon] })
    const enriched = enrichRecommendations(adapted.results, {
      flights: [{ ...flight, id: 'OTHER-ID', latitude: 1, longitude: 2 }],
    })
    expect(enriched.map((item) => item.id)).toEqual(adapted.results.map((item) => item.id))
    expect(enriched[0].destination.latitude).toBeNull()
  })
})
