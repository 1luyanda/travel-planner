import { describe, expect, it } from 'vitest'
import {
  ACTIVITIES_LIMIT,
  activitiesPayloadFromDestination,
  activityErrorMessage,
  createActivitiesLoader,
  formatActivityBusinessStatus,
  formatActivityPriceLevel,
  formatActivityRating,
  normalizeActivitiesResponse,
  normalizeActivityItem,
  preserveEditorialText,
} from './activities'

const rome = {
  id: 'ZAG-ROM-2026-09-18',
  destination: { city: 'Rome', country_code: 'IT' },
}

function abortError() {
  const error = new Error('Aborted')
  error.name = 'AbortError'
  return error
}

describe('activitiesPayloadFromDestination', () => {
  it('maps city, country code, destination id, moods, and limit 8', () => {
    expect(activitiesPayloadFromDestination(rome, [' cultural ', '', 'relaxing'])).toEqual({
      city: 'Rome',
      country_code: 'IT',
      destination_id: 'ZAG-ROM-2026-09-18',
      moods: ['cultural', 'relaxing'],
      limit: ACTIVITIES_LIMIT,
    })
  })

  it('omits missing optional fields and does not invent a city', () => {
    expect(
      activitiesPayloadFromDestination({ destination: { city: '  Lisbon  ' } }, null),
    ).toEqual({
      city: 'Lisbon',
      moods: [],
      limit: 8,
    })
    expect(activitiesPayloadFromDestination({ id: 'x', destination: {} }, ['outdoors'])).toBeNull()
    expect(activitiesPayloadFromDestination(null, ['outdoors'])).toBeNull()
  })
})

describe('normalizeActivitiesResponse', () => {
  it('keeps valid optional zeros and drops incomplete cards', () => {
    const normalized = normalizeActivitiesResponse({
      status: 'ready',
      city: 'Rome',
      destination_id: 'ZAG-ROM-2026-09-18',
      issues: [],
      activities: [
        {
          place_id: 'ChIJA',
          name: 'Colosseum',
          address: 'Rome, Italy',
          rating: 0,
          user_ratings_total: 0,
          business_status: 'OPERATIONAL',
          price_level: 'PRICE_LEVEL_MODERATE',
          types: ['tourist_attraction'],
        },
        { place_id: '', name: 'Missing id' },
        { name: 'Missing place' },
      ],
    })
    expect(normalized.activities).toEqual([
      {
        place_id: 'ChIJA',
        name: 'Colosseum',
        types: ['tourist_attraction'],
        address: 'Rome, Italy',
        rating: 0,
        user_ratings_total: 0,
        business_status: 'OPERATIONAL',
        price_level: 'PRICE_LEVEL_MODERATE',
        description: null,
        description_language_code: null,
        latitude: null,
        longitude: null,
      },
    ])
  })

  it('does not treat an error payload as an empty success', () => {
    const normalized = normalizeActivitiesResponse({
      status: 'error',
      city: 'Rome',
      destination_id: 'ZAG-ROM-2026-09-18',
      activities: [{ place_id: 'ChIJA', name: 'Colosseum' }],
      issues: ['Activity data is temporarily unavailable.'],
    })
    expect(normalized.status).toBe('error')
    expect(normalized.activities).toEqual([])
    expect(activityErrorMessage(normalized)).toBe('Activity data is temporarily unavailable.')
    expect(normalizeActivitiesResponse({ status: 'needs_input' })).toBeNull()
  })
})

describe('activity display helpers', () => {
  it('labels price level without inventing a monetary price', () => {
    expect(formatActivityPriceLevel('PRICE_LEVEL_MODERATE')).toBe('Moderate')
    expect(formatActivityPriceLevel(null)).toBeNull()
    expect(formatActivityBusinessStatus('OPERATIONAL')).toBe('Operational')
    expect(formatActivityBusinessStatus('CLOSED_TEMPORARILY')).toBe('Temporarily closed')
    expect(formatActivityRating(0, 0)).toBe('0 · 0 reviews')
    expect(formatActivityRating(4.6, 1)).toBe('4.6 · 1 review')
    expect(normalizeActivityItem({ place_id: 'id', name: 'Park', rating: null })).toMatchObject({
      rating: null,
      address: null,
      description: null,
      description_language_code: null,
    })
    const editorial = 'Iconic amphitheatre in the centre of Rome.'
    expect(
      normalizeActivityItem({
        place_id: 'ChIJA',
        name: 'Colosseum',
        description: editorial,
        description_language_code: 'en',
      }),
    ).toMatchObject({
      description: editorial,
      description_language_code: 'en',
    })
    expect(preserveEditorialText(editorial)).toBe(editorial)
    expect(preserveEditorialText('   ')).toBeNull()
    expect(preserveEditorialText(null)).toBeNull()
  })
})

