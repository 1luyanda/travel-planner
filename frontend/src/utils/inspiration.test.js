import { describe, expect, it, vi } from 'vitest'
import {
  adaptInspirationFlights,
  applyInspirationDraft,
  canOpenTripDetails,
  inspirationEmptyMessage,
  inspirationFare,
  inspirationFlightQuery,
  inspirationHeading,
  inspirationHint,
  INSPIRATION_GENERIC_HEADING,
  INSPIRATION_HINT_GENERIC,
  INSPIRATION_HINT_STORED,
  loadInspirationFlights,
  runInspirationFetch,
  staticInspirationDestinations,
} from './inspiration'

const romeFlight = {
  id: 'ZAG-ROM-2026-09-18',
  origin_id: 'zagreb-hr',
  origin_iata: 'ZAG',
  destination_iata: 'FCO',
  destination_city: 'Rome',
  destination_country: 'Italy',
  destination_country_code: 'IT',
  price_eur: 65,
  currency: 'EUR',
  departure_at: '2026-09-18T15:55:00+02:00',
  return_at: '2026-09-22T23:50:00+02:00',
}

const lisbonFlight = {
  id: 'ZAG-LIS-2026-09-18',
  origin_id: 'zagreb-hr',
  destination_iata: 'LIS',
  destination_city: 'Lisbon',
  destination_country: 'Portugal',
  price_eur: 189,
  currency: 'EUR',
  departure_at: '2026-09-18T08:10:00+02:00',
  return_at: '2026-09-22T21:40:00+01:00',
}

describe('static inspiration', () => {
  it('uses bundled city photos without prices or personalisation', () => {
    const destinations = staticInspirationDestinations()
    expect(destinations.map((item) => item.destination.city)).toEqual([
      'Athens',
      'Lisbon',
      'Malta',
      'Rome',
    ])
    expect(destinations).toHaveLength(4)
    for (const destination of destinations) {
      expect(inspirationFare(destination)).toBeNull()
      expect(destination.id).toMatch(/^inspiration:/)
      expect(canOpenTripDetails(destination)).toBe(false)
    }
    expect(inspirationHeading(null)).toBe(INSPIRATION_GENERIC_HEADING)
    expect(inspirationHint({})).toBe(INSPIRATION_HINT_GENERIC)
    expect(inspirationHint({ origin: null })).not.toMatch(/for you/i)
  })
})

describe('origin inspiration', () => {
  it('builds the flights query from origin and existing date rules', () => {
    const origin = { originId: 'zagreb-hr', city: 'Zagreb' }
    expect(inspirationHeading(origin)).toBe('Explore from Zagreb')
    expect(
      inspirationFlightQuery({
        origin,
        departureDate: '2026-09-18',
        returnDate: '2026-09-22',
      }),
    ).toEqual({
      origin_id: 'zagreb-hr',
      departure_date: '2026-09-18',
      return_date: '2026-09-22',
    })
    expect(
      inspirationFlightQuery({
        origin,
        departureDate: '2026-09-18',
        returnDate: '',
      }),
    ).toEqual({
      origin_id: 'zagreb-hr',
      departure_date: '2026-09-18',
    })
    expect(
      inspirationFlightQuery({
        origin,
        departureDate: '2026-09-22',
        returnDate: '2026-09-18',
      }),
    ).toEqual({ origin_id: 'zagreb-hr' })
  })

  it('deduplicates by destination and keeps stored fare fields together', () => {
    const cheaperRome = { ...romeFlight, id: 'ZAG-ROM-CHEAP', price_eur: 40 }
    const laterRome = { ...romeFlight, price_eur: 90, departure_at: '2026-10-01T10:00:00+02:00' }
    const destinations = adaptInspirationFlights([cheaperRome, laterRome, lisbonFlight], {
      originId: 'zagreb-hr',
    })
    expect(destinations.map((item) => item.destination.city)).toEqual(['Rome', 'Lisbon'])
    expect(destinations[0].id).toBe('ZAG-ROM-CHEAP')
    expect(inspirationFare(destinations[0])).toMatchObject({ priceText: '40 EUR' })
    expect(inspirationFare(destinations[0]).departureText).toBeTruthy()
    expect(inspirationFare(destinations[0]).returnText).toBeTruthy()
    expect(inspirationHint({ origin: { originId: 'zagreb-hr', city: 'Zagreb' } })).toBe(
      INSPIRATION_HINT_STORED,
    )
  })

  it('omits prices unless price, currency and both dates are present', () => {
    expect(
      inspirationFare(
        adaptInspirationFlights([{ ...romeFlight, currency: null }])[0],
      ),
    ).toBeNull()
    expect(
      inspirationFare(
        adaptInspirationFlights([{ ...romeFlight, return_at: null }])[0],
      ),
    ).toBeNull()
    expect(inspirationFare(adaptInspirationFlights([romeFlight])[0]).priceText).toBe('65 EUR')
  })

  it('does not invent a second destination when flights are missing', () => {
    expect(adaptInspirationFlights([])).toEqual([])
    expect(
      inspirationEmptyMessage({
        origin: { city: 'Zagreb' },
        query: { origin_id: 'zagreb-hr', departure_date: '2026-09-18' },
      }),
    ).toBe('No stored flights from Zagreb for the selected dates.')
  })
})

