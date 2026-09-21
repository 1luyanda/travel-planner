import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchActivities } from '../services/travelApi'
import {
  activitiesPayloadFromDestination,
  activitiesRequestKey,
  cleanMoods,
  createActivitiesLoader,
  formatActivityBusinessStatus,
  formatActivityPriceLevel,
  formatActivityRating,
} from '../utils/activities'

const INITIAL_STATE = { status: 'idle', activities: [], error: '' }

function stateForRequest({ visible, payload }) {
  if (!visible) return INITIAL_STATE
  if (!payload) return { status: 'unavailable', activities: [], error: '' }
  return { status: 'loading', activities: [], error: '' }
}

export function TripDetailsActivitiesView({
  titleId,
  state,
  onRetry,
}) {
  const headingId = `${titleId}-activities`
  const status = state?.status || 'idle'
  if (status === 'idle') return null

  return (
    <section className="trip-details-activities" aria-labelledby={headingId}>
      <h3 id={headingId}>Activities</h3>
      {status === 'loading' ? (
        <p className="trip-details-activities-status" aria-live="polite" aria-busy="true">
          Loading activities…
        </p>
      ) : null}
      {status === 'unavailable' ? (
        <p className="trip-details-activities-status">
          Activities are unavailable because this trip has no city.
        </p>
      ) : null}
      {status === 'error' ? (
        <div className="trip-details-activities-error">
          <p className="trip-details-activities-status" role="alert">
            {state.error || 'Activity data is temporarily unavailable.'}
          </p>
          {onRetry ? (
            <button type="button" className="trip-details-activities-retry" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      ) : null}
      {status === 'ready' && !state.activities.length ? (
        <p className="trip-details-activities-status">No activities found for this destination.</p>
      ) : null}
      {status === 'ready' && state.activities.length ? (
        <ul className="trip-details-activity-list">
          {state.activities.map((item) => (
            <ActivityCard key={item.place_id} item={item} />
          ))}
        </ul>
      ) : null}
    </section>
  )
}

function ActivityCard({ item }) {
  const rating = formatActivityRating(item.rating, item.user_ratings_total)
  const status = formatActivityBusinessStatus(item.business_status)
  const priceLevel = formatActivityPriceLevel(item.price_level)

  return (
    <li className="trip-details-activity-card">
      <p className="trip-details-activity-name">{item.name}</p>
      {item.address ? <p className="trip-details-activity-meta">{item.address}</p> : null}
      {rating ? <p className="trip-details-activity-meta">{rating}</p> : null}
      {status ? <p className="trip-details-activity-meta">{status}</p> : null}
      {priceLevel ? <p className="trip-details-activity-meta">Price level: {priceLevel}</p> : null}
    </li>
  )
}

export default function TripDetailsActivities({
  destination,
  moods,
  enabled = false,
  titleId,
}) {
  const city = destination?.destination?.city
  const countryCode = destination?.destination?.country_code
  const destinationId = destination?.id || destination?.destinationId
  const moodsKey = JSON.stringify(cleanMoods(moods))
  const payload = useMemo(
    () =>
      activitiesPayloadFromDestination(
        {
          id: destinationId,
          destination: { city, country_code: countryCode },
        },
        JSON.parse(moodsKey),
      ),
    [city, countryCode, destinationId, moodsKey],
  )
  const requestKey = activitiesRequestKey(payload)
  const visible = Boolean(enabled && destination)
  const sessionKey = `${visible}:${requestKey}`
  const [retry, setRetry] = useState(0)
  const [state, setState] = useState(INITIAL_STATE)
  const [appliedKey, setAppliedKey] = useState('')
  const loaderRef = useRef(null)
  if (!loaderRef.current) {
    loaderRef.current = createActivitiesLoader({ fetchActivities })
  }

  if (appliedKey !== sessionKey) {
    setAppliedKey(sessionKey)
    setRetry(0)
    setState(stateForRequest({ visible, payload }))
  }

  useEffect(() => {
    const loader = loaderRef.current
    loader.run({
      payload,
      enabled: visible,
      onChange: setState,
    })
    return () => loader.cancel()
  }, [payload, requestKey, retry, visible])

  return (
    <TripDetailsActivitiesView
      titleId={titleId}
      state={visible ? state : INITIAL_STATE}
      onRetry={state.status === 'error' ? () => setRetry((current) => current + 1) : undefined}
    />
  )
}
