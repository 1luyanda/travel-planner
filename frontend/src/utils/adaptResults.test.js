import { describe, expect, it } from 'vitest'
import { adaptSearchResults, indexFlightsById, snapshotLabel } from './adaptResults'

const candidate = {
  destination_id: 'ZAG-ROM-2026-09-18',
  destination_iata: 'FCO',
  city: 'Rome',
  price_eur: 65,
  changeover_count: 0,
  flight_duration_minutes: 170,
  trip_duration_days: 4,
  average_max_temperature_c: 27.8,
  average_min_temperature_c: 18.75,
  precipitation_probability_percent: 13,
  sunshine_hours: 11.96,
  max_wind_speed_kmh: null,
  airport_distance_km: null,
  flight_retrieved_at: null,
  weather_retrieved_at: null,
}

const flight = {
  id: 'ZAG-ROM-2026-09-18',
  origin_id: 'zagreb-hr',
  origin_iata: 'ZAG',
  origin_airport: 'ZAG',
  destination_city: 'Rome',
  destination_country: 'Italy',
  destination_country_code: 'IT',
  destination_iata: 'ROM',
  destination_airport: 'FCO',
  airport_name: 'Leonardo da Vinci-Fiumicino Airport',
  price_eur: 65,
  currency: 'EUR',
  departure_at: '2026-09-21T15:55:00+02:00',
  outbound_stops: 0,
  duration_minutes: 170,
  airline_code: 'FR',
  latitude: 41.794594,
  longitude: 12.250346,
}

describe('indexFlightsById', () => {
  it('indexes unique flight ids and refuses duplicates', () => {
    const unique = indexFlightsById([flight])
    expect(unique.byId.get('ZAG-ROM-2026-09-18')).toBe(flight)
    expect(unique.duplicateIds).toEqual([])

    const unsafe = indexFlightsById([flight, { ...flight, latitude: 1 }])
    expect(unsafe.byId.has('ZAG-ROM-2026-09-18')).toBe(false)
    expect(unsafe.duplicateIds).toEqual(['ZAG-ROM-2026-09-18'])
  })
})

describe('adaptSearchResults', () => {
  it('joins on candidate.destination_id === flight.id and keeps origin_id apart from IATA', () => {
    const adapted = adaptSearchResults({
      candidatesResponse: {
        origin_id: 'zagreb-hr',
        data_source: 'cosmos://TravelPlaner/flights',
        candidates: [candidate],
        rejected: [{ destination_id: 'ZAG-AGP-2026-09-18', reasons: [] }],
      },
      flightsResponse: { origin_id: 'zagreb-hr', flights: [flight] },
      selectedOrigin: { originId: 'zagreb-hr', iata: 'ZAG' },
    })

    expect(adapted.originId).toBe('zagreb-hr')
    expect(adapted.rejected).toHaveLength(1)
    const row = adapted.results[0]
    expect(row.id).toBe('ZAG-ROM-2026-09-18')
    expect(row.originId).toBe('zagreb-hr')
    expect(row.originIata).toBe('ZAG')
    expect(row.destinationIata).toBe('FCO')
    expect(row.joinedFlight).toBe(true)
    expect(row.flight.price).toBe(65)
    expect(row.flight.airline_code).toBe('FR')
    expect(row.destination.latitude).toBe(41.794594)
    expect(row.destination.city).toBe('Rome')
    expect(row.country.common_name).toBe('Italy')
    expect(row.dataSource).toBe('cosmos://TravelPlaner/flights')
  })

  it('does not join by city name or invent coordinates when the id does not match', () => {
    const adapted = adaptSearchResults({
      candidatesResponse: {
        origin_id: 'zagreb-hr',
        candidates: [candidate],
        rejected: [],
      },
      flightsResponse: {
        flights: [{ ...flight, id: 'OTHER-ID', destination_city: 'Rome', latitude: 41.79, longitude: 12.25 }],
      },
    })
    const row = adapted.results[0]
    expect(row.joinedFlight).toBe(false)
    expect(row.destination.latitude).toBeNull()
    expect(row.destination.longitude).toBeNull()
    expect(row.flight.airline_code).toBeNull()
    expect(row.flight.price).toBe(65)
  })

  it('refuses unsafe joins when flight ids are duplicated', () => {
    const adapted = adaptSearchResults({
      candidatesResponse: { origin_id: 'zagreb-hr', candidates: [candidate], rejected: [] },
      flightsResponse: { flights: [flight, { ...flight, airline_code: 'OU' }] },
    })
    expect(adapted.results[0].joinedFlight).toBe(false)
    expect(adapted.results[0].joinUnsafe).toBe(true)
    expect(adapted.results[0].destination.latitude).toBeNull()
  })

  it('leaves missing optional fields null instead of fabricating them', () => {
    const adapted = adaptSearchResults({
      candidatesResponse: {
        origin_id: 'zagreb-hr',
        candidates: [
          {
            destination_id: 'ZAG-XYZ-1',
            destination_iata: 'XYZ',
            city: 'Unknownville',
            price_eur: 80,
            changeover_count: 1,
            flight_duration_minutes: 200,
            trip_duration_days: 3,
            average_max_temperature_c: 21,
            precipitation_probability_percent: 10,
          },
        ],
        rejected: [],
      },
    })
    const row = adapted.results[0]
    expect(row.flight.airline_code).toBeNull()
    expect(row.flight.departure_at).toBeNull()
    expect(row.destination.airport).toBeNull()
    expect(row.flightRetrievedAt).toBeNull()
    expect(row.photoUrl).toBeNull()
  })
})

describe('snapshotLabel', () => {
  it('uses a stored-data label without calling fares live', () => {
    expect(snapshotLabel('cosmos://TravelPlaner/flights')).toBe('Stored travel data')
    expect(snapshotLabel(null)).toBeNull()
  })
})
