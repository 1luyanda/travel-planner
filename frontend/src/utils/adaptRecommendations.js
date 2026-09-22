/**
 * Map POST /api/recommend and /api/refine payloads onto the planner view model.
 * Preserves server order. Does not rank, filter, or invent explanation/fare facts.
 *
 * Flight display fields come from the recommend/refine payload. Optional extra
 * flights are joined on destination_id === flight.id only.
 */

import { indexFlightsById } from './adaptResults'

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

function pickFlight(destinationId, flightIndex) {
  const id = textOrNull(destinationId)
  if (!id || !flightIndex) return { flight: null, joined: false, unsafe: false }
  if (flightIndex.duplicateIds.includes(id)) {
    return { flight: null, joined: false, unsafe: true }
  }
  const flight = flightIndex.byId.get(id) || null
  return { flight, joined: Boolean(flight), unsafe: false }
}

function flightWeather(item, flight) {
  return {
    average_max_temperature_c:
      numberOrNull(item?.average_max_temperature_c) ?? numberOrNull(flight?.temp_max_c),
    average_min_temperature_c:
      numberOrNull(flight?.temp_min_c) ?? numberOrNull(flight?.average_min_temperature_c),
    average_precipitation_probability_percent:
      numberOrNull(flight?.rain_pct) ??
      numberOrNull(flight?.average_precipitation_probability_percent),
    average_sunshine_hours:
      numberOrNull(flight?.sunshine_hours) ?? numberOrNull(flight?.average_sunshine_hours),
    average_max_wind_speed_kmh: numberOrNull(flight?.average_max_wind_speed_kmh),
  }
}

function mapRecommendation(item, { originId, originIata, originCity, originCountry, dataSource, flightIndex }) {
  const destinationId = textOrNull(item?.destination_id)
  const { flight, joined, unsafe } = pickFlight(destinationId, flightIndex)
  const joinedOriginIata = textOrNull(flight?.origin_iata) || originIata
  const price = numberOrNull(item?.price_eur)
  const rank = numberOrNull(item?.rank)

  return {
    id: destinationId,
    destinationId,
    hotelDestinationId: typeof item?.hotel_destination_id === 'string' && item.hotel_destination_id.trim()
      ? item.hotel_destination_id : null,
    destinationIata: textOrNull(item?.destination_iata),
    originId: textOrNull(originId),
    originIata: joinedOriginIata,
    originCity,
    originCountry,
    documentId: textOrNull(flight?.id) || destinationId,
    dataSource: textOrNull(dataSource),
    photoUrl: textOrNull(flight?.photo_url),
    photoUrlSmall: textOrNull(flight?.photo_url_small),
    joinedFlight: joined,
    joinUnsafe: unsafe,
    tripDurationDays: numberOrNull(item?.trip_duration_days),
    rank: rank != null && rank >= 1 ? rank : null,
    temperatureDirection: textOrNull(item?.temperature_direction),
    isFlexibleDateOption: item?.is_flexible_date_option === true,
    requestedDepartureDate: textOrNull(item?.requested_departure_date),
    requestedReturnDate: textOrNull(item?.requested_return_date),
    actualDepartureDate: textOrNull(item?.actual_departure_date),
    actualReturnDate: textOrNull(item?.actual_return_date),
    scores: {
      price: numberOrNull(item?.price_score),
      weather: numberOrNull(item?.weather_score),
      precipitation: numberOrNull(item?.precipitation_score),
      sunshine: numberOrNull(item?.sunshine_score),
      stops: numberOrNull(item?.stops_score),
      duration: numberOrNull(item?.duration_score),
      total: numberOrNull(item?.final_score),
    },
    explanation: {
      summary: textOrNull(item?.summary),
      evidence: Array.isArray(item?.evidence) ? item.evidence : [],
      issues: Array.isArray(item?.issues) ? item.issues : [],
    },
    flight: {
      origin_iata: joinedOriginIata,
      origin_airport: textOrNull(flight?.origin_airport),
      destination_iata: textOrNull(flight?.destination_iata) || textOrNull(item?.destination_iata),
      destination_airport: textOrNull(flight?.destination_airport),
      price,
      currency: price != null ? 'EUR' : null,
      departure_at: textOrNull(flight?.departure_at),
      return_at: textOrNull(flight?.return_at),
      outbound_stops: numberOrNull(item?.changeover_count) ?? numberOrNull(flight?.outbound_stops),
      return_stops: numberOrNull(flight?.return_stops),
      duration_minutes:
        numberOrNull(item?.flight_duration_minutes) ?? numberOrNull(flight?.duration_minutes),
      outbound_duration_minutes: numberOrNull(flight?.outbound_duration_minutes),
      return_duration_minutes: numberOrNull(flight?.return_duration_minutes),
      airline_code: textOrNull(flight?.airline_code),
      airline_name: textOrNull(flight?.airline_name),
      flight_number: textOrNull(flight?.flight_number),
    },
    destination: {
      city: textOrNull(item?.city) || textOrNull(flight?.destination_city),
      airport: textOrNull(flight?.airport_name),
      country_code: textOrNull(flight?.destination_country_code),
      latitude: numberOrNull(flight?.latitude),
      longitude: numberOrNull(flight?.longitude),
    },
    weather: flightWeather(item, flight),
    country: {
      common_name: textOrNull(flight?.destination_country),
    },
  }
}

