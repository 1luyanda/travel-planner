import { describe, expect, it, vi, afterEach } from 'vitest'
import {
  ApiError,
  appendQuery,
  deleteSavedFlight,
  fetchActivities,
  fetchCandidates,
  fetchFlights,
  fetchHotels,
  fetchOrigin,
  fetchSavedFlights,
  recommendTrip,
  refineTrip,
  saveFlight,
  searchOrigins,
} from './travelApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('appendQuery', () => {
  it('omits undefined, null and blank values and encodes the rest', () => {
    expect(
      appendQuery('/api/candidates', {
        origin_id: 'zagreb-hr',
        max_price: 400,
        country: '',
        min_temp: null,
        departure_date: undefined,
      }),
    ).toBe('/api/candidates?origin_id=zagreb-hr&max_price=400')
  })
})

describe('hotels API', () => {
  it('uses the shared credentialed GET helper, exact ID, limit 5 and abort signal', async () => {
    const controller = new AbortController()
    const id = 'stored/id&special'
    const fetchMock = vi.fn(async () => ({
      ok: true, json: async () => ({ destination_id: id, hotels: [] }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    await fetchHotels(id, { signal: controller.signal })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/hotels?destination_id=stored%2Fid%26special&limit=5',
      { method: 'GET', credentials: 'include', signal: controller.signal },
    )
  })

  it.each([null, undefined, '', '   '])('does not request hotels for an absent ID: %s', async (id) => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchHotels(id)).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('uses existing error handling for failures and propagates cancellation', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false, status: 503, json: async () => ({ detail: 'Hotel data is temporarily unavailable.' }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchHotels('rome-it')).rejects.toMatchObject({ status: 503 })
    fetchMock.mockRejectedValueOnce(Object.assign(new Error('Aborted'), { name: 'AbortError' }))
    await expect(fetchHotels('rome-it')).rejects.toMatchObject({ name: 'AbortError' })
  })

  it.each([{ hotels: [] }, { destination_id: 'other', hotels: [] }, { destination_id: 'rome-it' }])(
    'rejects an unexpected response instead of showing hotels for the wrong destination', async (body) => {
      vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => body })))
      await expect(fetchHotels('rome-it')).rejects.toBeInstanceOf(ApiError)
    },
  )

  it.each(['recommend', 'refine'])('preserves hotel IDs in /api/%s parsing', async (route) => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ready', recommendations: [
        { destination_id: 'offer-1', hotel_destination_id: 'rome-it' },
        { destination_id: 'offer-2', hotel_destination_id: null },
      ] }),
    })))
    const response = route === 'recommend' ? await recommendTrip({})
      : await refineTrip({ text: 'Warmer', request: { origin: 'ZAG' } })
    expect(response.recommendations.map((item) => item.hotel_destination_id)).toEqual(['rome-it', null])
  })
})

describe('searchOrigins', () => {
  it('parses origin documents and keeps id separate from IATA lists', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => [
          {
            id: 'zagreb-hr',
            city: 'Zagreb',
            country: 'Croatia',
            country_code: 'HR',
            airports: ['ZAG'],
            city_iata: ['ZAG'],
          },
        ],
      })),
    )

    const origins = await searchOrigins('zag')
    expect(fetch).toHaveBeenCalledWith('/api/origins?q=zag', expect.any(Object))
    expect(origins[0].id).toBe('zagreb-hr')
    expect(origins[0].city_iata).toEqual(['ZAG'])
  })

  it('propagates abort without returning mock results', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url, { signal }) => {
        if (signal?.aborted) {
          const error = new Error('Aborted')
          error.name = 'AbortError'
          throw error
        }
        return { ok: true, json: async () => [{ id: 'mock-origin' }] }
      }),
    )
    await expect(searchOrigins('zag', { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
  })

  it('rejects a non-array body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ id: 'zagreb-hr' }) })))
    await expect(searchOrigins('zag')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('fetchOrigin', () => {
  it('loads one origin by origin_id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        expect(url).toBe('/api/origins/zagreb-hr')
        return {
          ok: true,
          json: async () => ({ id: 'zagreb-hr', city: 'Zagreb', country: 'Croatia', country_code: 'HR' }),
        }
      }),
    )
    const origin = await fetchOrigin('zagreb-hr')
    expect(origin.id).toBe('zagreb-hr')
  })
})

