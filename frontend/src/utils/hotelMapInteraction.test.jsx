// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TripDetailsContent from '../components/TripDetailsContent'
import TripDetailsDrawer from '../components/TripDetailsDrawer'
import DestinationMap from '../components/DestinationMap'
import { useHotelSelection } from './useHotelSelection'
import { useActivitySelection } from './useActivitySelection'
import { fetchActivities, fetchHotels } from '../services/travelApi'

vi.mock('../services/travelApi', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    fetchHotels: vi.fn(),
    fetchActivities: vi.fn(),
  }
})
const fake = vi.hoisted(() => ({ map: null, popups: new Map() }))
vi.mock('react-leaflet', async () => {
  const { forwardRef, useImperativeHandle, useRef } = await import('react')
  return {
  MapContainer: ({ children }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  Popup: ({ children }) => <span>{children}</span>,
  useMap: () => fake.map,
  Marker: forwardRef(function FakeMarker({ title, icon, position, children, eventHandlers }, ref) {
    const instance = useRef({ openPopup: vi.fn(), closePopup: vi.fn() })
    fake.popups.set(title || 'destination', instance.current)
    useImperativeHandle(ref, () => instance.current, [])
    return <div data-marker={title || 'destination'} data-position={JSON.stringify(position)}
      data-icon={icon?.options.className || 'primary'}>
      <button type="button" onClick={eventHandlers?.click}>Marker {title || 'destination'}</button>
      {children}
    </div>
  }),
  }
})

const trip = {
  id: 'offer-1', hotelDestinationId: 'rome-it', destination: { city: 'Rome', latitude: 41.8, longitude: 12.2 },
  flight: { price: 65, currency: 'EUR' },
}
const nextTrip = { ...trip, id: 'offer-2', hotelDestinationId: 'lisbon-pt',
  destination: { city: 'Lisbon', latitude: 38.7, longitude: -9.1 } }
const results = [trip, nextTrip]
const hotels = [
  { name: 'Hotel One', osm_id: 'node/1', distance_km: 0.1, latitude: 41.9, longitude: 12.5 },
  { name: 'Hotel Two', osm_id: 'node/2', distance_km: 0.2, latitude: 41.91, longitude: 12.51 },
  { name: 'Unmapped hotel', osm_id: 'node/3', distance_km: 0.3, latitude: null, longitude: null },
]

function Harness({ destination = trip, drawer = false }) {
  const selection = useHotelSelection(destination)
  const activitySelection = useActivitySelection(destination)
  const Details = drawer ? TripDetailsDrawer : TripDetailsContent
  return <>
    <Details destination={destination} titleId="details" activitiesEnabled hotelSelection={selection}
      activitySelection={activitySelection} onClose={() => {}} />
    <DestinationMap results={results} selectedId={destination?.id} viewportMode="selected"
      hotels={selection.hotels} selectedHotelId={selection.selectedHotelId}
      hotelFocusVersion={selection.focusVersion} onSelectHotel={selection.onSelectHotel}
      activities={activitySelection.activities} selectedActivityId={activitySelection.selectedActivityId}
      activityFocusVersion={activitySelection.focusVersion} onSelectActivity={activitySelection.onSelectActivity} />
  </>
}

let container, root
async function render(destination = trip) {
  await act(async () => { root.render(<Harness destination={destination} />) })
}
async function click(element) {
  expect(element).not.toBeNull()
  await act(async () => element.click())
}
function card(name) {
  return [...container.querySelectorAll('.trip-details-hotel-select')].find((node) => node.textContent.includes(name))
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  window.matchMedia = vi.fn(() => ({ matches: true }))
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  fake.popups.clear()
  fake.map = Object.fromEntries(['on', 'off', 'once', 'flyTo', 'setView', 'fitBounds', 'panTo', 'stop', 'invalidateSize']
    .map((key) => [key, vi.fn()]))
  fake.map.getContainer = () => container
  fake.map.getZoom = () => 10
  fetchHotels.mockReset().mockResolvedValue({ hotels, attribution: null })
  fetchActivities.mockReset().mockResolvedValue({ status: 'ready', activities: [{ place_id: 'activity', name: 'Museum' }] })
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
})

