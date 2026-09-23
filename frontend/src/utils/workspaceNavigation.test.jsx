// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { RouteProvider } from './routes.jsx'

const auth = vi.hoisted(() => ({
  user: { id: 'user-1', display_name: 'Luyanda' },
  loading: false,
  logout: vi.fn(),
}))

vi.mock('../auth/AuthProvider', async () => {
  const React = await import('react')
  return {
    AuthContext: React.createContext(null),
    useAuth: () => auth,
  }
})

vi.mock('../components/DestinationMap', () => ({
  default: () => null,
}))

vi.mock('../services/travelApi', async (importOriginal) => {
  const actual = await importOriginal()
  return {
  ...actual,
  deleteSavedFlight: vi.fn(),
  fetchFlights: vi.fn(async () => ({ origin_id: 'zagreb-hr', flights: [], count: 0 })),
  fetchHotels: vi.fn(async () => ({ destination_id: 'rome', hotels: [], attribution: null })),
  fetchActivities: vi.fn(async () => ({ status: 'ready', city: 'Rome', activities: [], issues: [] })),
  fetchNearbyActivities: vi.fn(async () => ({
    status: 'ready',
    activities: [],
    issues: [],
    radius_meters: 5000,
    search_center: null,
    attribution: 'Google Maps',
  })),
  fetchSavedFlights: vi.fn(async () => ({ items: [] })),
  recommendTrip: vi.fn(async () => ({
    status: 'ready',
    origin: {
      id: 'zagreb-hr',
      city: 'Zagreb',
      country: 'Croatia',
      country_code: 'HR',
      city_iata: ['ZAG'],
      airports: ['ZAG'],
    },
    request: {
      origin: 'ZAG',
      departure_date: '2026-10-12',
      return_date: '2026-10-16',
      budget: 400,
      currency: 'EUR',
    },
    recommendations: [
      {
        destination_id: 'ZAG-ROM-2026-09-18',
        destination_iata: 'FCO',
        city: 'Rome',
        rank: 1,
        price_eur: 65,
        summary: 'Rome stays within budget.',
        evidence: [],
      },
    ],
    flights: [
      {
        id: 'ZAG-ROM-2026-09-18',
        origin_iata: 'ZAG',
        destination_city: 'Rome',
        destination_country: 'Italy',
        destination_country_code: 'IT',
        latitude: 41.89,
        longitude: 12.49,
      },
    ],
    rejected: [],
  })),
  refineTrip: vi.fn(),
  saveFlight: vi.fn(),
  searchOrigins: vi.fn(async () => []),
  }
})

function clickLink(container, href) {
  const link = [...container.querySelectorAll('a')].find((item) => item.getAttribute('href') === href)
  link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
}

function setValue(element, value) {
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement
  Object.getOwnPropertyDescriptor(prototype.prototype, 'value').set.call(element, value)
  element.dispatchEvent(new Event('input', { bubbles: true }))
  element.dispatchEvent(new Event('change', { bubbles: true }))
}

describe('planner state across Explore', () => {
  let container
  let root

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    auth.user = { id: 'user-1', display_name: 'Luyanda' }
    auth.loading = false
    window.history.replaceState(null, '', '/planner')
  })

  async function mount(path = '/planner') {
    window.history.replaceState(null, '', path)
    window.matchMedia = vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root.render(
        <RouteProvider>
          <App />
        </RouteProvider>,
      )
    })
  }

  it('sends an unsigned Explore visit to login', async () => {
    auth.user = null
    await mount('/explore')
    expect(container.textContent).toContain('Log in')
    expect(window.location.pathname).toBe('/login')
  })

  it('keeps the planner conversation, draft, dates, origin and selected trip', async () => {
    await mount('/planner')
    expect(container.textContent).toContain('Where to today?')
    expect(container.textContent).toContain('Explore activities')
    expect(container.textContent).toContain('Plan a getaway')
    expect(container.textContent).not.toContain('Travel inspiration')
    expect(container.textContent).toContain('Plan a trip')

    const exploreActivities = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Explore activities')
    await act(async () => {
      exploreActivities.click()
    })
    expect(window.location.pathname).toBe('/explore')

    await act(async () => {
      clickLink(container, '/planner')
    })
    expect(window.location.pathname).toBe('/planner')
    expect(container.textContent).toContain('Where to today?')
    expect(container.querySelector('#trip-composer').value).toBe('')

    const composer = container.querySelector('#trip-composer')
    await act(async () => {
      setValue(composer, 'from ZAG 2026-10-12 2026-10-16 budget 400 EUR')
      composer.form.requestSubmit()
    })
    expect(container.textContent).toContain('Rome')

    const details = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Trip details')
    await act(async () => {
      details.click()
    })
    expect(container.textContent).toContain('Rome')

    const draft = container.querySelector('#trip-composer')
    await act(async () => {
      setValue(draft, 'keep this note')
    })
    expect(container.querySelector('#departure-date').value).toBe('2026-10-12')
    expect(container.querySelector('#return-date').value).toBe('2026-10-16')
    expect(container.querySelector('#flying-from').value).toContain('Zagreb')

    await act(async () => {
      clickLink(container, '/explore')
    })
    expect(window.location.pathname).toBe('/explore')
    expect(container.textContent).toContain('Activities near Rome')
    expect(container.textContent).not.toContain('Where to today?')
    expect(container.textContent).not.toContain('keep this note')
    expect(container.querySelector('a[href="/explore"]').getAttribute('aria-current')).toBe('page')

    await act(async () => {
      clickLink(container, '/planner')
    })
    expect(window.location.pathname).toBe('/planner')
    expect(container.querySelector('#trip-composer').value).toBe('keep this note')
    expect(container.querySelector('#departure-date').value).toBe('2026-10-12')
    expect(container.querySelector('#return-date').value).toBe('2026-10-16')
    expect(container.querySelector('#flying-from').value).toContain('Zagreb')
    expect(container.textContent).toContain('Rome')
    expect(container.textContent).toContain('Shortlist: Rome')
  })

  it('still clears the planner on New trip', async () => {
    await mount('/explore')
    await act(async () => {
      [...container.querySelectorAll('button')].find((button) => button.textContent.includes('New trip')).click()
    })
    expect(window.location.pathname).toBe('/planner')
    expect(container.textContent).toContain('Where to today?')
    expect(container.querySelector('#trip-composer').value).toBe('')
  })
})
