import { useRef } from 'react'
import { Heart } from 'lucide-react'
import DestinationPhoto from './DestinationPhoto'
import FlexibleDateNotice from './FlexibleDateNotice'
import {
  displayValue,
  formatAirline,
  formatDate,
  formatFlightDurations,
  formatDuration,
  formatPrecipitation,
  formatPrice,
  formatStops,
  formatTemperature,
  formatTripDays,
} from '../utils/format'
import { formatOriginLabel } from '../utils/origins'
import { uniqueExplanationView } from '../utils/plannerFlow'
import TripDetailsActivities from './TripDetailsActivities'
import TripDetailsHotels from './TripDetailsHotels'
import { useScrollMapFocus } from '../utils/useScrollMapFocus'

export const DETAILS_EMPTY_MESSAGE = 'Select a trip to view its details.'

function Row({ label, value }) {
  return (
    <div className="trip-details-row">
      <dt>{label}</dt>
      <dd>{displayValue(value)}</dd>
    </div>
  )
}

function originLabel(destination) {
  return formatOriginLabel({
    city: destination?.originCity,
    country: destination?.originCountry,
    iata: destination?.originIata,
    originId: destination?.originId,
  })
}

function weatherLine(weather = {}) {
  const parts = [
    formatTemperature(weather.average_max_temperature_c)
      ? `${formatTemperature(weather.average_max_temperature_c)} avg max`
      : null,
    formatTemperature(weather.average_min_temperature_c)
      ? `${formatTemperature(weather.average_min_temperature_c)} avg min`
      : null,
    formatPrecipitation(weather.average_precipitation_probability_percent)
      ? `${formatPrecipitation(weather.average_precipitation_probability_percent)} rain`
      : null,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

export function TripDetailsHeader({
  destination,
  titleId,
  isSaved = false,
  onToggleSaved,
  onClose,
  closeRef,
}) {
  const place = destination?.destination || {}
  const country = destination?.country || {}
  const city = place.city || 'Trip'

  return (
    <div className="trip-details-header">
      <div>
        <p className="eyebrow">Trip details</p>
        <h2 id={titleId}>{city}</h2>
        <p>{displayValue(country.common_name || place.country_code)}</p>
      </div>
      <div className="trip-details-header-actions">
        {onToggleSaved && (
          <button
            type="button"
            className="icon-button"
            aria-pressed={isSaved}
            aria-label={isSaved ? `Remove ${city} from saved` : `Save ${city}`}
            onClick={() => onToggleSaved(destination)}
          >
            <Heart size={16} fill={isSaved ? 'currentColor' : 'none'} />
            {isSaved ? 'Saved' : 'Save'}
          </button>
        )}
        <button ref={closeRef} type="button" className="icon-button" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}

/**
 * Shared trip-details body for the desktop panel and mobile drawer.
 */
export default function TripDetailsContent({
  destination,
  titleId,
  moods,
  activitiesEnabled = false,
  hotelSelection,
  activitySelection,
}) {
  const flight = destination?.flight || {}
  const place = destination?.destination || {}
  const weather = destination?.weather || {}
  const country = destination?.country || {}
  const airline = formatAirline(flight)
  const { summary, evidence } = uniqueExplanationView(destination)
  const placesRef = useRef(null)
  // Scrolling the hotel/activity lists moves the map to the card being read.
  useScrollMapFocus(placesRef, (kind, key) => {
    if (kind === 'hotel' && key !== hotelSelection?.selectedHotelId) hotelSelection?.onSelectHotel?.(key)
    if (kind === 'activity' && key !== activitySelection?.selectedActivityId) {
      activitySelection?.onSelectActivity?.(key)
    }
  })

  if (!destination) return null

  return (
    <>
      <DestinationPhoto
        key={destination.id}
        destination={destination}
        className="trip-details-photo"
        sizes="420px"
      />

      <FlexibleDateNotice destination={destination} className="trip-details-notice" />

      {summary && <p className="trip-details-summary">{summary}</p>}
      {evidence.length > 0 && (
        <ul className="trip-details-evidence">
          {evidence.map((item) => (
            <li key={item.id || item.statement}>{item.statement}</li>
          ))}
        </ul>
      )}

      <dl className="trip-details-list">
        <Row label="City" value={place.city} />
        <Row label="Country" value={country.common_name || place.country_code} />
        <Row label="Origin" value={originLabel(destination)} />
        <Row label="Price" value={formatPrice(flight)} />
        <Row label="Currency" value={flight.currency} />
        <Row label="Departs" value={formatDate(flight.departure_at)} />
        <Row label="Returns" value={formatDate(flight.return_at)} />
        <Row
          label="Duration"
          value={formatTripDays(destination.tripDurationDays) || formatDuration(flight.duration_minutes)}
        />
        <Row label="Flight durations" value={formatFlightDurations(flight)} />
        <Row label="Stops" value={formatStops(flight.outbound_stops)} />
        <Row label="Airline" value={airline} />
        <Row label="Weather" value={weatherLine(weather)} />
      </dl>

      <div ref={placesRef} className="trip-details-places">
        <TripDetailsHotels
          key={destination.hotelDestinationId || 'unavailable'}
          destinationId={destination.hotelDestinationId}
          titleId={titleId}
          onHotelsChange={hotelSelection?.onHotelsChange}
          selectedHotelId={hotelSelection?.selectedHotelId}
          onSelectHotel={hotelSelection?.onSelectHotel}
        />

        <TripDetailsActivities
          destination={destination}
          moods={moods}
          enabled={activitiesEnabled}
          titleId={titleId}
          onActivitiesChange={activitySelection?.onActivitiesChange}
          selectedActivityId={activitySelection?.selectedActivityId}
          onSelectActivity={activitySelection?.onSelectActivity}
        />
      </div>
    </>
  )
}
