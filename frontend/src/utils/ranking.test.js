import { describe, expect, it } from 'vitest'
import { applyBrowserRanking, defaultWeights, filterDestinations, rankDestinations, rankingReason } from './ranking'

const sample = [
  {
    id: 'cheap-direct',
    originId: 'zagreb-hr',
    flight: { origin_iata: 'ZAG', price: 65, outbound_stops: 0, duration_minutes: 170 },
    weather: { average_max_temperature_c: 22 },
  },
  {
    id: 'warm-long',
    originId: 'zagreb-hr',
    flight: { origin_iata: 'ZAG', price: 260, outbound_stops: 1, duration_minutes: 400 },
    weather: { average_max_temperature_c: 31 },
  },
]

describe('filterDestinations', () => {
  it('filters by origin_id, budget and direct outbound flights', () => {
    const filtered = filterDestinations(sample, { originId: 'zagreb-hr', maxBudget: 100, directOnly: true })
    expect(filtered.map((item) => item.id)).toEqual(['cheap-direct'])
  })

  it('does not treat an empty origin_id as all origins', () => {
    expect(filterDestinations(sample, { originId: '', maxBudget: 400, directOnly: false })).toEqual([])
  })

  it('does not match IATA codes as origin_id', () => {
    expect(filterDestinations(sample, { originId: 'ZAG', maxBudget: 400, directOnly: false })).toEqual([])
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

  it('scores missing ranking fields as 0 without inventing source values', () => {
    const ranked = rankDestinations(
      [{ id: 'gap', originId: 'zagreb-hr', flight: {}, weather: {} }],
      defaultWeights(true),
    )
    expect(ranked[0].flight.price).toBeUndefined()
    expect(ranked[0].scores.price).toBe(0)
    expect(ranked[0].scores.weather).toBe(0)
    expect(ranked[0].scores.stops).toBe(0)
    expect(ranked[0].scores.duration).toBe(0)
  })

  it('applies browser ranking exactly once per weight set', () => {
    const first = applyBrowserRanking(sample, false)
    const second = applyBrowserRanking(first.ranked, false)
    expect(first.ranked.map((item) => item.id)).toEqual(['cheap-direct', 'warm-long'])
    expect(second.ranked.map((item) => item.id)).toEqual(first.ranked.map((item) => item.id))
    expect(first.ranked[0].scores.total).toBe(second.ranked[0].scores.total)
  })
})