describe('fetchCandidates', () => {
  it('requires origin_id, candidates[] and does not invent results on error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'Destination data is temporarily unavailable.' }),
      })),
    )
    await expect(fetchCandidates({ origin_id: 'zagreb-hr' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      message: 'Destination data is temporarily unavailable.',
    })
  })

  it('keeps candidates and rejected as separate collections', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          origin_id: 'zagreb-hr',
          data_source: 'cosmos://TravelPlaner/flights',
          candidates: [{ destination_id: 'ZAG-ROM-2026-09-18', city: 'Rome', price_eur: 65 }],
          rejected: [{ destination_id: 'ZAG-AGP-2026-09-18', reasons: [{ code: 'missing', message: 'no weather' }] }],
        }),
      })),
    )
    const payload = await fetchCandidates({ origin_id: 'zagreb-hr' })
    expect(payload.candidates).toHaveLength(1)
    expect(payload.rejected).toHaveLength(1)
    expect(payload.candidates[0].city).toBe('Rome')
  })
})

describe('fetchFlights', () => {
  it('returns flight documents for map and detail fields', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        expect(String(url)).toContain('/api/flights?origin_id=zagreb-hr')
        expect(String(url)).not.toContain('max_changeovers')
        return {
          ok: true,
          json: async () => ({
            origin_id: 'zagreb-hr',
            count: 1,
            data_source: 'cosmos://TravelPlaner/flights',
            flights: [{ id: 'ZAG-ROM-2026-09-18', latitude: 41.79, longitude: 12.25 }],
          }),
        }
      }),
    )
    const payload = await fetchFlights({ origin_id: 'zagreb-hr' })
    expect(payload.flights[0].id).toBe('ZAG-ROM-2026-09-18')
  })
})

const tripRequest = {
  origin: 'ZAG',
  departure_date: '2026-09-21',
  return_date: '2026-09-25',
  budget: 400,
  currency: 'EUR',
  moods: ['relaxing'],
  weather_preference: 'warm',
}

const readyRecommendation = {
  status: 'ready',
  request: tripRequest,
  updated_request: null,
  origin_id: 'zagreb-hr',
  origin: { id: 'zagreb-hr', city: 'Zagreb', country: 'Croatia', country_code: 'HR' },
  recommendations: [
    {
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
    },
  ],
  rejected: [],
  flights: [
    {
      id: 'ZAG-ROM-2026-09-18',
      destination_city: 'Rome',
      latitude: 41.79,
      longitude: 12.25,
    },
  ],
  issues: [],
  clarification_questions: [],
  data_source: 'cosmos://TravelPlaner/flights',
  ranking_preferences: {
    price_weight: 0.225,
    weather_weight: 0.3,
    changeovers_weight: 0.175,
    duration_weight: 0.125,
    precipitation_weight: 0.0875,
    sunshine_weight: 0.0875,
    temperature_direction: 'higher_is_better',
  },
}