describe('inspiration fetch lifecycle', () => {
  it('reuses a cache and ignores a stale previous origin', async () => {
    const cache = new Map()
    let resolveZagreb
    const fetchFlightsFn = vi.fn((params) => {
      if (params.origin_id === 'zagreb-hr') {
        return new Promise((resolve) => {
          resolveZagreb = resolve
        })
      }
      return Promise.resolve({
        origin_id: 'london-gb',
        flights: [{ ...lisbonFlight, origin_id: 'london-gb', id: 'LON-LIS-1' }],
      })
    })

    const first = runInspirationFetch({
      query: { origin_id: 'zagreb-hr' },
      seq: 1,
      isCurrent: (seq) => seq === 2,
      fetchFlightsFn,
      cache,
    })
    const second = await runInspirationFetch({
      query: { origin_id: 'london-gb' },
      seq: 2,
      isCurrent: (seq) => seq === 2,
      fetchFlightsFn,
      cache,
    })
    expect(second.status).toBe('ready')
    expect(second.destinations[0].destination.city).toBe('Lisbon')

    resolveZagreb({ origin_id: 'zagreb-hr', flights: [romeFlight] })
    await expect(first).resolves.toEqual({ status: 'stale' })

    const cached = await loadInspirationFlights(
      { origin_id: 'london-gb' },
      { fetchFlightsFn, cache },
    )
    expect(cached[0].destination.city).toBe('Lisbon')
    expect(fetchFlightsFn).toHaveBeenCalledTimes(2)
  })

  it('returns aborted when the flights request is cancelled', async () => {
    const error = new Error('Aborted')
    error.name = 'AbortError'
    const outcome = await runInspirationFetch({
      query: { origin_id: 'zagreb-hr' },
      seq: 1,
      isCurrent: () => true,
      fetchFlightsFn: async () => {
        throw error
      },
      cache: new Map(),
    })
    expect(outcome).toEqual({ status: 'aborted' })
  })

  it('returns an error without substituting generic destinations', async () => {
    const fetchFlightsFn = vi.fn(async () => {
      throw new Error('Stored travel data is temporarily unavailable.')
    })
    const outcome = await runInspirationFetch({
      query: { origin_id: 'zagreb-hr' },
      seq: 1,
      isCurrent: () => true,
      fetchFlightsFn,
      cache: new Map(),
    })
    expect(outcome).toMatchObject({
      status: 'error',
      destinations: [],
      message: 'Stored travel data is temporarily unavailable.',
    })
  })

  it('does not fetch flights when no origin is selected', async () => {
    const fetchFlightsFn = vi.fn()
    const outcome = await runInspirationFetch({
      query: null,
      seq: 1,
      isCurrent: () => true,
      fetchFlightsFn,
    })
    expect(fetchFlightsFn).not.toHaveBeenCalled()
    expect(outcome.status).toBe('static')
    expect(outcome.destinations).toHaveLength(4)
  })
})

describe('inspiration card actions', () => {
  it('seeds an empty draft and leaves existing text alone', () => {
    expect(applyInspirationDraft({ draft: '', city: 'Rome' })).toEqual({
      draft: 'A getaway to Rome',
      hint: '',
      focusComposer: true,
    })
    expect(applyInspirationDraft({ draft: 'A warm escape under €500', city: 'Rome' })).toEqual({
      draft: 'A warm escape under €500',
      hint: 'Add Rome to your request, then search.',
      focusComposer: true,
    })
    expect(applyInspirationDraft({ draft: 'Weekend in Rome please', city: 'Rome' }).hint).toBe('')
  })

  it('opens trip details only for stored flights with complete ids', () => {
    const stored = adaptInspirationFlights([romeFlight])[0]
    expect(canOpenTripDetails(stored)).toBe(true)
    expect(canOpenTripDetails(staticInspirationDestinations()[0])).toBe(false)
    expect(canOpenTripDetails({ destination: { city: 'Rome' } })).toBe(false)
  })
})
