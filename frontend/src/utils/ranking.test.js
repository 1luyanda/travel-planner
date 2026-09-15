import { describe, expect, it } from 'vitest'
import { defaultWeights, filterDestinations, rankDestinations, rankingReason } from './ranking'

const sample = [
  {
    id: 'cheap-direct',
    flight: { origin_iata: 'ZAG', price: 65, outbound_stops: 0, duration_minutes: 170 },
    weather: { average_max_temperature_c: 22 },
  },
  {
    id: 'warm-long',
    flight: { origin_iata: 'ZAG', price: 260, outbound_stops: 1, duration_minutes: 400 },
    weather: { average_max_temperature_c: 31 },
  },
]

describe('filterDestinations', () => {
  it('filters by budget and direct outbound flights', () => {
    const filtered = filterDestinations(sample, { origin: 'ZAG', maxBudget: 100, directOnly: true })
    expect(filtered.map((item) => item.id)).toEqual(['cheap-direct'])
  })
})

describe('rankDestinations', () => {
  it('puts the cheaper direct trip first with default weights', () => {
    const ranked = rankDestinations(sample, defaultWeights(false))
    expect(ranked[0].id).toBe('cheap-direct')
    expect(ranked[0].scores.total).toBeGreaterThan(ranked[1].scores.total)
  })

  it('raises the warmer trip when weather weight is high', () => {
    const ranked = rankDestinations(sample, { price: 0.1, weather: 0.7, stops: 0.1, duration: 0.1 })
    expect(ranked[0].id).toBe('warm-long')
  })

  it('only labels a ranking reason from weighted scores', () => {
    const ranked = rankDestinations(sample, defaultWeights(false))
    expect(rankingReason(ranked[0], defaultWeights(false))).toMatch(/price|stops|duration/i)
  })
})