function fillMissingDisplayFields(result, flight) {
  if (!result || !flight) return result
  const nextFlight = { ...result.flight }
  const nextDestination = { ...result.destination }
  const nextCountry = { ...result.country }

  if (!nextFlight.origin_iata) nextFlight.origin_iata = textOrNull(flight.origin_iata)
  if (!nextFlight.origin_airport) nextFlight.origin_airport = textOrNull(flight.origin_airport)
  if (!nextFlight.destination_airport) {
    nextFlight.destination_airport = textOrNull(flight.destination_airport)
  }
  if (!nextFlight.airline_code) nextFlight.airline_code = textOrNull(flight.airline_code)
  if (!nextFlight.airline_name) nextFlight.airline_name = textOrNull(flight.airline_name)
  if (!nextFlight.flight_number) nextFlight.flight_number = textOrNull(flight.flight_number)
  if (!nextFlight.departure_at) nextFlight.departure_at = textOrNull(flight.departure_at)
  if (!nextFlight.return_at) nextFlight.return_at = textOrNull(flight.return_at)
  if (nextFlight.return_stops == null) nextFlight.return_stops = numberOrNull(flight.return_stops)
  if (nextFlight.duration_minutes == null) nextFlight.duration_minutes = numberOrNull(flight.duration_minutes)
  if (nextFlight.outbound_duration_minutes == null) {
    nextFlight.outbound_duration_minutes = numberOrNull(flight.outbound_duration_minutes)
  }
  if (nextFlight.return_duration_minutes == null) {
    nextFlight.return_duration_minutes = numberOrNull(flight.return_duration_minutes)
  }

  if (!nextDestination.airport) nextDestination.airport = textOrNull(flight.airport_name)
  if (!nextDestination.country_code) {
    nextDestination.country_code = textOrNull(flight.destination_country_code)
  }
  if (nextDestination.latitude == null) nextDestination.latitude = numberOrNull(flight.latitude)
  if (nextDestination.longitude == null) nextDestination.longitude = numberOrNull(flight.longitude)
  if (!nextCountry.common_name) nextCountry.common_name = textOrNull(flight.destination_country)

  const nextWeather = { ...result.weather }
  const fromFlight = flightWeather(result, flight)
  for (const [key, value] of Object.entries(fromFlight)) {
    if (nextWeather[key] == null && value != null) nextWeather[key] = value
  }

  return {
    ...result,
    originIata: result.originIata || textOrNull(flight.origin_iata),
    photoUrl: result.photoUrl || textOrNull(flight.photo_url),
    photoUrlSmall: result.photoUrlSmall || textOrNull(flight.photo_url_small),
    joinedFlight: true,
    documentId: result.documentId || textOrNull(flight.id),
    flight: nextFlight,
    destination: nextDestination,
    country: nextCountry,
    weather: nextWeather,
  }
}

