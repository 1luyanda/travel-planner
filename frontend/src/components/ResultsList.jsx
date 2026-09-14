import DestinationCard from './DestinationCard'

/**
 * Centre column: match count, empty-state copy, or ranked destination cards.
 * @param {object[]} results Filtered, ranked shortlist.
 * @param {Record<string, number>} previousRanks Map of destination id to previous rank.
 * @param {object} weights Passed through to each card’s score explanation.
 * @param {Function} onViewDetails Opens the trip details drawer.
 */
export default function ResultsList({ results, previousRanks, weights, onViewDetails }) {
  const count = results.length
  const heading = count === 1 ? '1 matching trip' : `${count} matching trips`

  return (
    <section className="results" aria-labelledby="results-title">
      <div className="results-heading">
        <h2 id="results-title">{heading}</h2>
        <p>Ranked by transparent local weighted score.</p>
      </div>

      {count === 0 ? (
        // Empty state: data loaded successfully, but filters matched nothing.
        <p className="notice">No destinations match these filters. Try a higher budget or fewer constraints.</p>
      ) : (
        <div className="card-stack">
          {results.map((destination, index) => (
            <DestinationCard
              key={destination.id || `${destination.destination?.city}-${index}`}
              destination={destination}
              rank={index + 1}
              previousRank={previousRanks[destination.id]}
              isBestMatch={index === 0}
              weights={weights}
              onViewDetails={onViewDetails}
            />
          ))}
        </div>
      )}
    </section>
  )
}
