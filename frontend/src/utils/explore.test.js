import { describe, expect, it, vi } from 'vitest'
import { activityLikeId } from './activityLikes'
import {
  activityPhotoUrl,
  createExploreSearch,
  exploreHeading,
  exploreSeedFromTrip,
  formatStraightLineDistance,
  locationErrorMessage,
  nearbyActivitiesPayload,
  normalizeNearbyActivity,
  straightLineKm,
} from './explore'

const colosseum = {
  place_id: 'ChIJA',
  name: 'Colosseum',
  types: ['tourist_attraction', 'point_of_interest'],
  address: 'Piazza del Colosseo, Rome',
  rating: 4.7,
  user_ratings_total: 1800,
  latitude: 41.8902,
  longitude: 12.4922,
  google_maps_uri: 'https://maps.google.com/?cid=123',
  photo: {
    name: 'places/ChIJA/photos/AbCd_123',
    author_attributions: [{ display_name: 'Ada Lovelace', uri: 'https://maps.google.com/maps/contrib/1' }],
    google_maps_uri: 'https://www.google.com/maps/place/photo',
  },
}

describe('explore search helpers', () => {
  it('labels a city and a device location differently', () => {
    expect(exploreHeading({ city: 'Rome' })).toBe('Activities near Rome')
    expect(exploreHeading({ source: 'device' })).toBe('Activities near your location')
    expect(exploreHeading({ source: 'device', city: 'Rome' })).toBe('Activities near your location')
  })

  it('seeds a selected trip without inventing coordinates', () => {
    expect(
      exploreSeedFromTrip({
        destination: { city: 'Rome', country_code: 'IT', latitude: 41.9, longitude: 12.5 },
      }),
    ).toEqual({
      city: 'Rome',
      countryCode: 'IT',
      centre: { source: 'trip', latitude: 41.9, longitude: 12.5 },
    })
    expect(exploreSeedFromTrip({ destination: { city: 'Lisbon' } })).toEqual({
      city: 'Lisbon',
      countryCode: '',
      centre: null,
    })
    expect(exploreSeedFromTrip({ destination: { latitude: 1, longitude: 2 } })).toBeNull()
  })

  it('sends coordinates without the city, and a city without coordinates', () => {
    expect(
      nearbyActivitiesPayload({
        city: 'Rome',
        countryCode: 'IT',
        latitude: 41.9,
        longitude: 12.5,
        types: ['museum'],
      }),
    ).toMatchObject({ latitude: 41.9, longitude: 12.5, included_types: ['museum'], radius_meters: 5000 })
    expect(
      nearbyActivitiesPayload({
        city: 'Rome',
        countryCode: 'IT',
        latitude: 41.9,
        longitude: 12.5,
      }).city,
    ).toBeUndefined()
    expect(nearbyActivitiesPayload({ city: '  Lisbon  ', countryCode: 'PT' })).toMatchObject({
      city: 'Lisbon',
      country_code: 'PT',
    })
    expect(nearbyActivitiesPayload({ city: '   ' })).toBeNull()
  })

  it('describes location permission failures and keeps a city fallback', () => {
    expect(locationErrorMessage({ code: 1 })).toContain('denied')
    expect(locationErrorMessage({ code: 1 })).toContain('Choose a city')
    expect(locationErrorMessage({ code: 3 })).toContain('timed out')
    expect(locationErrorMessage({ code: 2 })).toContain('unavailable')
  })

  it('uses the same place id as activity likes and ignores unsafe photos', () => {
    const normalized = normalizeNearbyActivity(colosseum)
    expect(normalized.place_id).toBe(activityLikeId('ChIJA'))
    expect(activityPhotoUrl(normalized.photo.name)).toBe(
      '/api/activities/photo?name=places%2FChIJA%2Fphotos%2FAbCd_123&max_height_px=400',
    )
    expect(activityPhotoUrl(normalized.photo.name)).not.toContain('key')
    expect(activityPhotoUrl('https://evil.example/a.jpg')).toBeNull()
    expect(normalizeNearbyActivity({ ...colosseum, photo: { name: 'not-a-photo' } }).photo).toBeNull()
    expect(normalizeNearbyActivity({ ...colosseum, rating: null, user_ratings_total: null }).rating).toBeNull()
  })

  it('keeps a provider editorial summary and drops a blank one', () => {
    const source = 'Iconic  amphitheatre in the centre of Rome.'
    expect(
      normalizeNearbyActivity({
        ...colosseum,
        description: source,
        description_language_code: 'en',
      }),
    ).toMatchObject({
      description: source,
      description_language_code: 'en',
    })
    expect(
      normalizeNearbyActivity({
        ...colosseum,
        description: '   ',
        description_language_code: 'en',
      }).description,
    ).toBeNull()
    expect(normalizeNearbyActivity(colosseum)).toMatchObject({
      description: null,
      description_language_code: null,
    })
  })

  it('shows straight-line distance only for valid coordinates', () => {
    const km = straightLineKm({ latitude: 41.9, longitude: 12.5 }, { latitude: 41.8902, longitude: 12.4922 })
    expect(formatStraightLineDistance(km)).toMatch(/straight line/)
    expect(formatStraightLineDistance(km)).not.toMatch(/walk|drive/i)
    expect(straightLineKm({ latitude: 41.9 }, { latitude: 41.89, longitude: 12.49 })).toBeNull()
    expect(straightLineKm({ latitude: 95, longitude: 12 }, colosseum)).toBeNull()
    expect(formatStraightLineDistance(null)).toBeNull()
  })

  it('ignores a stale nearby response after the centre changes', async () => {
    const pending = []
    const fetchNearby = vi.fn(() => new Promise((resolve) => pending.push(resolve)))
    const search = createExploreSearch({ fetchNearby })
    const updates = []
    const first = search.run({ city: 'Rome' }, (patch) => updates.push(patch))
    search.run({ city: 'Lisbon' }, (patch) => updates.push(patch))
    pending[0]({
      status: 'ready',
      activities: [{ place_id: 'rome', name: 'Colosseum' }],
      issues: [],
      radius_meters: 5000,
      search_center: null,
      attribution: 'Google Maps',
    })
    await first
    expect(updates.some((patch) => patch.activities?.some((item) => item.name === 'Colosseum'))).toBe(false)
    expect(updates.at(-1).status).toBe('loading')
    search.cancel()
  })
})
