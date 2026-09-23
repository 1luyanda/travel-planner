import { useId } from 'react'
import TripDetailsContent, { DETAILS_EMPTY_MESSAGE, TripDetailsHeader } from './TripDetailsContent'
import styles from '../workspace.module.css'

/**
 * Desktop inline trip-details pane. Not a modal: no overlay, focus trap, or
 * page-scroll lock.
 */
export default function TripDetailsPanel({
  destination,
  isSaved = false,
  onToggleSaved,
  onClose,
  moods,
  activitiesEnabled = false,
  hotelSelection,
  activitySelection,
}) {
  const titleId = useId()

  if (!destination) {
    return (
      <section className={styles.detailsPane} aria-label="Trip details">
        <p className={styles.detailsEmpty}>{DETAILS_EMPTY_MESSAGE}</p>
      </section>
    )
  }

  return (
    <section className={styles.detailsPane} aria-labelledby={titleId}>
      <TripDetailsHeader
        destination={destination}
        titleId={titleId}
        isSaved={isSaved}
        onToggleSaved={onToggleSaved}
        onClose={onClose}
      />
      <div className={styles.detailsBody}>
        <TripDetailsContent
          destination={destination}
          titleId={titleId}
          moods={moods}
          activitiesEnabled={activitiesEnabled}
          hotelSelection={hotelSelection}
          activitySelection={activitySelection}
        />
      </div>
    </section>
  )
}
