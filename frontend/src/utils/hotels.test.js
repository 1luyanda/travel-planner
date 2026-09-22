import { describe, expect, it, vi } from 'vitest'
import { createHotelsLoader, formatHotelDistance, normalizeHotelsResponse, officialWebsite } from './hotels'

describe('hotel display data', () => {
  it('keeps backend order and full distance precision while dropping unused fields', () => {
    const data = normalizeHotelsResponse({
      destination_id: 'abu-simbel-eg', attribution: '© OpenStreetMap contributors',
      hotels: [
        { name: 'Zulu', distance_km: 0.1455, stars: null, website: null,
          booking_url: 'https://booking.example/never-display', address: 'Unused address', price: 100 },
        { name: 'Alpha', distance_km: 0.1456, stars: 4, website: 'https://hotel.example/' },
      ],
    })
    expect(data.hotels.map((item) => item.name)).toEqual(['Zulu', 'Alpha'])
    expect(data.hotels[0]).toEqual({ name: 'Zulu', distance_km: 0.1455, osm_id: null, stars: null, website: null,
      latitude: null, longitude: null })
    expect(formatHotelDistance(data.hotels[0].distance_km)).toBe('0.15 km')
    expect(data.hotels[0].distance_km).toBe(0.1455)
    expect(formatHotelDistance(0)).toBe('0.00 km')
    expect(data.attribution).toBe('© OpenStreetMap contributors')
  })

  it.each([null, '', 'javascript:alert(1)', 'data:text/html,hello', '//hotel.example', 'not a URL'])(
    'omits missing or unsafe official websites: %s', (value) => {
      expect(officialWebsite(value)).toBeNull()
    },
  )

  it.each(['https://hotel.example/', 'http://hotel.example/'])('accepts an official HTTP(S) link', (url) => {
    expect(officialWebsite(url)).toBe(url)
  })
})

describe('selected hotel loader', () => {
  it.each([null, undefined, '', '   '])('does not fetch without a hotel ID: %s', async (destinationId) => {
    const fetchHotels = vi.fn()
    const onChange = vi.fn()
    await createHotelsLoader({ fetchHotels }).run({ destinationId, onChange })
    expect(fetchHotels).not.toHaveBeenCalled()
    expect(onChange).toHaveBeenCalledWith({ status: 'unavailable', hotels: [], attribution: null })
  })

  it('requests only the supplied selected ID and exposes loading then empty success', async () => {
    const fetchHotels = vi.fn(async () => ({ hotels: [], attribution: null }))
    const changes = []
    await createHotelsLoader({ fetchHotels }).run({
      destinationId: 'selected-hotel-id', onChange: (state) => changes.push(state),
    })
    expect(fetchHotels).toHaveBeenCalledExactlyOnceWith('selected-hotel-id', { signal: expect.any(AbortSignal) })
    expect(changes.map((state) => state.status)).toEqual(['loading', 'ready'])
    expect(changes[1].hotels).toEqual([])
  })

  it('aborts and ignores the old destination when responses arrive out of order', async () => {
    const pending = {}
    const fetchHotels = (id, { signal }) => new Promise((resolve) => { pending[id] = { signal, resolve } })
    const loader = createHotelsLoader({ fetchHotels })
    const changes = []
    const onChange = (state) => changes.push(state)
    const first = loader.run({ destinationId: 'old', onChange })
    const second = loader.run({ destinationId: 'selected', onChange })
    expect(pending.old.signal.aborted).toBe(true)
    pending.selected.resolve({ hotels: [{ name: 'Selected hotel' }], attribution: null })
    await second
    pending.old.resolve({ hotels: [{ name: 'Stale hotel' }], attribution: null })
    await first
    expect(changes.at(-1).hotels).toEqual([{ name: 'Selected hotel' }])
    expect(changes.filter((state) => state.status === 'ready')).toHaveLength(1)
  })

  it('ignores pending results after details close', async () => {
    let resolveFetch
    let signal
    const loader = createHotelsLoader({ fetchHotels: (_id, options) => {
      signal = options.signal
      return new Promise((resolve) => { resolveFetch = resolve })
    } })
    const onChange = vi.fn()
    const pending = loader.run({ destinationId: 'rome-it', onChange })
    loader.cancel()
    resolveFetch({ hotels: [{ name: 'Late hotel' }] })
    await pending
    expect(signal.aborted).toBe(true)
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('isolates failure and permits retry', async () => {
    const fetchHotels = vi.fn().mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce({ hotels: [], attribution: null })
    const loader = createHotelsLoader({ fetchHotels })
    let state
    const request = { destinationId: 'rome-it', onChange: (next) => { state = next } }
    await loader.run(request)
    expect(state).toEqual({ status: 'error', hotels: [], attribution: null })
    await loader.run(request)
    expect(state.status).toBe('ready')
  })
})
