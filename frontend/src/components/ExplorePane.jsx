import { useEffect, useRef, useState } from 'react'
import { Heart, LocateFixed } from 'lucide-react'
import { fetchNearbyActivities } from '../services/travelApi'
import { useActivityLikes } from '../utils/useActivityLikes'
import { cityTone } from '../utils/format'
import { formatActivityBusinessStatus, formatActivityRating } from '../utils/activities'
import {
  EXPLORE_CATEGORIES,
  EXPLORE_RADIUS_METERS,
  activityPhotoUrl,
  createExploreSearch,
  exploreCategory,
  exploreHeading,
  exploreSeedFromTrip,
  formatActivityTypes,
  formatSearchRadius,
  formatStraightLineDistance,
  locationErrorMessage,
  nearbyActivitiesPayload,
  straightLineKm,
} from '../utils/explore'
import styles from '../workspace.module.css'

const INITIAL_RESULTS = {
  status: 'idle',
  activities: [],
  error: '',
  issues: [],
  radiusMeters: null,
  searchCenter: null,
  attribution: null,
  heading: '',
}

function ActivityPhoto({ name, label }) {
  const src = activityPhotoUrl(name)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [name])

  if (!src || failed) {
    return (
      <div
        className={`${styles.photoFallback} ${styles.explorePhoto}`}
        style={{ '--tone': cityTone(label) }}
        role="img"
        aria-label={label}
      >
        <span>{label}</span>
      </div>
    )
  }

  return (
    <img
      className={`${styles.photo} ${styles.explorePhoto}`}
      src={src}
      alt={`Photo of ${label}`}
      width={640}
      height={400}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  )
}

