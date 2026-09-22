/**
 * Saved-flight helpers. Flights live on the backend; hotel lookup IDs can be
 * restored from browser metadata by travelApi. This file only
 * adapts API payloads and decides Saved vs Explore chrome.
 */

import { hotelIdOrNull } from './savedHotelMetadata'

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

export function adaptSavedFlight(item) {
  const flight = item?.flight && typeof item.flight === 'object' ? item.flight : null
  const flightId = textOrNull(item?.flight_id) || textOrNull(flight?.id)
  const price = numberOrNull(flight?.price_eur)
  const available = item?.availability !== 'unavailable'

  return {
    id: flightId,
    destinationId: flightId,
    hotelDestinationId: hotelIdOrNull(item?.hotel_destination_id),
    destinationIata: textOrNull(flight?.destination_iata),
    originId: textOrNull(item?.origin_id) || textOrNull(flight?.origin_id),
    originIata: textOrNull(flight?.origin_iata),
    originCity: null,
    originCountry: null,
    documentId: flightId,
    photoUrl: textOrNull(flight?.photo_url),
    photoUrlSmall: textOrNull(flight?.photo_url_small),
    joinedFlight: Boolean(flight),
    availability: available ? 'available' : 'unavailable',
    priceChanged: Boolean(item?.price_changed),
    savedAt: item?.saved_at || null,
    savedPrice: numberOrNull(item?.saved_price),
    lastCheckedAt: item?.last_checked_at || null,
    lastCheckedPrice: numberOrNull(item?.last_checked_price),
    rank: null,
    scores: {},
    explanation: { summary: null, evidence: [], issues: [] },
    flight: {
      origin_iata: textOrNull(flight?.origin_iata),
      origin_airport: textOrNull(flight?.origin_airport),
      destination_iata: textOrNull(flight?.destination_iata),
      destination_airport: textOrNull(flight?.destination_airport),
      price,
      currency: textOrNull(flight?.currency) || (price != null ? 'EUR' : null),
      departure_at: textOrNull(flight?.departure_at),
      return_at: textOrNull(flight?.return_at),
      outbound_stops: numberOrNull(flight?.outbound_stops),
      return_stops: numberOrNull(flight?.return_stops),
      duration_minutes: numberOrNull(flight?.duration_minutes),
      outbound_duration_minutes: numberOrNull(flight?.outbound_duration_minutes),
      return_duration_minutes: numberOrNull(flight?.return_duration_minutes),
      airline_code: textOrNull(flight?.airline_code),
      airline_name: textOrNull(flight?.airline_name),
      flight_number: textOrNull(flight?.flight_number),
    },
    destination: {
      city: textOrNull(flight?.destination_city),
      airport: textOrNull(flight?.airport_name),
      country_code: textOrNull(flight?.destination_country_code),
      latitude: numberOrNull(flight?.latitude),
      longitude: numberOrNull(flight?.longitude),
    },
    weather: {
      average_max_temperature_c: numberOrNull(flight?.temp_max_c),
      average_min_temperature_c: numberOrNull(flight?.temp_min_c),
      average_precipitation_probability_percent: numberOrNull(flight?.rain_pct),
      average_sunshine_hours: numberOrNull(flight?.sunshine_hours),
      average_max_wind_speed_kmh: numberOrNull(flight?.max_wind_speed_kmh),
    },
    country: {
      common_name: textOrNull(flight?.destination_country),
    },
  }
}

export function adaptSavedFlights(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : []
  return items.map(adaptSavedFlight)
}

export function savedFlightIds(destinations = []) {
  return destinations.map((item) => item?.id).filter((id) => typeof id === 'string' && id)
}

export function destinationsForView(view, { results = [], savedItems = [] } = {}) {
  return view === 'saved' ? savedItems : results
}

export function showPlannerComposer(view) {
  return view !== 'saved'
}

export function showPlannerConversation(view, hasSearched) {
  return view !== 'saved' && Boolean(hasSearched)
}

export function showPlannerFilters(view) {
  return view === 'explore'
}

export function canSaveFlights(user) {
  return Boolean(user?.id)
}

export function flightReferenceFromDestination(destination) {
  return {
    flight_id: textOrNull(destination?.documentId) || textOrNull(destination?.id),
  }
}

export function keepSavedFlightPhotos(adapted, source) {
  if (!adapted) return adapted
  return {
    ...adapted,
    photoUrl: adapted.photoUrl || textOrNull(source?.photoUrl) || textOrNull(source?.photo_url),
    photoUrlSmall:
      adapted.photoUrlSmall || textOrNull(source?.photoUrlSmall) || textOrNull(source?.photo_url_small),
  }
}
