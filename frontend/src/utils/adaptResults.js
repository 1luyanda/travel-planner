/**
 * Map FastAPI candidate + flight payloads onto the planner view model.
 * Only copies fields the APIs actually return. Missing values stay null.
 *
 * Join key: candidate.destination_id === flight.id
 * (ranking prepares destination_id from the Cosmos flight document id).
 * City name and list index are never used as join keys.
 */

function textOrNull(value) {
  if (value == null) return null
  const text = String(value).trim()
  return text ? text : null
}

function numberOrNull(value) {
  if (value == null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

export function indexFlightsById(flights = []) {
  const counts = new Map()
  const first = new Map()

  for (const flight of flights) {
    const id = textOrNull(flight?.id)
    if (!id) continue
    counts.set(id, (counts.get(id) || 0) + 1)
    if (!first.has(id)) first.set(id, flight)
  }

  const byId = new Map()
  const duplicateIds = []
  for (const [id, count] of counts) {
    if (count === 1) byId.set(id, first.get(id))
    else duplicateIds.push(id)
  }

  return { byId, duplicateIds }
}

function pickFlight(candidate, flightIndex) {
  const destinationId = textOrNull(candidate?.destination_id)
  if (!destinationId) return { flight: null, joined: false, unsafe: false }
  if (flightIndex.duplicateIds.includes(destinationId)) {
    return { flight: null, joined: false, unsafe: true }
  }
  const flight = flightIndex.byId.get(destinationId) || null
  return { flight, joined: Boolean(flight), unsafe: false }
}

function mapCandidate(candidate, originId, dataSource, flightIndex, selectedOrigin) {
  const { flight, joined, unsafe } = pickFlight(candidate, flightIndex)
  const destinationId = textOrNull(candidate?.destination_id)
  const originIata = textOrNull(flight?.origin_iata) || selectedOrigin?.iata || null

  return {
    id: destinationId,
    destinationId,
    destinationIata: textOrNull(candidate?.destination_iata),
    originId: textOrNull(originId),
    originIata,
    documentId: textOrNull(flight?.id),
    dataSource: textOrNull(dataSource),
    flightRetrievedAt: candidate?.flight_retrieved_at ?? null,
    weatherRetrievedAt: candidate?.weather_retrieved_at ?? null,
    photoUrl: textOrNull(flight?.photo_url) || textOrNull(candidate?.photo_url),
    photoUrlSmall: textOrNull(flight?.photo_url_small) || textOrNull(candidate?.photo_url_small),
    joinedFlight: joined,
    joinUnsafe: unsafe,
    flight: {
      origin_iata: originIata,
      origin_airport: textOrNull(flight?.origin_airport),
      destination_iata: textOrNull(flight?.destination_iata) || textOrNull(candidate?.destination_iata),
      destination_airport: textOrNull(flight?.destination_airport),
      price: numberOrNull(candidate?.price_eur),
      currency: textOrNull(flight?.currency) || (candidate?.price_eur != null ? 'EUR' : null),
      departure_at: textOrNull(flight?.departure_at),
      return_at: textOrNull(flight?.return_at),
      outbound_stops: numberOrNull(flight?.outbound_stops) ?? numberOrNull(candidate?.changeover_count),
      return_stops: numberOrNull(flight?.return_stops),
      duration_minutes: numberOrNull(candidate?.flight_duration_minutes) ?? numberOrNull(flight?.duration_minutes),
      airline_code: textOrNull(flight?.airline_code),
      airline_name: textOrNull(flight?.airline_name),
      flight_number: textOrNull(flight?.flight_number),
    },
    destination: {
      city: textOrNull(candidate?.city) || textOrNull(flight?.destination_city),
      airport: textOrNull(flight?.airport_name),
      country_code: textOrNull(flight?.destination_country_code),
      latitude: numberOrNull(flight?.latitude) ?? numberOrNull(candidate?.latitude),
      longitude: numberOrNull(flight?.longitude) ?? numberOrNull(candidate?.longitude),
    },
    weather: {
      average_max_temperature_c: numberOrNull(candidate?.average_max_temperature_c),
      average_min_temperature_c: numberOrNull(candidate?.average_min_temperature_c),
      average_precipitation_probability_percent: numberOrNull(candidate?.precipitation_probability_percent),
      average_sunshine_hours: numberOrNull(candidate?.sunshine_hours),
      average_max_wind_speed_kmh: numberOrNull(candidate?.max_wind_speed_kmh),
    },
    country: {
      common_name: textOrNull(flight?.destination_country),
    },
  }
}

export function adaptSearchResults({
  candidatesResponse,
  flightsResponse = null,
  selectedOrigin = null,
} = {}) {
  const originId = textOrNull(candidatesResponse?.origin_id)
  const dataSource = textOrNull(candidatesResponse?.data_source) || textOrNull(flightsResponse?.data_source)
  const flightIndex = indexFlightsById(flightsResponse?.flights)
  const candidates = Array.isArray(candidatesResponse?.candidates) ? candidatesResponse.candidates : []
  const rejected = Array.isArray(candidatesResponse?.rejected) ? candidatesResponse.rejected : []

  return {
    originId,
    dataSource,
    rejected,
    duplicateFlightIds: flightIndex.duplicateIds,
    results: candidates.map((candidate) =>
      mapCandidate(candidate, originId, dataSource, flightIndex, selectedOrigin),
    ),
  }
}

export function snapshotLabel(dataSource, timestamps = []) {
  if (!dataSource && !timestamps.some(Boolean)) return null
  const stored = dataSource ? 'Stored travel data' : 'Latest available snapshot'
  const times = timestamps.filter(Boolean)
  if (!times.length) return stored
  return `${stored} · ${times[0]}`
}