export function ExploreView({
  city,
  onCityChange,
  categoryId,
  onCategoryChange,
  heading,
  radiusLabel,
  locating = false,
  locationError = '',
  onUseLocation,
  onSearch,
  canSearch = false,
  results,
  onRetry,
  likedIds,
  pendingIds,
  likeError = '',
  persistenceNote = '',
  onToggleLike,
}) {
  const status = results?.status || 'idle'
  const liked = likedIds instanceof Set ? likedIds : new Set(likedIds || [])
  const pending = pendingIds instanceof Set ? pendingIds : new Set(pendingIds || [])
  const activities = Array.isArray(results?.activities) ? results.activities : []
  const radius = radiusLabel || formatSearchRadius(results?.radiusMeters) || formatSearchRadius(EXPLORE_RADIUS_METERS)
  const emptyMessage = results?.issues?.[0] || (radius ? `No activities found within ${radius}.` : 'No activities found.')

  return (
    <div className={styles.explore}>
      <div className={styles.exploreIntro}>
        <h1>{heading}</h1>
        <p>Search activities and attractions. Results use Google Maps ranking.</p>
      </div>

      <form
        className={styles.exploreControls}
        onSubmit={(event) => {
          event.preventDefault()
          if (canSearch) onSearch?.()
        }}
      >
        <label className={styles.exploreField} htmlFor="explore-city">
          City
          <input
            id="explore-city"
            type="text"
            value={city}
            autoComplete="off"
            placeholder="Type any city"
            onChange={(event) => onCityChange?.(event.target.value)}
          />
        </label>
        <label className={styles.exploreField} htmlFor="explore-category">
          Category
          <select
            id="explore-category"
            value={categoryId}
            onChange={(event) => onCategoryChange?.(event.target.value)}
          >
            {EXPLORE_CATEGORIES.map((category) => (
              <option key={category.id} value={category.id}>
                {category.label}
              </option>
            ))}
          </select>
        </label>
        <div className={styles.exploreActions}>
          <button type="submit" className={styles.primaryBtn} disabled={!canSearch || locating || status === 'loading'}>
            {radius ? `Search within ${radius}` : 'Search'}
          </button>
          <button type="button" className={styles.secondaryBtn} onClick={onUseLocation} disabled={locating}>
            <LocateFixed size={16} aria-hidden="true" />
            {locating ? 'Finding location…' : 'Use my location'}
          </button>
        </div>
        {locationError ? (
          <p className={styles.noticeError} role="alert">
            {locationError}
          </p>
        ) : null}
        <p className={styles.exploreMapNote}>
          Place results stay in this list. They are not shown on the OpenStreetMap map used for trips.
        </p>
      </form>

      {persistenceNote ? <p className={styles.exploreNote}>{persistenceNote}</p> : null}
      {likeError ? (
        <p className={styles.noticeError} role="alert">
          {likeError}
        </p>
      ) : null}

      {status === 'idle' ? (
        <p className={styles.exploreStatus}>Choose a city or use your location, then search.</p>
      ) : null}
      {status === 'loading' ? (
        <p className={styles.exploreStatus} aria-live="polite" aria-busy="true">
          Searching for activities…
        </p>
      ) : null}
      {status === 'error' ? (
        <div className={styles.exploreError}>
          <p className={styles.noticeError} role="alert">
            {results.error || 'Activity data is temporarily unavailable.'}
          </p>
          {onRetry ? (
            <button type="button" className={styles.secondaryBtn} onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      ) : null}
      {status === 'ready' && !activities.length ? <p className={styles.exploreStatus}>{emptyMessage}</p> : null}
      {status === 'ready' && activities.length ? (
        <ul className={styles.exploreList}>
          {activities.map((item) => (
            <ExploreCard
              key={item.place_id}
              item={item}
              searchCenter={results.searchCenter}
              liked={liked.has(item.place_id)}
              pending={pending.has(item.place_id)}
              onToggleLike={onToggleLike}
            />
          ))}
        </ul>
      ) : null}
      {status === 'ready' && results?.attribution ? (
        <p className={styles.mapsAttribution} translate="no">
          {results.attribution}
        </p>
      ) : null}
    </div>
  )
}

function ExploreCard({ item, searchCenter, liked = false, pending = false, onToggleLike }) {
  const rating = formatActivityRating(item.rating, item.user_ratings_total)
  const status = formatActivityBusinessStatus(item.business_status)
  const categories = formatActivityTypes(item.types)
  const distance = formatStraightLineDistance(straightLineKm(searchCenter, item))
  const placeUri = item.google_maps_uri
  const photoUri = item.photo?.google_maps_uri
  const label = liked ? `Unlike ${item.name}` : `Like ${item.name}`

  return (
    <li className={styles.exploreCard}>
      <ActivityPhoto name={item.photo?.name} label={item.name} />
      <div className={styles.exploreCardBody}>
        <h2>{item.name}</h2>
        {categories.length ? <p>{categories.join(' · ')}</p> : null}
        {item.address ? <p>{item.address}</p> : null}
        {rating ? <p>{rating}</p> : null}
        {status ? <p>{status}</p> : null}
        {distance ? <p>{distance}</p> : null}
        {placeUri ? (
          <a href={placeUri} target="_blank" rel="noopener noreferrer">
            View on Google Maps
          </a>
        ) : null}
        {photoUri && photoUri !== placeUri ? (
          <a href={photoUri} target="_blank" rel="noopener noreferrer">
            View photo on Google Maps
          </a>
        ) : null}
        <PhotoAuthors authors={item.photo?.author_attributions} />
      </div>
      <button
        type="button"
        className={liked ? styles.exploreLikeOn : styles.exploreLike}
        aria-pressed={liked}
        aria-label={label}
        disabled={pending}
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
          onToggleLike?.(item.place_id)
        }}
      >
        <Heart size={18} strokeWidth={2} fill={liked ? 'currentColor' : 'none'} aria-hidden="true" />
      </button>
    </li>
  )
}

function PhotoAuthors({ authors = [] }) {
  if (!authors?.length) return null
  return (
    <div className={styles.exploreAuthors}>
      {authors.map((author) => {
        const name = author.display_name || 'Photo author'
        const key = `${name}-${author.uri || author.photo_uri || ''}`
        return (
          <p key={key}>
            {author.photo_uri ? (
              <img src={author.photo_uri} alt="" width="24" height="24" />
            ) : null}
            {author.uri ? (
              <a href={author.uri} target="_blank" rel="noopener noreferrer">
                Photo: {name}
              </a>
            ) : (
              <span>Photo: {name}</span>
            )}
          </p>
        )
      })}
    </div>
  )
}