describe('createActivitiesLoader', () => {
  it('does not fetch before details are open or from a hidden container', async () => {
    const fetchActivities = async () => {
      throw new Error('should not fetch')
    }
    const changes = []
    const loader = createActivitiesLoader({ fetchActivities })

    await loader.run({
      payload: activitiesPayloadFromDestination(rome, []),
      enabled: false,
      onChange: (value) => changes.push(value),
    })
    await loader.run({
      payload: null,
      enabled: true,
      onChange: (value) => changes.push(value),
    })

    expect(changes).toEqual([
      { status: 'idle', activities: [], error: '' },
      { status: 'unavailable', activities: [], error: '' },
    ])
  })

  it('does not let a hidden desktop or mobile surface issue a second request', async () => {
    const calls = []
    const fetchActivities = async (payload) => {
      calls.push(payload.city)
      return { status: 'ready', city: payload.city, activities: [], issues: [] }
    }
    const payload = activitiesPayloadFromDestination(rome, [])
    const desktop = createActivitiesLoader({ fetchActivities })
    const mobile = createActivitiesLoader({ fetchActivities })

    await Promise.all([
      desktop.run({ payload, enabled: true, onChange: () => {} }),
      mobile.run({ payload, enabled: false, onChange: () => {} }),
    ])

    expect(calls).toEqual(['Rome'])
  })

  it('keeps the later destination when responses arrive out of order', async () => {
    const deferred = {}
    const fetchActivities = (payload) =>
      new Promise((resolve, reject) => {
        deferred[payload.city] = { resolve, reject }
      })
    let latest = null
    const loader = createActivitiesLoader({ fetchActivities })
    const romePayload = activitiesPayloadFromDestination(rome, [])
    const lisbonPayload = activitiesPayloadFromDestination(
      { id: 'ZAG-LIS', destination: { city: 'Lisbon', country_code: 'PT' } },
      [],
    )

    const first = loader.run({
      payload: romePayload,
      enabled: true,
      onChange: (value) => {
        latest = value
      },
    })
    const second = loader.run({
      payload: lisbonPayload,
      enabled: true,
      onChange: (value) => {
        latest = value
      },
    })

    deferred.Rome.resolve({
      status: 'ready',
      activities: [{ place_id: 'rome', name: 'Colosseum' }],
    })
    deferred.Lisbon.resolve({
      status: 'ready',
      activities: [{ place_id: 'lisbon', name: 'Belem' }],
    })
    await Promise.allSettled([first, second])

    expect(latest).toEqual({
      status: 'ready',
      activities: [{ place_id: 'lisbon', name: 'Belem' }],
      error: '',
    })
  })

  it('ignores a pending result after details close', async () => {
    let resolveFetch
    const fetchActivities = (_payload, { signal } = {}) =>
      new Promise((resolve, reject) => {
        signal?.addEventListener('abort', () => reject(abortError()), { once: true })
        resolveFetch = resolve
      })
    let latest = { status: 'loading', activities: [], error: '' }
    const loader = createActivitiesLoader({ fetchActivities })
    const pending = loader.run({
      payload: activitiesPayloadFromDestination(rome, []),
      enabled: true,
      onChange: (value) => {
        latest = value
      },
    })

    loader.cancel()
    resolveFetch({
      status: 'ready',
      activities: [{ place_id: 'rome', name: 'Colosseum' }],
    })
    await pending

    expect(latest.status).toBe('loading')
    expect(latest.activities).toEqual([])
  })

  it('treats a ready empty list as empty success and an error status as failure', async () => {
    const changes = []
    const emptyLoader = createActivitiesLoader({
      fetchActivities: async () => ({ status: 'ready', city: 'Rome', activities: [], issues: [] }),
    })
    await emptyLoader.run({
      payload: activitiesPayloadFromDestination(rome, []),
      enabled: true,
      onChange: (value) => changes.push(value.status),
    })

    const errorLoader = createActivitiesLoader({
      fetchActivities: async () => ({
        status: 'error',
        city: 'Rome',
        activities: [{ place_id: 'x', name: 'Hidden' }],
        issues: ['Activity data is temporarily unavailable.'],
      }),
    })
    let errorState
    await errorLoader.run({
      payload: activitiesPayloadFromDestination(rome, []),
      enabled: true,
      onChange: (value) => {
        errorState = value
      },
    })

    expect(changes).toEqual(['loading', 'ready'])
    expect(errorState).toEqual({
      status: 'error',
      activities: [],
      error: 'Activity data is temporarily unavailable.',
    })
  })
})
