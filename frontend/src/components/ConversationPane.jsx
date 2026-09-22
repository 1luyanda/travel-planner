import { REFINEMENT_ACTIONS, plannerRequestSummary } from '../utils/plannerFlow'
import ResultsList from './ResultsList'
import styles from '../workspace.module.css'

export default function ConversationPane({
  messages,
  filters,
  originLabel,
  tripRequest = null,
  preferences = null,
  dataSource,
  dateFallback = null,
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
  const summary = plannerRequestSummary(filters, originLabel, tripRequest, preferences)

  return (
    <div className={styles.conversation}>
      {summary && (
        <p className={styles.requestSummary}>
          <span>Request</span>
          {summary}
        </p>
      )}
      {rejectedCount > 0 && (
        <p className={styles.panelHint}>
          {rejectedCount} {rejectedCount === 1 ? 'offer was' : 'offers were'} excluded as incomplete.
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

      {showResults && results.length > 0 && dateFallback?.used && (
        <p className={styles.panelHint}>
          Nearby dates included.
          {dateFallback.exactMatchCount != null && ` Exact-date matches: ${dateFallback.exactMatchCount}.`}
          {dateFallback.fallbackCount != null && ` Alternative-date options: ${dateFallback.fallbackCount}.`}
        </p>
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