export default function ExplorePane({ selectedTrip = null }) {
  const seed = exploreSeedFromTrip(selectedTrip)
  const [city, setCity] = useState(() => seed?.city || '')
  const [countryCode, setCountryCode] = useState(() => seed?.countryCode || '')
  const [centre, setCentre] = useState(() => seed?.centre || null)
  const [categoryId, setCategoryId] = useState(EXPLORE_CATEGORIES[0].id)
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [results, setResults] = useState(INITIAL_RESULTS)
  const [appliedHeading, setAppliedHeading] = useState('')
  const searchRef = useRef(null)
  const payloadRef = useRef(null)
  const mountedRef = useRef(true)
  const { likedIds, pendingIds, likeError, persistenceNote, toggleLike } = useActivityLikes()

  if (!searchRef.current) {
    searchRef.current = createExploreSearch({ fetchNearby: fetchNearbyActivities })
  }

  useEffect(() => {
    mountedRef.current = true
    const search = searchRef.current
    return () => {
      mountedRef.current = false
      search.cancel()
    }
  }, [])

  const heading = appliedHeading || exploreHeading({ source: centre?.source, city })
  const canSearch = Boolean(centre?.source === 'device' || city.trim())

  function handleCityChange(value) {
    setCity(value)
    setCountryCode('')
    setCentre(null)
    setLocationError('')
  }

  function handleUseLocation() {
    setLocationError('')
    if (!navigator.geolocation) {
      setLocationError(locationErrorMessage({ code: 2 }))
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!mountedRef.current) return
        const latitude = position?.coords?.latitude
        const longitude = position?.coords?.longitude
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
          setLocating(false)
          setLocationError(locationErrorMessage({ code: 2 }))
          return
        }
        setCentre({ source: 'device', latitude, longitude })
        setLocating(false)
      },
      (error) => {
        if (!mountedRef.current) return
        setLocating(false)
        setLocationError(locationErrorMessage(error))
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 },
    )
  }

  function runSearch(payload, nextHeading) {
    payloadRef.current = payload
    setAppliedHeading(nextHeading)
    searchRef.current.run(payload, (patch) => {
      setResults((current) => ({
        ...current,
        activities: [],
        error: '',
        issues: [],
        ...patch,
      }))
    })
  }

  function handleSearch() {
    const usingDevice = centre?.source === 'device'
    const payload = nearbyActivitiesPayload({
      city: usingDevice ? '' : city,
      countryCode: usingDevice ? '' : countryCode,
      latitude: centre?.latitude,
      longitude: centre?.longitude,
      types: exploreCategory(categoryId).types,
    })
    if (!payload) return
    runSearch(payload, exploreHeading({ source: usingDevice ? 'device' : 'city', city }))
  }

  function handleRetry() {
    if (!payloadRef.current) return
    runSearch(payloadRef.current, appliedHeading)
  }

  function handleToggleLike(placeId) {
    const activity = results.activities.find((item) => item.place_id === placeId)
    const searched = payloadRef.current
    toggleLike(
      placeId,
      activity
        ? {
            activity,
            city: typeof searched?.city === 'string' ? searched.city : city,
            countryCode: searched?.country_code || countryCode,
          }
        : undefined,
    )
  }

  return (
    <ExploreView
      city={city}
      onCityChange={handleCityChange}
      categoryId={categoryId}
      onCategoryChange={setCategoryId}
      heading={heading}
      locating={locating}
      locationError={locationError}
      onUseLocation={handleUseLocation}
      onSearch={handleSearch}
      canSearch={canSearch}
      results={results}
      onRetry={results.status === 'error' ? handleRetry : undefined}
      likedIds={likedIds}
      pendingIds={pendingIds}
      likeError={likeError}
      persistenceNote={persistenceNote}
      onToggleLike={handleToggleLike}
    />
  )
}