export function adaptRecommendations(response, { flightsResponse = null, selectedOrigin = null } = {}) {
  const originId =
    textOrNull(response?.origin_id) ||
    textOrNull(response?.origin?.id) ||
    textOrNull(selectedOrigin?.originId)
  const originIata =
    textOrNull(selectedOrigin?.iata) ||
    textOrNull(response?.origin?.city_iata?.[0]) ||
    textOrNull(response?.origin?.airports?.[0]) ||
    textOrNull(response?.request?.origin) ||
    textOrNull(response?.updated_request?.origin)
  const originCity = textOrNull(response?.origin?.city) || textOrNull(selectedOrigin?.city)
  const originCountry = textOrNull(response?.origin?.country) || textOrNull(selectedOrigin?.country)
  const dataSource = textOrNull(response?.data_source) || textOrNull(flightsResponse?.data_source)
  const flightIndex = indexFlightsById(flightsResponse?.flights ?? response?.flights)
  const recommendations = Array.isArray(response?.recommendations) ? response.recommendations : []

  return {
    originId,
    dataSource,
    dateFallback: {
      used: response?.flexible_date_fallback_used === true,
      exactMatchCount: numberOrNull(response?.exact_match_count),
      fallbackCount: numberOrNull(response?.fallback_count),
    },
    rejected: Array.isArray(response?.rejected) ? response.rejected : [],
    results: recommendations.map((item) =>
      mapRecommendation(item, {
        originId,
        originIata,
        originCity,
        originCountry,
        dataSource,
        flightIndex,
      }),
    ),
  }
}

function cityKey(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
}

/**
 * Attach photo URLs from origin-city documents whose city exactly matches the
 * destination city. Flight documents do not store photos; origins do.
 * Never copies a departure city's photo onto a different destination.
 * Never adds, removes, reorders, or rescores items.
 */
export function attachDestinationCityPhotos(results, originItems = []) {
  const list = Array.isArray(results) ? results : []
  const photosByCity = new Map()
  const photosByCityCountry = new Map()

  for (const item of Array.isArray(originItems) ? originItems : []) {
    const city = cityKey(item?.city)
    const photoUrl = textOrNull(item?.photo_url)
    const photoUrlSmall = textOrNull(item?.photo_url_small)
    if (!city || (!photoUrl && !photoUrlSmall)) continue
    const photos = { photoUrl, photoUrlSmall }
    if (!photosByCity.has(city)) photosByCity.set(city, photos)
    const country = cityKey(item?.country_code)
    if (country) {
      const key = `${city}|${country}`
      if (!photosByCityCountry.has(key)) photosByCityCountry.set(key, photos)
    }
  }

  return list.map((result) => {
    if (result?.photoUrl || result?.photoUrlSmall) return result
    const destCity = cityKey(result?.destination?.city)
    if (!destCity) return result
    const destCountry = cityKey(result?.destination?.country_code)
    const match =
      (destCountry && photosByCityCountry.get(`${destCity}|${destCountry}`)) ||
      photosByCity.get(destCity) ||
      null
    if (!match) return result
    return {
      ...result,
      photoUrl: result.photoUrl || match.photoUrl,
      photoUrlSmall: result.photoUrlSmall || match.photoUrlSmall,
    }
  })
}

/**
 * Join flight display fields onto already-adapted recommendations.
 * Never adds, removes, reorders, or rescores items.
 */
export function enrichRecommendations(results, flightsResponse) {
  const list = Array.isArray(results) ? results : []
  if (!flightsResponse) return list.slice()
  const flightIndex = indexFlightsById(flightsResponse.flights)
  return list.map((item) => {
    const { flight, joined, unsafe } = pickFlight(item?.id || item?.destinationId, flightIndex)
    if (!joined) {
      return unsafe ? { ...item, joinUnsafe: true } : item
    }
    return fillMissingDisplayFields(item, flight)
  })
}
