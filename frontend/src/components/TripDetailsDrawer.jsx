import { useEffect, useId, useRef } from 'react'
import ScoreBreakdown from './ScoreBreakdown'
import {
  NOT_AVAILABLE,
  formatAirline,
  formatDate,
  formatDuration,
  formatPrecipitation,
  formatPrice,
  formatStops,
  formatTemperature,
} from '../utils/format'
import { snapshotLabel } from '../utils/adaptResults'
import { backendScoreItems, explanationView } from '../utils/plannerFlow'

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
 * Right-hand slide-over with planner explanation, evidence, and scores.
 * Escape, overlay click, and Close all dismiss it and restore focus.
 */
export default function TripDetailsDrawer({ destination, onClose }) {
  const titleId = useId()
  const closeRef = useRef(null)
  const flight = destination?.flight || {}
  const place = destination?.destination || {}
  const weather = destination?.weather || {}
  const country = destination?.country || {}
  const airline = formatAirline(flight)
  const breakdown = destination ? backendScoreItems(destination) : []
  const { summary, evidence } = explanationView(destination)

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

        {summary && <p className="drawer-summary">{summary}</p>}
        {evidence.length > 0 && (
          <ul className="drawer-evidence">
            {evidence.map((item) => (
              <li key={item.id || item.statement}>{item.statement}</li>
            ))}
          </ul>
        )}

        <dl className="drawer-list">
          <Row label="Airport" value={place.airport || NOT_AVAILABLE} />
          <Row label="Price" value={formatPrice(flight) || NOT_AVAILABLE} />
          <Row label="Airline" value={airline || NOT_AVAILABLE} />
          <Row label="Flight number" value={flight.flight_number} />
          <Row label="Departs" value={formatDate(flight.departure_at)} />
          <Row label="Returns" value={formatDate(flight.return_at)} />
          <Row label="Duration" value={formatDuration(flight.duration_minutes) || NOT_AVAILABLE} />
          <Row label="Stops" value={formatStops(flight.outbound_stops) || NOT_AVAILABLE} />
          <Row label="Average max temperature" value={formatTemperature(weather.average_max_temperature_c) || NOT_AVAILABLE} />
          <Row
            label="Precipitation probability"
            value={formatPrecipitation(weather.average_precipitation_probability_percent)}
          />
          <Row label="Data" value={snapshotLabel(destination.dataSource)} />
        </dl>

        {breakdown.length > 0 && (
          <section className="drawer-score" aria-labelledby={`${titleId}-score`}>
            <h3 id={`${titleId}-score`}>Planner scores</h3>
            <ScoreBreakdown items={breakdown} total={destination.scores?.total} />
          </section>
        )}
      </aside>
    </div>
  )
}