describe('recommendTrip', () => {
  it('sends the explicit preserve flag with effective filter preferences', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
      expect(JSON.parse(options.body)).toMatchObject({
        text: '', ranking_preferences: readyRecommendation.ranking_preferences,
        preserve_ranking_preferences: true,
      })
      return { ok: true, json: async () => readyRecommendation }
    }))
    await recommendTrip({
      ranking_preferences: readyRecommendation.ranking_preferences,
      preserve_ranking_preferences: true,
    })
  })

  it.each(['recommend', 'refine'])('preserves all fallback metadata from %s', async (kind) => {
    const dates = {
      is_flexible_date_option: true,
      requested_departure_date: '2026-09-21', requested_return_date: '2026-09-25',
      actual_departure_date: '2026-09-22', actual_return_date: '2026-09-26',
    }
    const summary = { flexible_date_fallback_used: true, exact_match_count: 0, fallback_count: 1 }
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({
      ...readyRecommendation, ...summary,
      recommendations: [{ ...readyRecommendation.recommendations[0], ...dates }],
    }) })))
    const response = kind === 'recommend'
      ? await recommendTrip({})
      : await refineTrip({ text: 'Warmer', request: tripRequest })
    expect(response).toMatchObject(summary)
    expect(response.recommendations[0]).toMatchObject(dates)
  })

  it('POSTs JSON to /api/recommend using backend field names', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(url).toBe('/api/recommend')
        expect(options.method).toBe('POST')
        expect(options.headers['Content-Type']).toBe('application/json')
        expect(JSON.parse(options.body)).toEqual({
          text: 'Warm trip from ZAG',
          form_fields: { origin: 'ZAG', budget: 400, currency: 'EUR' },
        })
        return { ok: true, json: async () => readyRecommendation }
      }),
    )

    const payload = await recommendTrip({
      text: 'Warm trip from ZAG',
      form_fields: { origin: 'ZAG', budget: 400, currency: 'EUR' },
    })
    expect(payload.status).toBe('ready')
    expect(payload.request).toEqual(tripRequest)
    expect(payload.recommendations[0].city).toBe('Rome')
    expect(payload.flights[0].id).toBe('ZAG-ROM-2026-09-18')
    expect(payload.ranking_preferences.weather_weight).toBe(0.3)
  })

  it('keeps GET origin autocomplete working alongside POST', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        expect(String(url)).toContain('/api/origins?q=zag')
        return { ok: true, json: async () => [{ id: 'zagreb-hr', city: 'Zagreb' }] }
      }),
    )
    const origins = await searchOrigins('zag')
    expect(origins[0].id).toBe('zagreb-hr')
  })

  it('propagates abort without returning mock recommendations', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url, { signal }) => {
        if (signal?.aborted) {
          const error = new Error('Aborted')
          error.name = 'AbortError'
          throw error
        }
        return { ok: true, json: async () => readyRecommendation }
      }),
    )
    await expect(recommendTrip({ text: 'From ZAG' }, { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
  })

  it('surfaces backend error messages and empty non-JSON bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => {
          throw new Error('not json')
        },
      })),
    )
    await expect(recommendTrip({ text: 'From ZAG' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      message: 'Stored travel data is temporarily unavailable.',
    })
  })
})

describe('refineTrip', () => {
  it('POSTs the saved TripRequest and current ranking preferences to /api/refine', async () => {
    const rankingPreferences = {
      price_weight: 0.225,
      weather_weight: 0.3,
      changeovers_weight: 0.175,
      duration_weight: 0.125,
      precipitation_weight: 0.0875,
      sunshine_weight: 0.0875,
      temperature_direction: 'higher_is_better',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(url).toBe('/api/refine')
        expect(options.method).toBe('POST')
        expect(JSON.parse(options.body)).toEqual({
          text: 'Cheaper',
          request: tripRequest,
          ranking_preferences: rankingPreferences,
        })
        return {
          ok: true,
          json: async () => ({
            ...readyRecommendation,
            request: tripRequest,
            updated_request: { ...tripRequest, weather_preference: 'warm' },
          }),
        }
      }),
    )
    const payload = await refineTrip({
      text: 'Cheaper',
      request: tripRequest,
      ranking_preferences: rankingPreferences,
    })
    expect(payload.updated_request.origin).toBe('ZAG')
  })

  it('rejects refine without a saved request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(refineTrip({ text: 'Cheaper' })).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

const savedFlightItem = {
  flight_id: 'ZAG-ROM-2026-09-18',
  origin_id: 'zagreb-hr',
  saved_at: '2026-09-18T12:40:00Z',
  last_checked_at: '2026-09-18T12:40:00Z',
  saved_price: 65,
  last_checked_price: 65,
  price_changed: false,
  availability: 'available',
  flight: { id: 'ZAG-ROM-2026-09-18', destination_city: 'Rome', price_eur: 65 },
}

describe('saved flights API', () => {
  it('loads saved flights from GET /api/saved-flights', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(url).toBe('/api/saved-flights')
        expect(options.credentials).toBe('include')
        return { ok: true, json: async () => ({ items: [savedFlightItem] }) }
      }),
    )
    const payload = await fetchSavedFlights()
    expect(payload.items[0].flight_id).toBe('ZAG-ROM-2026-09-18')
  })

  it('saves a flight with only the flight id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(url).toBe('/api/saved-flights')
        expect(options.method).toBe('POST')
        expect(JSON.parse(options.body)).toEqual({
          flight_id: 'ZAG-ROM-2026-09-18',
        })
        return { ok: true, json: async () => savedFlightItem }
      }),
    )
    const payload = await saveFlight({
      flight_id: 'ZAG-ROM-2026-09-18',
      origin_id: 'zagreb-hr',
      price: 65,
    })
    expect(payload.flight_id).toBe('ZAG-ROM-2026-09-18')
  })

  it('saves the on-screen LLM summary with the flight id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(url).toBe('/api/saved-flights')
        expect(JSON.parse(options.body)).toEqual({
          flight_id: 'ZAG-ROM-2026-09-18',
          explanation: {
            summary: 'Rome stays within budget.',
            evidence: [{ statement: 'Fare is EUR 65 against a EUR 400 budget.' }],
          },
        })
        return { ok: true, json: async () => savedFlightItem }
      }),
    )
    const payload = await saveFlight({
      flight_id: 'ZAG-ROM-2026-09-18',
      explanation: {
        summary: 'Rome stays within budget.',
        evidence: [{ statement: 'Fare is EUR 65 against a EUR 400 budget.' }],
      },
    })
    expect(payload.flight_id).toBe('ZAG-ROM-2026-09-18')
  })

  it('unsaves through DELETE and accepts an empty success body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(url).toBe('/api/saved-flights/ZAG-ROM-2026-09-18')
        expect(options.method).toBe('DELETE')
        return { ok: true, status: 204, json: async () => { throw new Error('no body') } }
      }),
    )
    await expect(deleteSavedFlight('ZAG-ROM-2026-09-18')).resolves.toBeUndefined()
  })
})

