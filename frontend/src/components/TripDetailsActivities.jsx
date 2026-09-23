import { useEffect, useMemo, useRef, useState } from 'react'
import { Heart } from 'lucide-react'
import { fetchActivities } from '../services/travelApi'
import TripDetailsSection from './TripDetailsSection'
import {
  activitiesPayloadFromDestination,
  activitiesRequestKey,
  cleanMoods,
  createActivitiesLoader,
  formatActivityBusinessStatus,
  formatActivityPriceLevel,
  formatActivityRating,
} from '../utils/activities'
import { useActivityLikes } from '../utils/useActivityLikes'
import { activityPosition } from '../utils/activityMarkers'

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
  likedIds,
  pendingIds,
  likeError = '',
  persistenceNote = '',
  onToggleLike,
  selectedActivityId,
  onSelectActivity,
}) {
  const headingId = `${titleId}-activities`
  const status = state?.status || 'idle'
  const liked = likedIds instanceof Set ? likedIds : new Set(likedIds || [])
  const pending = pendingIds instanceof Set ? pendingIds : new Set(pendingIds || [])
  if (status === 'idle') return null

  return (
    <TripDetailsSection title="Activities" headingId={headingId}>
      {persistenceNote ? (
        <p className="trip-details-activities-like-note">{persistenceNote}</p>
      ) : null}
      {likeError ? (
        <p className="trip-details-activities-status" role="alert">
          {likeError}
        </p>
      ) : null}
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
        <>
          <ul className="trip-details-activity-list">
            {state.activities.map((item) => (
              <ActivityCard
                key={item.place_id}
                item={item}
                liked={liked.has(item.place_id)}
                pending={pending.has(item.place_id)}
                onToggleLike={onToggleLike}
                selected={selectedActivityId === item.place_id}
                onSelect={onSelectActivity}
              />
            ))}
          </ul>
          {state.activities.some((item) => item.description) ? (
            <p className="trip-details-activities-attribution">Place summaries from Google.</p>
          ) : null}
        </>
      ) : null}
    </TripDetailsSection>
  )
}

function ActivityCard({ item, liked = false, pending = false, onToggleLike, selected = false, onSelect }) {
  const rating = formatActivityRating(item.rating, item.user_ratings_total)
  const status = formatActivityBusinessStatus(item.business_status)
  const priceLevel = formatActivityPriceLevel(item.price_level)
  const name = item.name || 'activity'
  const placeId = item.place_id
  const label = liked ? `Unlike ${name}` : `Like ${name}`

  return (
    <li
      className={`trip-details-activity-card trip-details-hotel-card${selected ? ' is-selected' : ''}`}
      {...(placeId && activityPosition(item) ? { 'data-map-kind': 'activity', 'data-map-key': placeId } : {})}
    >
      <button
        type="button"
        className="trip-details-activity-body trip-details-hotel-select"
        aria-pressed={selected}
        onClick={() => onSelect?.(placeId)}
      >
        <span className="trip-details-activity-name">{item.name}</span>
        {item.description ? (
          <span
            className="trip-details-activity-description"
            lang={item.description_language_code || undefined}
          >
            {item.description}
          </span>
        ) : null}
        {item.address ? <span className="trip-details-activity-meta">{item.address}</span> : null}
        {rating ? <span className="trip-details-activity-meta">{rating}</span> : null}
        {status ? <span className="trip-details-activity-meta">{status}</span> : null}
        {priceLevel ? <span className="trip-details-activity-meta">Price level: {priceLevel}</span> : null}
        {!activityPosition(item) ? <span className="trip-details-activity-meta">Map location unavailable</span> : null}
      </button>
      {placeId ? (
        <button
          type="button"
          className={
            liked ? 'trip-details-activity-like trip-details-activity-like-on' : 'trip-details-activity-like'
          }
          aria-pressed={liked}
          aria-label={label}
          disabled={pending}
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
            onToggleLike?.(placeId)
          }}
        >
          <Heart size={18} strokeWidth={2} fill={liked ? 'currentColor' : 'none'} aria-hidden="true" />
        </button>
      ) : null}
    </li>
  )
}

export default function TripDetailsActivities({
  destination,
  moods,
  enabled = false,
  titleId,
  onActivitiesChange,
  selectedActivityId,
  onSelectActivity,
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
  const { likedIds, pendingIds, likeError, persistenceNote, toggleLike } = useActivityLikes()

  const handleToggleLike = (placeId) => {
    const activity = state.activities.find((item) => item.place_id === placeId)
    toggleLike(
      placeId,
      activity ? { activity, city, countryCode, destinationId } : undefined,
    )
  }

  if (appliedKey !== sessionKey) {
    setAppliedKey(sessionKey)
    setRetry(0)
    setState(stateForRequest({ visible, payload }))
  }

  useEffect(() => {
    onActivitiesChange?.(state)
  }, [state, onActivitiesChange])

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
      likedIds={likedIds}
      pendingIds={pendingIds}
      likeError={likeError}
      persistenceNote={visible ? persistenceNote : ''}
      onToggleLike={handleToggleLike}
      selectedActivityId={selectedActivityId}
      onSelectActivity={onSelectActivity}
    />
  )
}
