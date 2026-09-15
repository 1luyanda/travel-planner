import { useEffect, useRef } from 'react'
import DestinationCard from './DestinationCard'
import styles from '../workspace.module.css'

export default function ResultsList({
  results,
  previousRanks,
  weights,
  selectedId,
  savedIds,
  onSelect,
  onToggleSaved,
  onViewDetails,
}) {
  const count = results.length
  const heading = count === 1 ? '1 matching trip' : `${count} matching trips`
  const cardRefs = useRef({})

  useEffect(() => {
    if (!selectedId) return
    cardRefs.current[selectedId]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [selectedId])

  return (
    <section className={styles.results} aria-labelledby="results-title">
      <h2 id="results-title">{heading}</h2>
      {count === 0 ? (
        <p className={styles.notice}>
          No destinations match these filters. Try a higher budget or fewer constraints.
        </p>
      ) : (
        <div className={styles.cardStack}>
          {results.map((destination, index) => (
            <DestinationCard
              key={destination.id || `${destination.destination?.city}-${index}`}
              destination={destination}
              rank={index + 1}
              previousRank={previousRanks[destination.id]}
              isBestMatch={index === 0 && destination.scores?.total != null}
              isSelected={destination.id === selectedId}
              isSaved={savedIds.includes(destination.id)}
              weights={weights}
              onSelect={onSelect}
              onToggleSaved={onToggleSaved}
              onViewDetails={onViewDetails}
              cardRef={(node) => {
                if (destination.id) cardRefs.current[destination.id] = node
              }}
            />
          ))}
        </div>
      )}
    </section>
  )
}
