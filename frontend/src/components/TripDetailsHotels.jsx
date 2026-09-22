import { useEffect, useRef, useState } from 'react'
import { fetchHotels } from '../services/travelApi'
import { createHotelsLoader, formatHotelDistance, officialWebsite } from '../utils/hotels'
import { hotelKey, hotelPosition } from '../utils/hotelMarkers'
import TripDetailsSection from './TripDetailsSection'

const EMPTY_MESSAGE = 'No hotel recommendations available for this destination.'

export function TripDetailsHotelsView({ titleId, state, onRetry, selectedHotelId, onSelectHotel }) {
  const headingId = `${titleId}-hotels`
  return (
    <TripDetailsSection title="Hotels" headingId={headingId} defaultExpanded>
      {state.status === 'loading' && (
        <p className="trip-details-activities-status" aria-live="polite" aria-busy="true">
          Loading hotels...
        </p>
      )}
      {(state.status === 'unavailable' || (state.status === 'ready' && !state.hotels.length)) && (
        <p className="trip-details-activities-status">{EMPTY_MESSAGE}</p>
      )}
      {state.status === 'error' && (
        <div className="trip-details-activities-error">
          <p className="trip-details-activities-status" role="alert">
            Hotel recommendations are temporarily unavailable.
          </p>
          {onRetry && (
            <button type="button" className="trip-details-activities-retry" onClick={onRetry}>
              Retry
            </button>
          )}
        </div>
      )}
      {state.status === 'ready' && state.hotels.length > 0 && (
        <>
          <ul className="trip-details-activity-list">
            {state.hotels.map((hotel) => {
              const website = officialWebsite(hotel.website)
              const id = hotelKey(hotel)
              const selected = selectedHotelId === id
              return (
                <li className={`trip-details-activity-card trip-details-hotel-card${selected ? ' is-selected' : ''}`} key={id}>
                  <button type="button" className="trip-details-hotel-select"
                    aria-pressed={selected} onClick={() => onSelectHotel?.(id)}>
                    <span className="trip-details-activity-name">{hotel.name}</span>
                    {Number.isInteger(hotel.stars) && hotel.stars > 0 && (
                      <span className="trip-details-activity-meta">{hotel.stars} {hotel.stars === 1 ? 'star' : 'stars'}</span>
                    )}
                    <span className="trip-details-activity-meta">
                      Approx. {formatHotelDistance(hotel.distance_km)} from destination centre
                    </span>
                    {!hotelPosition(hotel) && <span className="trip-details-activity-meta">Map location unavailable</span>}
                  </button>
                  {website && (
                    <p className="trip-details-activity-meta">
                      <a href={website} target="_blank" rel="noopener noreferrer">Official website</a>
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
          <p className="trip-details-activity-meta">Distances are approximate and measured in a straight line.</p>
          {state.attribution && <p className="trip-details-activity-meta">{state.attribution}</p>}
        </>
      )}
    </TripDetailsSection>
  )
}

/** Mounted only inside selected Trip Details; the parent keys this by hotel ID. */
export default function TripDetailsHotels({ destinationId, titleId, onHotelsChange, selectedHotelId, onSelectHotel }) {
  const [state, setState] = useState({
    status: destinationId ? 'loading' : 'unavailable', hotels: [], attribution: null,
  })
  const [retry, setRetry] = useState(0)
  const loaderRef = useRef(null)
  if (!loaderRef.current) loaderRef.current = createHotelsLoader({ fetchHotels })

  useEffect(() => {
    const loader = loaderRef.current
    loader.run({ destinationId, onChange: setState })
    return () => loader.cancel()
  }, [destinationId, retry])

  useEffect(() => {
    onHotelsChange?.(state)
  }, [state, onHotelsChange])

  return (
    <TripDetailsHotelsView
      titleId={titleId}
      state={state}
      selectedHotelId={selectedHotelId}
      onSelectHotel={onSelectHotel}
      onRetry={state.status === 'error' ? () => setRetry((value) => value + 1) : undefined}
    />
  )
}
