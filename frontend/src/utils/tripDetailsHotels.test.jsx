import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { TripDetailsHotelsView } from '../components/TripDetailsHotels'
import TripDetailsContent from '../components/TripDetailsContent'
import { createHotelsLoader } from './hotels'
import { fetchHotels } from '../services/travelApi'

// Node tests render static markup, so provide the real loader's settled state
// at the component boundary when verifying failure isolation in the parent.
const settled = vi.hoisted(() => ({ state: null }))
vi.mock('../components/TripDetailsHotels', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    default: (props) => settled.state
      ? <actual.TripDetailsHotelsView titleId={props.titleId} state={settled.state} />
      : <actual.default {...props} />,
  }
})
afterEach(() => {
  settled.state = null
  vi.unstubAllGlobals()
})

const hotel = { name: 'Hllol', distance_km: 0.1455, stars: null, website: null }
const renderHotels = (state) => renderToStaticMarkup(
  <TripDetailsHotelsView titleId="details" state={state} onRetry={() => {}} />,
)

describe('Trip Details hotels', () => {
  it('renders name and approximate distance without nullable metadata or booking data', () => {
    const html = renderHotels({ status: 'ready', hotels: [{ ...hotel,
      booking_url: 'https://booking.example/hidden', address: null,
    }] })
    expect(html).toContain('Hllol')
    expect(html).toContain('Approx. 0.15 km from destination centre')
    expect(html).not.toContain('stars')
    expect(html).not.toContain('Official website')
    expect(html).not.toContain('<a ')
    expect(html).not.toMatch(/booking|availability|price/i)
  })

  it('renders known stars and official website safely, in unchanged order', () => {
    const html = renderHotels({ status: 'ready', attribution: '© OpenStreetMap contributors', hotels: [
      { ...hotel, name: 'Zulu', stars: 4, website: 'https://hotel.example/' },
      { ...hotel, name: 'Alpha' },
    ] })
    expect(html).toContain('4 stars')
    expect(html).toContain('href="https://hotel.example/" target="_blank" rel="noopener noreferrer"')
    expect(html).toContain('Official website')
    expect(html.indexOf('Zulu')).toBeLessThan(html.indexOf('Alpha'))
    expect(html.match(/Official website/g)).toHaveLength(1)
    expect(html).toContain('© OpenStreetMap contributors')
  })

  it('does not render unsafe website protocols', () => {
    expect(renderHotels({ status: 'ready', hotels: [{ ...hotel, website: 'javascript:alert(1)' }] }))
      .not.toContain('<a ')
  })

  it('shows loading, empty, unavailable and recoverable error states', () => {
    expect(renderHotels({ status: 'loading', hotels: [] })).toContain('Loading hotels...')
    for (const status of ['ready', 'unavailable']) {
      expect(renderHotels({ status, hotels: [] })).toContain('No hotel recommendations available for this destination.')
    }
    const html = renderHotels({ status: 'error', hotels: [hotel] })
    expect(html).toContain('Hotel recommendations are temporarily unavailable.')
    expect(html).toContain('role="alert"')
    expect(html).toContain('Retry')
    expect(html).not.toContain('Hllol')
  })

  it.each(['rome-it', null])('places Hotels above Activities while other trip details render: %s', (hotelDestinationId) => {
    const html = renderToStaticMarkup(<TripDetailsContent titleId="details" activitiesEnabled destination={{
      id: 'offer-1', hotelDestinationId, destination: { city: 'Rome' },
      flight: { price: 65, currency: 'EUR' }, weather: {}, scores: { total: 0.8 },
    }} />)
    expect(html).toContain('65 EUR')
    expect(html).toContain('id="details-hotels"')
    expect(html).toContain('id="details-activities"')
    expect(html.indexOf('id="details-hotels"')).toBeLessThan(html.indexOf('id="details-activities"'))
    expect(html).toContain(hotelDestinationId ? 'Loading hotels...' : 'No hotel recommendations available')
  })

  it('renders no hotel section without a selected trip', () => {
    expect(renderToStaticMarkup(<TripDetailsContent destination={null} titleId="details" />)).toBe('')
  })

  it('keeps flight details and Activities visible after the hotel API fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 503, json: async () => ({ detail: 'Hotel data is temporarily unavailable.' }),
    })))
    await createHotelsLoader({ fetchHotels }).run({
      destinationId: 'rome-it', onChange: (state) => { settled.state = state },
    })
    expect(settled.state.status).toBe('error')
    const html = renderToStaticMarkup(<TripDetailsContent titleId="details" activitiesEnabled destination={{
      id: 'offer-1', hotelDestinationId: 'rome-it', destination: { city: 'Rome' },
      flight: { price: 65, currency: 'EUR' },
    }} />)
    expect(html).toContain('Hotel recommendations are temporarily unavailable.')
    expect(html).toContain('65 EUR')
    expect(html).toContain('id="details-activities"')
    expect(html.indexOf('id="details-hotels"')).toBeLessThan(html.indexOf('id="details-activities"'))
  })
})
