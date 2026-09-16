import { snapshotLabel } from '../utils/adaptResults'
import { refinementPresets } from '../utils/ranking'
import ResultsList from './ResultsList'
import styles from '../workspace.module.css'

const actions = ['Cheaper', 'Warmer', 'Direct flights', 'Shorter travel']

function isActive(action, weights) {
  const preset = refinementPresets[action]
  if (!preset || !weights) return false
  return Object.keys(preset).every((key) => preset[key] === weights[key])
}

function summaryLine(filters, originLabel) {
  if (!filters) return ''
  return [
    originLabel || filters.originId,
    `up to €${filters.maxBudget}`,
    filters.directOnly ? 'Direct only' : 'Any stops',
    filters.preferWarm ? 'Prefer warmer' : 'Any weather',
  ].filter(Boolean).join(' · ')
}

export default function ConversationPane({
  messages,
  filters,
  originLabel,
  dataSource,
  rejectedCount = 0,
  weights,
  results,
  previousRanks,
  selectedId,
  savedIds,
  loading,
  onRefine,
  onSelect,
  onToggleSaved,
  onViewDetails,
}) {
  return (
    <div className={styles.conversation}>
      {filters && (
        <p className={styles.requestSummary}>
          <span>Request</span>
          {summaryLine(filters, originLabel)}
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
          {message.role !== 'user' && <small>Stored snapshot</small>}
          <p>{message.text}</p>
        </div>
      ))}

      {loading && <p className={styles.notice}>Loading destinations…</p>}

      {results.length > 0 && (
        <div className={styles.chips} role="group" aria-label="Refine ranking">
          {actions.map((action) => (
            <button
              key={action}
              type="button"
              className={isActive(action, weights) ? styles.chipActive : styles.chip}
              aria-pressed={isActive(action, weights)}
              onClick={() => onRefine(action)}
            >
              {action}
            </button>
          ))}
        </div>
      )}

      <ResultsList
        results={results}
        previousRanks={previousRanks}
        weights={weights}
        selectedId={selectedId}
        savedIds={savedIds}
        onSelect={onSelect}
        onToggleSaved={onToggleSaved}
        onViewDetails={onViewDetails}
      />
    </div>
  )
}
