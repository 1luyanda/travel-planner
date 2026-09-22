import { useEffect, useId, useRef } from 'react'
import TripDetailsContent, { TripDetailsHeader } from './TripDetailsContent'

/**
 * Trip-details popup over the chat column. The map stays outside this overlay
 * so it remains interactive.
 */
export default function TripDetailsDrawer({
  destination,
  onClose,
  isSaved = false,
  onToggleSaved,
  moods,
  activitiesEnabled = false,
  hotelSelection,
}) {
  const generatedTitleId = useId()
  const titleId = generatedTitleId
  const closeRef = useRef(null)
  const panelRef = useRef(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const tripId = destination?.id

  useEffect(() => {
    if (!tripId) return undefined

    closeRef.current?.focus()

    function focusables() {
      const root = panelRef.current
      if (!root) return []
      return [...root.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(
        (node) => !node.hasAttribute('disabled') && !node.closest('[hidden]'),
      )
    }

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const nodes = focusables()
      if (!nodes.length) return
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [tripId])

  if (!destination) return null

  return (
    <div className="drawer-root">
      <button
        type="button"
        className="drawer-overlay"
        aria-label="Close trip details"
        tabIndex={-1}
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <TripDetailsHeader
          destination={destination}
          titleId={titleId}
          isSaved={isSaved}
          onToggleSaved={onToggleSaved}
          onClose={onClose}
          closeRef={closeRef}
        />
        <div className="drawer-body">
          <TripDetailsContent
            destination={destination}
            titleId={titleId}
            moods={moods}
            activitiesEnabled={activitiesEnabled}
            hotelSelection={hotelSelection}
          />
        </div>
      </aside>
    </div>
  )
}
