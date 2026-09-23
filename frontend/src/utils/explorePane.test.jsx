// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExplorePane, { ExploreView } from '../components/ExplorePane'
import { fetchNearbyActivities } from '../services/travelApi'

vi.mock('../services/travelApi', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    fetchNearbyActivities: vi.fn(),
  }
})

const colosseum = {
  place_id: 'ChIJA',
  name: 'Colosseum',
  types: ['tourist_attraction'],
  address: 'Piazza del Colosseo, Rome',
  rating: 4.7,
  user_ratings_total: 1800,
  latitude: 41.8902,
  longitude: 12.4922,
  google_maps_uri: 'https://maps.google.com/?cid=123',
  photo: {
    name: 'places/ChIJA/photos/AbCd_123',
    author_attributions: [
      {
        display_name: 'Ada Lovelace',
        uri: 'https://maps.google.com/maps/contrib/1',
        photo_uri: 'https://lh3.googleusercontent.com/author.jpg',
      },
    ],
  },
}

function renderView(results, extra = {}) {
  return renderToStaticMarkup(
    <ExploreView
      city="Rome"
      categoryId="activities"
      heading="Activities near Rome"
      onSearch={() => {}}
      onUseLocation={() => {}}
      canSearch
      results={results}
      likedIds={extra.likedIds || []}
      onToggleLike={() => {}}
      {...extra}
    />,
  )
}

describe('Explore view', () => {
  it('shows place facts, attribution, and a like control outside the maps link', () => {
    const html = renderView({
      status: 'ready',
      activities: [colosseum, { place_id: 'quiet', name: 'Quiet Square' }],
      attribution: 'Google Maps',
      radiusMeters: 5000,
      searchCenter: { latitude: 41.9, longitude: 12.5 },
    }, { likedIds: ['ChIJA'] })

    expect(html).toContain('Activities near Rome')
    expect(html).toContain('Colosseum')
    expect(html).toContain('Piazza del Colosseo, Rome')
    expect(html).toContain('Tourist attraction')
    expect(html).toContain('4.7')
    expect(html).toContain('1800 reviews')
    expect(html).toContain('straight line')
    expect(html).toContain('Photo: Ada Lovelace')
    expect(html).toContain('translate="no"')
    expect(html).toContain('Google Maps')
    expect(html).toContain('View on Google Maps')
    expect(html).toContain('aria-pressed="true"')
    expect(html).toContain('aria-label="Unlike Colosseum"')
    expect(html).toMatch(/<\/div><button type="button"[^>]*aria-pressed="true"/)
    expect(html).not.toContain('For you')
    expect(html).not.toContain('aria-label="List or map"')
    expect(html).toContain('Search within 5 km')
    expect(html).toContain('Quiet Square')
    expect(html).not.toContain('Quiet Square</h2><p>0')
  })

  it('uses the placeholder when a photo or coordinates are missing', () => {
    const html = renderView({
      status: 'ready',
      activities: [{ place_id: 'quiet', name: 'Quiet Square' }],
      attribution: 'Google Maps',
      searchCenter: null,
    })
    expect(html).toContain('aria-label="Quiet Square"')
    expect(html).not.toContain('/api/activities/photo')
    expect(html).not.toContain('straight line')
    expect(html).not.toContain('View on Google Maps')
  })

  it('shows idle, empty, and error states', () => {
    expect(renderView({ status: 'idle', activities: [] })).toContain('Choose a city or use your location, then search.')
    expect(renderView({ status: 'loading', activities: [] })).toContain('Searching for activities…')
    expect(renderView({ status: 'ready', activities: [], radiusMeters: 5000 })).toContain('No activities found within 5 km.')
    const error = renderView({ status: 'error', activities: [], error: 'Activity data is temporarily unavailable.' }, { onRetry: () => {} })
    expect(error).toContain('Activity data is temporarily unavailable.')
    expect(error).toContain('Retry')
    expect(renderView({ status: 'idle', activities: [] }, { locationError: 'Location permission was denied. Choose a city to search instead.' })).toContain(
      'Location permission was denied',
    )
  })
})

describe('Explore interactions', () => {
  let container
  let root

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  async function mount(props = {}) {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root.render(<ExplorePane {...props} />)
    })
  }

  it('does not search until the user submits, including after a category change', async () => {
    await mount({
      selectedTrip: { destination: { city: 'Rome', country_code: 'IT', latitude: 41.9, longitude: 12.5 } },
    })
    expect(container.textContent).toContain('Activities near Rome')
    expect(container.querySelector('#explore-city').value).toBe('Rome')
    expect(fetchNearbyActivities).not.toHaveBeenCalled()

    const select = container.querySelector('#explore-category')
    await act(async () => {
      select.value = 'museum'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(fetchNearbyActivities).not.toHaveBeenCalled()

    fetchNearbyActivities.mockResolvedValue({
      status: 'ready',
      city: null,
      radius_meters: 5000,
      search_center: { latitude: 41.9, longitude: 12.5 },
      activities: [colosseum],
      issues: [],
      attribution: 'Google Maps',
    })
    await act(async () => {
      container.querySelector('form').requestSubmit()
    })
    expect(fetchNearbyActivities).toHaveBeenCalledTimes(1)
    expect(fetchNearbyActivities.mock.calls[0][0]).toMatchObject({
      latitude: 41.9,
      longitude: 12.5,
      included_types: ['museum'],
    })
    expect(fetchNearbyActivities.mock.calls[0][0].city).toBeUndefined()
  })

  it('keeps a denied location from searching and offers the city field', async () => {
    const getCurrentPosition = vi.fn((_success, failure) => failure({ code: 1 }))
    navigator.geolocation = { getCurrentPosition }
    await mount()
    await act(async () => {
      [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Use my location')).click()
    })
    expect(container.textContent).toContain('Location permission was denied')
    expect(container.textContent).toContain('Choose a city')
    expect(fetchNearbyActivities).not.toHaveBeenCalled()
    expect(container.querySelector('#explore-city')).toBeTruthy()
  })
})