describe('Trip Details accordion and hotel map integration', () => {
  it('keeps keyboard focus on the selected hotel and skips collapsed content in the drawer', async () => {
    fetchActivities.mockRejectedValueOnce(new Error('Unavailable'))
    await act(async () => root.render(<Harness drawer />))
    const hotelButton = card('Hotel One')
    hotelButton.focus()
    await click(hotelButton)
    expect(document.activeElement).toBe(hotelButton)
    const close = [...container.querySelectorAll('button')].find((node) => node.textContent === 'Close')
    const activitiesToggle = [...container.querySelectorAll('.trip-details-section-toggle')]
      .find((node) => node.textContent === 'Activities')
    close.focus()
    await act(async () => close.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Tab', shiftKey: true, bubbles: true, cancelable: true,
    })))
    expect(document.activeElement).toBe(activitiesToggle)
  })

  it('toggles both sections accessibly without losing data, markers or issuing new requests', async () => {
    await render()
    const hotelToggle = container.querySelector('#details-hotels button')
    const activityToggle = container.querySelector('#details-activities button')
    expect(hotelToggle.getAttribute('aria-expanded')).toBe('true')
    expect(activityToggle.getAttribute('aria-expanded')).toBe('false')
    expect(activityToggle.getAttribute('aria-controls')).toBe('details-activities-content')
    const originalCard = card('Hotel One')
    await click(hotelToggle)
    expect(hotelToggle.getAttribute('aria-expanded')).toBe('false')
    expect(container.querySelector('#details-hotels-content').hidden).toBe(true)
    expect(container.querySelector('[data-marker="Hotel One"]')).not.toBeNull()
    await click(activityToggle)
    expect(activityToggle.getAttribute('aria-expanded')).toBe('true')
    expect(container.querySelector('#details-activities-content').hidden).toBe(false)
    expect(container.querySelector('#details-activities-content').textContent).toContain('Museum')
    await click(activityToggle)
    await click(hotelToggle)
    expect(card('Hotel One')).toBe(originalCard)
    expect(fetchHotels).toHaveBeenCalledTimes(1)
    expect(fetchActivities).toHaveBeenCalledTimes(1)
  })

  it('selects cards, zooms in to street level, opens popups and preserves primary markers', async () => {
    await render()
    expect(container.querySelectorAll('[data-icon="primary"]')).toHaveLength(2)
    expect(container.querySelector('[data-marker="Unmapped hotel"]')).toBeNull()
    const destinationFocusCount = fake.map.setView.mock.calls.length
    await click(card('Hotel One'))
    expect(card('Hotel One').getAttribute('aria-pressed')).toBe('true')
    expect(card('Hotel One').closest('li').classList.contains('is-selected')).toBe(true)
    expect(fake.map.setView).toHaveBeenLastCalledWith([41.9, 12.5], 16, { animate: false })
    expect(fake.popups.get('Hotel One').openPopup).toHaveBeenCalled()
    expect(container.querySelector('[data-marker="Hotel One"]').dataset.icon).toContain('is-selected')
    await click(card('Hotel Two'))
    expect(card('Hotel One').getAttribute('aria-pressed')).toBe('false')
    expect(card('Hotel Two').getAttribute('aria-pressed')).toBe('true')
    expect(fake.map.setView).toHaveBeenLastCalledWith([41.91, 12.51], 16, { animate: false })
    await click(card('Hotel Two'))
    expect(fake.map.setView).toHaveBeenCalledTimes(destinationFocusCount + 3)
    expect(fetchHotels).toHaveBeenCalledTimes(1)
  })

  it('zooms to an activity location and marks it selected', async () => {
    fetchActivities.mockResolvedValue({ status: 'ready', activities: [
      { place_id: 'colosseum', name: 'Colosseum', address: 'Piazza del Colosseo, Rome', latitude: 41.89, longitude: 12.49 },
      { place_id: 'nowhere', name: 'Unmapped museum' },
    ] })
    await render()
    expect(container.querySelector('[data-marker="Colosseum"]').dataset.icon).toBe('activity-map-marker')
    expect(container.querySelector('[data-marker="Unmapped museum"]')).toBeNull()
    await click(container.querySelector('#details-activities button'))
    const activityCard = [...container.querySelectorAll('#details-activities-content .trip-details-hotel-select')]
      .find((node) => node.textContent.includes('Colosseum'))
    await click(activityCard)
    expect(activityCard.getAttribute('aria-pressed')).toBe('true')
    expect(fake.map.setView).toHaveBeenLastCalledWith([41.89, 12.49], 16, { animate: false })
    expect(fake.popups.get('Colosseum').openPopup).toHaveBeenCalled()
    expect(container.querySelector('[data-marker="Colosseum"]').dataset.icon).toContain('is-selected')
    expect(container.textContent).toContain('Map location unavailable')
  })

  it('selects the matching card from a marker, including while Hotels is collapsed', async () => {
    await render()
    await click(container.querySelector('#details-hotels button'))
    await click(container.querySelector('[data-marker="Hotel Two"] button'))
    expect(card('Hotel Two').getAttribute('aria-pressed')).toBe('true')
    await click(container.querySelector('#details-hotels button'))
    expect(card('Hotel Two').closest('li').classList.contains('is-selected')).toBe(true)
  })

  it('focuses the map on the card under the reading line when scrolling settles', async () => {
    vi.useFakeTimers()
    try {
      await render()
      const scroller = document.createElement('div')
      container.parentElement.insertBefore(scroller, container)
      scroller.append(container)
      scroller.getBoundingClientRect = () => ({ top: 0, bottom: 500, height: 500 })
      const rects = { 'Hotel One': 100, 'Hotel Two': 230, 'Unmapped hotel': 200 }
      for (const [name, top] of Object.entries(rects)) {
        card(name).closest('li').getBoundingClientRect = () => ({ top, bottom: top + 60, height: 60 })
      }
      const destinationFocusCount = fake.map.setView.mock.calls.length
      await act(async () => {
        scroller.dispatchEvent(new Event('scroll'))
        vi.advanceTimersByTime(250)
      })
      // Hotel Two's centre (260) is nearest the 40% line (200); the unmapped card is skipped.
      expect(card('Hotel Two').getAttribute('aria-pressed')).toBe('true')
      expect(fake.map.setView).toHaveBeenLastCalledWith([41.91, 12.51], 16, { animate: false })
      await act(async () => {
        scroller.dispatchEvent(new Event('scroll'))
        vi.advanceTimersByTime(250)
      })
      // Settling on the already-selected card does not re-fly the map.
      expect(fake.map.setView).toHaveBeenCalledTimes(destinationFocusCount + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('selects an unmapped hotel without trying to move the map', async () => {
    await render()
    const destinationFocusCount = fake.map.setView.mock.calls.length
    await click(card('Unmapped hotel'))
    expect(card('Unmapped hotel').getAttribute('aria-pressed')).toBe('true')
    expect(fake.map.setView).toHaveBeenCalledTimes(destinationFocusCount)
    expect(container.textContent).toContain('65 EUR')
  })

  it('clears selection for a new offer with the same hotel destination without refetching', async () => {
    await render()
    await click(card('Hotel One'))
    await render({ ...trip, id: 'another-offer' })
    expect(card('Hotel One').getAttribute('aria-pressed')).toBe('false')
    expect(fetchHotels).toHaveBeenCalledTimes(1)
  })

  it('removes stale hotel markers on destination change and details close', async () => {
    await render()
    await click(card('Hotel One'))
    fetchHotels.mockResolvedValueOnce({ hotels: [], attribution: null })
    await render(nextTrip)
    expect(container.querySelector('[data-marker="Hotel One"]')).toBeNull()
    expect(container.querySelectorAll('[data-icon="primary"]')).toHaveLength(2)
    expect(container.textContent).toContain('No hotel recommendations available')
    await render(null)
    expect(container.querySelector('#details-hotels')).toBeNull()
    expect(container.querySelectorAll('[data-icon="primary"]')).toHaveLength(2)
  })

  it('creates no hotel markers or requests for a null hotel ID', async () => {
    await render({ ...trip, hotelDestinationId: null })
    expect(fetchHotels).not.toHaveBeenCalled()
    expect(container.querySelectorAll('[data-marker]')).toHaveLength(2)
  })

  it('keeps destination markers and Activities working after a hotel failure', async () => {
    fetchHotels.mockRejectedValueOnce(new Error('Unavailable'))
    await render()
    expect(container.querySelectorAll('[data-icon="primary"]')).toHaveLength(2)
    expect(container.textContent).toContain('Hotel recommendations are temporarily unavailable')
    await click(container.querySelector('#details-activities button'))
    expect(container.textContent).toContain('Museum')
    await click(container.querySelector('#details-hotels button'))
    await click(container.querySelector('#details-hotels button'))
    expect(container.querySelector('[role="alert"]')).not.toBeNull()
    expect(fetchHotels).toHaveBeenCalledTimes(1)
  })
})
