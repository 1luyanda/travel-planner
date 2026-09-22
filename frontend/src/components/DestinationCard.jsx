import { Heart } from 'lucide-react'
import ScoreBreakdown from './ScoreBreakdown'
import FlexibleDateNotice from './FlexibleDateNotice'
import DestinationPhoto from './DestinationPhoto'
import {
  displayValue,
  formatDate,
  formatPrice,
  tripFactItems,
} from '../utils/format'
import { backendScoreItems } from '../utils/plannerFlow'
import styles from '../workspace.module.css'

export default function DestinationCard({
  destination,
  rank,
  previousRank,
  isBestMatch,
  isSelected,
  isSaved,
  onSelect,
  onToggleSaved,
  onViewDetails,
  showRanking = true,
  cardRef,
}) {
  const flight = destination.flight || {}
  const place = destination.destination || {}
  const country = destination.country || {}
  const moved = previousRank && previousRank !== rank
  const breakdown = backendScoreItems(destination)
  const facts = tripFactItems(destination)
  const displayRank = destination.rank || rank

  return (
    <article
      className={isSelected ? `${styles.card} ${styles.cardSelected}` : styles.card}
      ref={cardRef}
      aria-current={isSelected ? 'true' : undefined}
    >
      <button type="button" className={styles.cardHit} onClick={() => onSelect?.(destination)}>
        <DestinationPhoto
          key={destination.id}
          destination={destination}
          className={styles.cardPhoto}
          sizes="280px"
        />
      </button>

      <div className={styles.cardBody}>
        <div className={styles.cardTop}>
          <div>
            <div className={styles.cardLabels}>
              {showRanking && isBestMatch && <span className={styles.bestMatch}>Best match</span>}
              {showRanking && <span className={styles.rank}>#{displayRank}</span>}
              {destination.priceChanged && <span className={styles.priceChanged}>Price changed</span>}
              {destination.availability === 'unavailable' && (
                <span className={styles.unavailable}>Unavailable</span>
              )}
            </div>
            <h3>{place.city || 'Unknown city'}</h3>
            <p>{country.common_name || place.country_code || displayValue(null)}</p>
          </div>
          <div className={styles.cardPrice}>
            <strong>{formatPrice(flight) || displayValue(null)}</strong>
            {onToggleSaved ? (
            <button
              type="button"
              className={isSaved ? styles.saveOn : styles.saveBtn}
              aria-pressed={isSaved}
              aria-label={isSaved ? `Remove ${place.city} from saved` : `Save ${place.city}`}
              onClick={(event) => {
                event.stopPropagation()
                onToggleSaved(destination)
              }}
            >
              <Heart size={16} fill={isSaved ? 'currentColor' : 'none'} />
            </button>
            ) : null}
          </div>
        </div>

        {destination.availability === 'unavailable' && (
          <p className={styles.unavailableNote}>Flight no longer available</p>
        )}
        {destination.savedAt && (
          <p className={styles.savedAt}>Saved {formatDate(destination.savedAt)}</p>
        )}
        {moved && <p className={styles.movement}>Moved from #{previousRank}</p>}
        {facts.length > 0 && (
          <ul className={styles.evidence}>
            {facts.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        <FlexibleDateNotice destination={destination} className={styles.reason} />

        {breakdown.length > 0 && (
          <details className={styles.why}>
            <summary>Planner scores</summary>
            <ScoreBreakdown items={breakdown} total={destination.scores?.total} />
          </details>
        )}

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
