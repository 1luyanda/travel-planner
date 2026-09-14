import { useEffect, useId, useRef } from 'react'
import ScoreBreakdown from './ScoreBreakdown'
import {
  formatAirline,
  formatDate,
  formatDuration,
  formatPrecipitation,
  formatPrice,
  formatStops,
  formatTemperature,
} from '../utils/format'
import { scoreBreakdown } from '../utils/ranking'

/** Omit a details row when the mock JSON has no value for that field. */
function Row({ label, value }) {
  if (value == null || value === '') return null
  return (
    <div className="drawer-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

/**
 * Right-hand slide-over with real mock fields and the ranking breakdown.
 * Escape, overlay click, and Close all dismiss it and restore focus.
 * @param {object | null} destination Selected trip, or null when closed.
 * @param {object | null} weights Current ranking weights.
 * @param {() => void} onClose
 */
export default function TripDetailsDrawer({ destination, weights, onClose }) {
  const titleId = useId()
  const closeRef = useRef(null)
  const flight = destination?.flight || {}
  const place = destination?.destination || {}
  const weather = destination?.weather || {}
  const country = destination?.country || {}
  const airline = formatAirline(flight)
  const breakdown = destination ? scoreBreakdown(destination, weights) : []

  // Trap nothing heavy: focus Close, lock body scroll, and listen for Escape.
  useEffect(() => {
    if (!destination) return undefined

    closeRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function onKeyDown(event) {
      if (event.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [destination, onClose])

  if (!destination) return null

  return (
    <div className="drawer-root">
      <button type="button" className="drawer-overlay" aria-label="Close trip details" onClick={onClose} />
      <aside className="drawer-panel" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Trip details</p>
            <h2 id={titleId}>{place.city || 'Trip'}</h2>
            {country.common_name && <p>{country.common_name}</p>}
          </div>
          <button ref={closeRef} type="button" className="icon-button" onClick={onClose}>
            Close
          </button>
        </div>

        <dl className="drawer-list">
          <Row label="Airport" value={place.airport} />
          <Row label="Price" value={formatPrice(flight)} />
          <Row label="Airline" value={airline} />
          <Row label="Flight number" value={flight.flight_number} />
          <Row label="Departs" value={formatDate(flight.departure_at)} />
          <Row label="Returns" value={formatDate(flight.return_at)} />
          <Row label="Duration" value={formatDuration(flight.duration_minutes)} />
          <Row label="Stops" value={formatStops(flight.outbound_stops)} />
          <Row label="Average max temperature" value={formatTemperature(weather.average_max_temperature_c)} />
          <Row
            label="Precipitation probability"
            value={formatPrecipitation(weather.average_precipitation_probability_percent)}
          />
        </dl>

        <section className="drawer-score" aria-labelledby={`${titleId}-score`}>
          <h3 id={`${titleId}-score`}>Ranking breakdown</h3>
          <ScoreBreakdown items={breakdown} total={destination.scores?.total} />
        </section>
      </aside>
    </div>
  )
}
