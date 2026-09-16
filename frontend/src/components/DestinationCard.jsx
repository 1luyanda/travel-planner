import { Heart } from 'lucide-react'
import ScoreBreakdown from './ScoreBreakdown'
import DestinationPhoto from './DestinationPhoto'
import {
  displayValue,
  formatAirline,
  formatPrice,
  tripFactsLine,
} from '../utils/format'
import { rankingReason, scoreBreakdown } from '../utils/ranking'
import styles from '../workspace.module.css'

export default function DestinationCard({
  destination,
  rank,
  previousRank,
  isBestMatch,
  isSelected,
  isSaved,
  weights,
  onSelect,
  onToggleSaved,
  onViewDetails,
  cardRef,
}) {
  const flight = destination.flight || {}
  const place = destination.destination || {}
  const country = destination.country || {}
  const airline = formatAirline(flight)
  const moved = previousRank && previousRank !== rank
  const breakdown = scoreBreakdown(destination, weights)
  const reason = rankingReason(destination, weights)
  const facts = tripFactsLine(destination)

  return (
    <article
      className={isSelected ? `${styles.card} ${styles.cardSelected}` : styles.card}
      ref={cardRef}
      aria-current={isSelected ? 'true' : undefined}
    >
      <button type="button" className={styles.cardHit} onClick={() => onSelect?.(destination)}>
        <DestinationPhoto destination={destination} className={styles.cardPhoto} sizes="280px" />
      </button>

      <div className={styles.cardBody}>
        <div className={styles.cardTop}>
          <div>
            <div className={styles.cardLabels}>
              {isBestMatch && <span className={styles.bestMatch}>Best match</span>}
              <span className={styles.rank}>#{rank}</span>
            </div>
            <h3>{place.city || 'Unknown city'}</h3>
            <p>{country.common_name || place.country_code || displayValue(null)}</p>
          </div>
          <div className={styles.cardPrice}>
            <strong>{formatPrice(flight) || displayValue(null)}</strong>
            <button
              type="button"
              className={isSaved ? styles.saveOn : styles.saveBtn}
              aria-pressed={isSaved}
              aria-label={isSaved ? `Remove ${place.city} from saved` : `Save ${place.city}`}
              onClick={(event) => {
                event.stopPropagation()
                onToggleSaved?.(destination)
              }}
            >
              <Heart size={16} fill={isSaved ? 'currentColor' : 'none'} />
            </button>
          </div>
        </div>

        {moved && <p className={styles.movement}>Moved from #{previousRank}</p>}
        {facts && <p className={styles.facts}>{facts}{airline ? ` · ${airline}` : ''}</p>}
        {!facts && <p className={styles.facts}>{displayValue(null)}</p>}
        {reason && <p className={styles.reason}>{reason}</p>}

        <details className={styles.why}>
          <summary>How it’s ranked</summary>
          <ScoreBreakdown items={breakdown} total={destination.scores?.total} />
        </details>

        {onViewDetails && (
          <button
            type="button"
            className={styles.textLink}
            onClick={(event) => onViewDetails(destination, event)}
          >
            Trip details
          </button>
        )}
      </div>
    </article>
  )
}
