import { describe, expect, it, vi, afterEach } from 'vitest'
import {
  ApiError,
  appendQuery,
  fetchCandidates,
  fetchFlights,
  fetchOrigin,
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
