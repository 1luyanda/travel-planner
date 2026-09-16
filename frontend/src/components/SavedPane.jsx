import ResultsList from './ResultsList'
import styles from '../workspace.module.css'

export default function SavedPane({
  destinations,
  weights,
  selectedId,
  savedIds,
  onSelect,
  onToggleSaved,
  onViewDetails,
  onExplore,
}) {
  return (
    <div className={styles.conversation}>
      <h1 className={styles.savedTitle}>Saved</h1>
      <p className={styles.panelHint}>Kept on this device. Hearts save trips from the current stored shortlist.</p>
      {destinations.length === 0 ? (
        <div className={styles.emptySaved}>
          <p>No saved destinations yet.</p>
          <button type="button" className={styles.secondaryBtn} onClick={onExplore}>
            Back to explore
          </button>
        </div>
      ) : (
        <ResultsList
          results={destinations}
          previousRanks={{}}
          weights={weights}
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
