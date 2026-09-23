import ResultsList from './ResultsList'
import styles from '../workspace.module.css'

export default function SavedPane({
  destinations,
  loading,
  error,
  selectedId,
  savedIds,
  onSelect,
  onToggleSaved,
  onViewDetails,
  onExplore,
}) {
  const count = destinations.length
  const heading = count === 1 ? '1 saved flight' : `${count} saved flights`

  return (
    <div className={styles.conversation}>
      <h1 className={styles.savedTitle}>Saved</h1>
      <p className={styles.panelHint}>
        Saved to your account.
      </p>
      {error ? <p className={styles.noticeError}>{error}</p> : null}
      {loading ? (
        <p className={styles.notice}>Loading saved flights…</p>
      ) : destinations.length === 0 && !error ? (
        <div className={styles.emptySaved}>
          <p>No saved flights yet.</p>
          <button type="button" className={styles.secondaryBtn} onClick={onExplore}>
            Plan a trip
          </button>
        </div>
      ) : destinations.length > 0 ? (
        <ResultsList
          results={destinations}
          heading={heading}
          showRanking={false}
          previousRanks={{}}
          selectedId={selectedId}
          savedIds={savedIds}
          onSelect={onSelect}
          onToggleSaved={onToggleSaved}
          onViewDetails={onViewDetails}
        />
      ) : null}
    </div>
  )
}
