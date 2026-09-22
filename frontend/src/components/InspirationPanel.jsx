import { useEffect, useRef, useState } from 'react'
import { workspaceImages } from '../data/destinationImages'
import { fetchFlights } from '../services/travelApi'
import {
  applyInspirationDraft,
  canOpenTripDetails,
  inspirationEmptyMessage,
  inspirationFare,
  inspirationFlightQuery,
  inspirationHeading,
  inspirationHint,
  runInspirationFetch,
  staticInspirationDestinations,
} from '../utils/inspiration'
import DestinationPhoto from './DestinationPhoto'
import styles from '../workspace.module.css'

export default function InspirationPanel({
  origin = null,
  departureDate = '',
  returnDate = '',
  draft = '',
  onDraftChange,
  composerRef,
  onPlan,
  onExplore,
  onViewDetails,
  fetchFlightsFn = fetchFlights,
}) {
  const query = inspirationFlightQuery({ origin, departureDate, returnDate })
  const [destinations, setDestinations] = useState(() =>
    query ? [] : staticInspirationDestinations(),
  )
  const [status, setStatus] = useState(query ? 'loading' : 'ready')
  const [loadError, setLoadError] = useState('')
  const [instruction, setInstruction] = useState('')
  const seqRef = useRef(0)
  const fetchRef = useRef(fetchFlightsFn)
  fetchRef.current = fetchFlightsFn

  useEffect(() => {
    const nextQuery = inspirationFlightQuery({ origin, departureDate, returnDate })
    const seq = ++seqRef.current

    if (!origin?.originId) {
      setDestinations(staticInspirationDestinations())
      setStatus('ready')
      setLoadError('')
      return undefined
    }

    if (!nextQuery) {
      setDestinations([])
      setStatus('ready')
      setLoadError('')
      return undefined
    }

    const controller = new AbortController()
    setDestinations([])
    setStatus('loading')
    setLoadError('')

    runInspirationFetch({
      query: nextQuery,
      seq,
      isCurrent: (value) => value === seqRef.current,
      signal: controller.signal,
      fetchFlightsFn: fetchRef.current,
    }).then((outcome) => {
      if (outcome.status === 'stale' || outcome.status === 'aborted') return
      if (outcome.status === 'error') {
        setDestinations([])
        setLoadError(outcome.message)
        setStatus('error')
        return
      }
      setDestinations(outcome.destinations || [])
      setLoadError('')
      setStatus('ready')
    })

    return () => controller.abort()
  }, [origin?.originId, departureDate, returnDate])

  function handleSelect(destination) {
    if (canOpenTripDetails(destination)) {
      onViewDetails?.(destination)
    }
    const next = applyInspirationDraft({
      draft,
      city: destination?.destination?.city,
    })
    if (next.draft !== draft) onDraftChange?.(next.draft)
    setInstruction(next.hint)
    if (next.focusComposer) composerRef?.current?.focus()
  }

  const heading = inspirationHeading(origin)
  const hint = inspirationHint({ origin, query })
  const loading = status === 'loading'
  const empty = status === 'ready' && destinations.length === 0

  return (
    <aside className={styles.inspiration} aria-label="Destination inspiration">
      <h2>Get started</h2>
      <div className={styles.tiles}>
        <button type="button" className={styles.tile} onClick={onPlan}>
          <img src={workspaceImages.tileGetaway.src} alt="" />
          <span>Plan a getaway</span>
        </button>
        <button type="button" className={styles.tile} onClick={onExplore}>
          <img src={workspaceImages.tileExplore.src} alt="" />
          <span>Explore destinations</span>
        </button>
      </div>

      <div className={styles.previewBlock} id="destination-previews">
        <h3>{heading}</h3>
        <p className={styles.panelHint}>{hint}</p>
        {loading ? (
          <p className={styles.panelHint} role="status">
            Loading destinations…
          </p>
        ) : null}
        {loadError ? (
          <p className={styles.panelHint} role="status">
            {loadError} You can still search from the composer.
          </p>
        ) : null}
        {empty ? (
          <p className={styles.panelHint} role="status">
            {inspirationEmptyMessage({ origin, query })}
          </p>
        ) : null}
        {instruction ? (
          <p className={styles.panelHint} role="status">
            {instruction}
          </p>
        ) : null}
        <div className={styles.previews}>
          {destinations.map((destination) => {
            const city = destination.destination?.city || 'Destination'
            const country = destination.country?.common_name
            const fare = inspirationFare(destination)
            return (
              <button
                key={destination.id}
                type="button"
                className={styles.preview}
                onClick={() => handleSelect(destination)}
              >
                <div className={styles.previewMedia}>
                  <DestinationPhoto destination={destination} sizes="180px" />
                </div>
                <span className={styles.previewCopy}>
                  <strong>{city}</strong>
                  {country ? <em>{country}</em> : null}
                  {fare ? (
                    <b className={styles.previewFare}>
                      {fare.priceText}
                      <span>
                        {fare.departureText} – {fare.returnText}
                      </span>
                    </b>
                  ) : null}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
