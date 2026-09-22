// @vitest-environment jsdom
import { act, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SavedPane from '../components/SavedPane'
import TripDetailsContent from '../components/TripDetailsContent'
import { deleteSavedFlight, fetchSavedFlights, saveFlight } from '../services/travelApi'
import { adaptRecommendations } from './adaptRecommendations'
import { adaptSavedFlight, adaptSavedFlights, flightReferenceFromDestination } from './savedFlights'
import { readSavedHotelIds, rememberSavedHotelId } from './savedHotelMetadata'

const userId = 'user-1'
const flight = { id: 'offer-1', destination_city: 'Rome', destination_country_code: 'IT',
  price_eur: 65, currency: 'EUR', latitude: 41.9, longitude: 12.5 }
const savedItem = { flight_id: flight.id, availability: 'available', flight }
const recommendation = { destination_id: flight.id, city: 'Rome', rank: 1, final_score: 0.9,
  hotel_destination_id: 'actual-hotel-document-id', price_eur: 65 }
function exploreTrip() {
  return adaptRecommendations({ recommendations: [recommendation], flights: [flight] }).results[0]
}
function saveFromExplore(destination = exploreTrip(), account = userId) {
  return saveFlight({ ...flightReferenceFromDestination(destination), hotelDestinationId: destination.hotelDestinationId },
    { userId: account })
}
function SavedView({ destinations }) {
  const [selected, setSelected] = useState(null)
  return <>
    <SavedPane destinations={destinations} savedIds={destinations.map((item) => item.id)}
      onViewDetails={setSelected} />
    <TripDetailsContent destination={selected} titleId="saved-details" />
  </>
}

let container, root, fetchMock
const ok = (data) => ({ ok: true, status: 200, json: async () => data })
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  localStorage.clear()
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  fetchMock = vi.fn(async (url, options) => {
    if (url === '/api/saved-flights') {
      return ok(options.method === 'POST' ? savedItem : { items: [savedItem] })
    }
    if (url === '/api/saved-flights/offer-1' && options.method === 'DELETE') return { ok: true, status: 204 }
    if (url === '/api/hotels?destination_id=actual-hotel-document-id&limit=5') return ok({
      destination_id: 'actual-hotel-document-id', hotels: [
        { name: 'Zulu', osm_id: 'node/1', distance_km: 0.1455, latitude: 41.9, longitude: 12.5, stars: null },
        { name: 'Alpha', osm_id: 'node/2', distance_km: 0.1456, latitude: 41.91, longitude: 12.51, stars: 4 },
      ],
    })
    throw new Error(`Unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('saved hotel lookup persistence', () => {
  it('saves only the backend lookup ID locally after a successful flight save', async () => {
    const result = await saveFromExplore()
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ flight_id: 'offer-1' })
    expect(fetchMock.mock.calls[0][1].credentials).toBe('include')
    expect(adaptSavedFlight(result).hotelDestinationId).toBe('actual-hotel-document-id')
    expect(readSavedHotelIds(userId)).toEqual({ 'offer-1': 'actual-hotel-document-id' })
    expect(localStorage.length).toBe(1)
    expect(JSON.parse(localStorage.getItem(localStorage.key(0))))
      .toEqual({ 'offer-1': 'actual-hotel-document-id' })
  })

  it('restores metadata from serialized storage without the Explore recommendation', async () => {
    await saveFromExplore()
    const key = localStorage.key(0)
    const serialized = localStorage.getItem(key)
    localStorage.clear()
    localStorage.setItem(key, serialized)
    const [restored] = adaptSavedFlights(await fetchSavedFlights({ userId }))
    expect(restored.hotelDestinationId).toBe('actual-hotel-document-id')
    expect(restored.id).toBe('offer-1')
    expect(restored.flight.price).toBe(65)
    expect(restored.scores).toEqual({})
  })

  it('reopens Saved details through the existing fetch flow with the same hotel order as Explore', async () => {
    await saveFromExplore()
    const restored = adaptSavedFlights(await fetchSavedFlights({ userId }))
    await act(async () => root.render(<SavedView destinations={restored} />))
    expect(fetchMock.mock.calls.filter(([url]) => url.startsWith('/api/hotels'))).toHaveLength(0)
    const details = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Trip details')
    await act(async () => details.click())
    const names = () => [...container.querySelectorAll('.trip-details-hotel-select .trip-details-activity-name')]
      .map((node) => node.textContent)
    expect(names()).toEqual(['Zulu', 'Alpha'])
    expect(container.textContent).toContain('0.15 km from destination centre')
    await act(async () => root.render(<TripDetailsContent destination={exploreTrip()} titleId="explore-details" />))
    expect(names()).toEqual(['Zulu', 'Alpha'])
    const requests = fetchMock.mock.calls.filter(([url]) => url.startsWith('/api/hotels'))
    expect(requests.map(([url]) => url)).toEqual([
      '/api/hotels?destination_id=actual-hotel-document-id&limit=5',
      '/api/hotels?destination_id=actual-hotel-document-id&limit=5',
    ])
  })

  it('keeps legacy saved items usable without inventing a lookup ID', async () => {
    const [legacy] = adaptSavedFlights(await fetchSavedFlights({ userId }))
    expect(legacy.hotelDestinationId).toBeNull()
    await act(async () => root.render(<TripDetailsContent destination={legacy} titleId="legacy" />))
    expect(container.textContent).toContain('No hotel recommendations available for this destination.')
    expect(container.textContent).toContain('65 EUR')
    expect(fetchMock.mock.calls.filter(([url]) => url.startsWith('/api/hotels'))).toHaveLength(0)
  })

  it('isolates hotel metadata between accounts and anonymous reads', async () => {
    await saveFromExplore()
    for (const account of ['another-user', undefined]) {
      expect(adaptSavedFlights(await fetchSavedFlights({ userId: account }))[0].hotelDestinationId).toBeNull()
    }
    expect(readSavedHotelIds(userId)['offer-1']).toBe('actual-hotel-document-id')
  })

  it('does not persist metadata for a failed save', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'Unavailable' }) })
    await expect(saveFromExplore()).rejects.toMatchObject({ status: 503 })
    expect(readSavedHotelIds(userId)).toEqual({})
  })

  it('retains metadata on failed removal and deletes it only after success', async () => {
    await saveFromExplore()
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'Unavailable' }) })
    await expect(deleteSavedFlight('offer-1', { userId })).rejects.toMatchObject({ status: 503 })
    expect(readSavedHotelIds(userId)['offer-1']).toBe('actual-hotel-document-id')
    await deleteSavedFlight('offer-1', { userId })
    expect(readSavedHotelIds(userId)).toEqual({})
  })

  it('ignores invalid metadata and never serializes null or invented IDs', async () => {
    rememberSavedHotelId(userId, 'offer-1', null)
    expect(localStorage.length).toBe(0)
    await saveFromExplore()
    const key = localStorage.key(0)
    for (const corrupt of ['invalid json', '[]', '{"offer-1":42}', '{"offer-1":""}']) {
      localStorage.setItem(key, corrupt)
      expect(readSavedHotelIds(userId)).toEqual({})
    }
  })

  it('handles disabled storage and preserves the immediate save response ID', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Disabled') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Disabled') })
    expect(adaptSavedFlight(await saveFromExplore()).hotelDestinationId).toBe('actual-hotel-document-id')
    expect(adaptSavedFlights(await fetchSavedFlights({ userId }))[0].hotelDestinationId).toBeNull()
  })
})
