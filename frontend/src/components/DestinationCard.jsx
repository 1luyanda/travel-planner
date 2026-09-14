import ScoreBreakdown from './ScoreBreakdown'
import {
  cityTone,
  formatAirline,
  formatDuration,
  formatPrecipitation,
  formatPrice,
  formatStops,
  formatTemperature,
} from '../utils/format'
import { percent, scoreBreakdown } from '../utils/ranking'

/**
 * One ranked destination. Values come from the mock JSON; missing fields are omitted.
 * @param {object} destination Normalised record plus `scores` from ranking.js.
 * @param {number} rank 1-based position in the current shortlist.
 * @param {number} [previousRank] Prior rank, used after refinement.
 * @param {boolean} isBestMatch First result in the ranked list.
 * @param {object} weights Current weights for the “Why this ranking?” breakdown.
 * @param {(destination: object, event: MouseEvent) => void} onViewDetails
 */
export default function DestinationCard({
  destination,
  rank,
  previousRank,
  isBestMatch,
  weights,
  onViewDetails,
}) {
  const flight = destination.flight || {}
  const place = destination.destination || {}
  const weather = destination.weather || {}
  const country = destination.country || {}
  const airline = formatAirline(flight)
  const moved = previousRank && previousRank !== rank
  const breakdown = scoreBreakdown(destination, weights)
  const tone = cityTone(place.city)

  return (
    <article className="destination-card">
      {/* Decorative gradient only; the mock data has no destination images. */}
      <div
        className="card-media"
        style={{ '--tone': `${tone}` }}
        aria-hidden="true"
      />

      <div className="card-body">
        <div className="card-top">
          <div>
            <div className="card-labels">
              {isBestMatch && <span className="best-match">Best match</span>}
              <span className="rank">#{rank}</span>
            </div>
            <h3>{place.city || 'Unknown city'}</h3>
            <p className="country">{country.common_name || place.country_code}</p>
          </div>
          {formatPrice(flight) && <strong className="price">{formatPrice(flight)}</strong>}
        </div>

        {moved && <p className="movement">Moved from #{previousRank}</p>}

        <div className="facts">
          {formatStops(flight.outbound_stops) && <span>{formatStops(flight.outbound_stops)}</span>}
          {formatDuration(flight.duration_minutes) && <span>{formatDuration(flight.duration_minutes)}</span>}
          {formatTemperature(weather.average_max_temperature_c) && (
            <span>{formatTemperature(weather.average_max_temperature_c)} avg max</span>
          )}
          {formatPrecipitation(weather.average_precipitation_probability_percent) && (
            <span>{formatPrecipitation(weather.average_precipitation_probability_percent)} rain</span>
          )}
          {airline && <span>{airline}{flight.flight_number ? ` ${flight.flight_number}` : ''}</span>}
        </div>

        <div className="score-row">
          <span>Ranking score</span>
          <strong>{percent(destination.scores?.total)}</strong>
        </div>
        <div className="bar">
          <i style={{ width: percent(destination.scores?.total) }} />
        </div>

        <details className="why-ranking">
          <summary>Why this ranking?</summary>
          <ScoreBreakdown items={breakdown} total={destination.scores?.total} />
        </details>

        <button type="button" className="secondary" onClick={(event) => onViewDetails(destination, event)}>
          View trip details
        </button>
      </div>
    </article>
  )
}