describe('activities API', () => {
  it('posts mapped fields to /api/activities with credentials and limit 8', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(url).toBe('/api/activities')
        expect(options.method).toBe('POST')
        expect(options.credentials).toBe('include')
        expect(JSON.parse(options.body)).toEqual({
          city: 'Rome',
          country_code: 'IT',
          destination_id: 'ZAG-ROM-2026-09-18',
          moods: ['cultural'],
          limit: 8,
        })
        return {
          ok: true,
          json: async () => ({
            status: 'ready',
            city: 'Rome',
            destination_id: 'ZAG-ROM-2026-09-18',
            issues: [],
            activities: [
              {
                place_id: 'ChIJA',
                name: 'Colosseum',
                address: 'Rome, Italy',
                rating: 4.6,
                user_ratings_total: 1200,
                business_status: 'OPERATIONAL',
                price_level: 'PRICE_LEVEL_MODERATE',
                types: ['tourist_attraction'],
              },
            ],
          }),
        }
      }),
    )

    const payload = await fetchActivities({
      city: 'Rome',
      country_code: 'IT',
      destination_id: 'ZAG-ROM-2026-09-18',
      moods: ['cultural'],
      limit: 8,
    })
    expect(payload.status).toBe('ready')
    expect(payload.activities[0].name).toBe('Colosseum')
    expect(JSON.stringify(payload)).not.toMatch(/GOOGLE_PLACES_API_KEY/)
  })

  it('omits blank optional fields and keeps a ready empty list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url, options) => {
        expect(JSON.parse(options.body)).toEqual({
          city: 'Lisbon',
          moods: [],
          limit: 8,
        })
        return {
          ok: true,
          json: async () => ({
            status: 'ready',
            city: 'Lisbon',
            destination_id: null,
            activities: [],
            issues: [],
          }),
        }
      }),
    )
    await expect(fetchActivities({ city: 'Lisbon', moods: [] })).resolves.toMatchObject({
      status: 'ready',
      activities: [],
    })
  })

  it('surfaces HTTP failures instead of an empty success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'Activity data is temporarily unavailable.' }),
      })),
    )
    await expect(fetchActivities({ city: 'Rome' })).rejects.toMatchObject({
      status: 503,
      message: 'Activity data is temporarily unavailable.',
    })
  })

  it('rejects a 200 error status instead of rendering leftover cards', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          status: 'error',
          city: 'Rome',
          activities: [{ place_id: 'ChIJA', name: 'Colosseum' }],
          issues: ['Activity data is temporarily unavailable.'],
        }),
      })),
    )
    const payload = await fetchActivities({ city: 'Rome' })
    expect(payload.status).toBe('error')
    expect(payload.activities).toEqual([])
  })

  it('propagates abort without returning mock activities', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url, { signal }) => {
        if (signal?.aborted) {
          const error = new Error('Aborted')
          error.name = 'AbortError'
          throw error
        }
        return { ok: true, json: async () => ({ status: 'ready', activities: [{ name: 'mock' }] }) }
      }),
    )
    await expect(fetchActivities({ city: 'Rome' }, { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
  })
})

