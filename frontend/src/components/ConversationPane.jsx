import { snapshotLabel } from '../utils/adaptResults'
import { REFINEMENT_ACTIONS } from '../utils/plannerFlow'
import ResultsList from './ResultsList'
import styles from '../workspace.module.css'

function summaryLine(filters, originLabel, tripRequest) {
  if (tripRequest) {
    return [
      originLabel || tripRequest.origin,
      tripRequest.budget != null
        ? `${tripRequest.currency || 'EUR'} ${tripRequest.budget}`.trim()
        : null,
      tripRequest.direct_flights_only ? 'Direct only' : null,
      tripRequest.weather_preference || null,
      tripRequest.departure_date && tripRequest.return_date
        ? `${tripRequest.departure_date} → ${tripRequest.return_date}`
        : null,
    ]
      .filter(Boolean)
      .join(' · ')
  }
  if (!filters) return ''
  return [
    originLabel || filters.originId,
    filters.maxBudget != null ? `up to €${filters.maxBudget}` : null,
    filters.directOnly ? 'Direct only' : 'Any stops',
    filters.preferWarm ? 'Prefer warmer' : 'Any weather',
  ]
    .filter(Boolean)
    .join(' · ')
}

export default function ConversationPane({
  messages,
  filters,
  originLabel,
  tripRequest = null,
  dataSource,
  rejectedCount = 0,
  results,
  previousRanks,
  selectedId,
  savedIds,
  loading,
  refining = false,
  phase = 'ready',
  activeRefinement = null,
  canRefine = false,
  onRefine,
  onSelect,
  onToggleSaved,
  onViewDetails,
}) {
  const showResults = phase !== 'clarifying' && (results.length > 0 || (!loading && phase === 'ready'))
  const busy = loading || refining

  return (
    <div className={styles.conversation}>
      {(filters || tripRequest) && (
        <p className={styles.requestSummary}>
          <span>Request</span>
          {summaryLine(filters, originLabel, tripRequest)}
        </p>
      )}
      {snapshotLabel(dataSource) && (
        <p className={styles.panelHint}>{snapshotLabel(dataSource)}. Not live or bookable.</p>
      )}
      {rejectedCount > 0 && (
        <p className={styles.panelHint}>
          {rejectedCount} stored {rejectedCount === 1 ? 'offer was' : 'offers were'} excluded as incomplete.
        </p>
      )}

      {messages.map((message) => (
        <div
          key={message.id}
          className={message.role === 'user' ? styles.bubbleUser : styles.bubbleAssistant}
        >
          {message.role !== 'user' && <small>Planner service</small>}
          <p>{message.text}</p>
        </div>
      ))}

      {loading && <p className={styles.notice}>Loading destinations…</p>}
      {refining && !loading && <p className={styles.notice}>Updating recommendations…</p>}

      {showResults && results.length > 0 && (
        <div className={styles.chips} role="group" aria-label="Refine recommendations">
          {REFINEMENT_ACTIONS.map((action) => (
            <button
              key={action.label}
              type="button"
              className={activeRefinement === action.label ? styles.chipActive : styles.chip}
              aria-pressed={activeRefinement === action.label}
              disabled={!canRefine || busy}
              onClick={() => onRefine(action.label)}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}

      {showResults && (
        <ResultsList
          results={results}
          previousRanks={previousRanks}
          selectedId={selectedId}
          savedIds={savedIds}
          onSelect={onSelect}
          onToggleSaved={onToggleSaved}
          onViewDetails={onViewDetails}
        />
      )}
    </div>
  )
}
