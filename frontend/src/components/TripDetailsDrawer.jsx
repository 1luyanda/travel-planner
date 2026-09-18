import { useEffect, useId, useRef } from 'react'
import { Heart } from 'lucide-react'
import DestinationPhoto from './DestinationPhoto'
import ScoreBreakdown from './ScoreBreakdown'
import {
  NOT_AVAILABLE,
  displayValue,
  formatAirline,
  formatDate,
  formatDuration,
  formatPrecipitation,
  formatPrice,
  formatStops,
  formatTemperature,
  formatTripDays,
} from '../utils/format'
import { formatOriginLabel } from '../utils/origins'
import { backendScoreItems, explanationView } from '../utils/plannerFlow'

const SNAPSHOT_NOTICE = 'Stored snapshot data — not live or bookable'

function Row({ label, value }) {
  return (
    <div className="drawer-row">
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

/**
 * Right-hand slide-over with planner explanation, evidence, and scores.
 * Escape, overlay click, and Close all dismiss it and restore focus.
 */
export default function TripDetailsDrawer({
  destination,
  onClose,
  isSaved = false,
  onToggleSaved,
}) {
  const titleId = useId()
  const closeRef = useRef(null)
  const panelRef = useRef(null)
  const flight = destination?.flight || {}
  const place = destination?.destination || {}
  const weather = destination?.weather || {}
  const country = destination?.country || {}
  const airline = formatAirline(flight)
  const breakdown = destination ? backendScoreItems(destination) : []
  const { summary, evidence } = explanationView(destination)
  const city = place.city || 'Trip'

  useEffect(() => {
    if (!destination) return undefined

    closeRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function focusables() {
      const root = panelRef.current
      if (!root) return []
      return [...root.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(
        (node) => !node.hasAttribute('disabled'),
      )
    }

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const nodes = focusables()
      if (!nodes.length) return
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
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
      <button
        type="button"
        className="drawer-overlay"
        aria-label="Close trip details"
        tabIndex={-1}
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Trip details</p>
            <h2 id={titleId}>{city}</h2>
            <p>{displayValue(country.common_name || place.country_code)}</p>
          </div>
          <div className="drawer-header-actions">
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

        <DestinationPhoto
          key={destination.id}
          destination={destination}
          className="drawer-photo"
          sizes="420px"
        />

        <p className="drawer-notice">{SNAPSHOT_NOTICE}</p>

        {summary && <p className="drawer-summary">{summary}</p>}
        {evidence.length > 0 && (
          <ul className="drawer-evidence">
            {evidence.map((item) => (
              <li key={item.id || item.statement}>{item.statement}</li>
            ))}
          </ul>
        )}

        <dl className="drawer-list">
          <Row label="City" value={place.city} />
          <Row label="Country" value={country.common_name || place.country_code} />
          <Row label="Origin" value={originLabel(destination)} />
          <Row label="Price" value={formatPrice(flight)} />
          <Row label="Currency" value={flight.currency} />
          <Row label="Departs" value={formatDate(flight.departure_at)} />
          <Row label="Returns" value={formatDate(flight.return_at)} />
          <Row label="Duration" value={formatTripDays(destination.tripDurationDays) || formatDuration(flight.duration_minutes)} />
          <Row label="Stops" value={formatStops(flight.outbound_stops)} />
          <Row label="Airline" value={airline} />
          <Row label="Weather" value={weatherLine(weather)} />
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

export { SNAPSHOT_NOTICE }
