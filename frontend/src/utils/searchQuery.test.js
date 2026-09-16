import { describe, expect, it } from 'vitest'
import { buildCandidateQuery, buildFlightQuery, isIsoDate } from './searchQuery'

describe('buildCandidateQuery', () => {
  it('requires origin_id and never sends IATA in that field', () => {
    expect(buildCandidateQuery({ originId: 'ZAG' })).toBeNull()
    expect(buildCandidateQuery({ originId: 'zagreb-hr', originIata: 'ZAG' })).toEqual({
      origin_id: 'zagreb-hr',
    })
  })

  it('omits empty filters and includes supported candidate params', () => {
    expect(
      buildCandidateQuery({
        originId: 'zagreb-hr',
        maxBudget: 400,
        directOnly: true,
        departureDate: '2026-09-18',
        returnDate: '2026-09-22',
        country: 'IT',
        minTemp: 20,
        maxDurationMinutes: 300,
        mood: 'warm',
      }),
    ).toEqual({
      origin_id: 'zagreb-hr',
      max_price: 400,
      max_changeovers: 0,
      departure_date: '2026-09-18',
      return_date: '2026-09-22',
      country: 'IT',
      min_temp: 20,
      max_duration_minutes: 300,
    })
  })

  it('omits blank, invalid and inverted dates', () => {
    expect(
      buildCandidateQuery({
        originId: 'zagreb-hr',
        maxBudget: '',
        country: '',
        departureDate: '18/09/2026',
      }),
    ).toEqual({ origin_id: 'zagreb-hr' })

    expect(
      buildCandidateQuery({
        originId: 'zagreb-hr',
        departureDate: '2026-09-22',
        returnDate: '2026-09-18',
      }),
    ).toEqual({ origin_id: 'zagreb-hr' })
  })
})

describe('buildFlightQuery', () => {
  it('drops max_changeovers and max_duration_minutes', () => {
    const candidates = buildCandidateQuery({
      originId: 'zagreb-hr',
      maxBudget: 300,
      directOnly: true,
      maxDurationMinutes: 240,
    })
    expect(buildFlightQuery(candidates)).toEqual({
      origin_id: 'zagreb-hr',
      max_price: 300,
    })
  })
})

describe('isIsoDate', () => {
  it('accepts calendar dates only', () => {
    expect(isIsoDate('2026-09-18')).toBe(true)
    expect(isIsoDate('2026-13-01')).toBe(false)
    expect(isIsoDate('')).toBe(false)
  })
})
