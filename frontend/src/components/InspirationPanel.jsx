import { formatPrice } from '../utils/format'
import { workspaceImages } from '../data/destinationImages'
import DestinationPhoto from './DestinationPhoto'
import styles from '../workspace.module.css'

export default function InspirationPanel({ destinations, onPlan, onExplore, onSelectDestination }) {
  const previews = destinations.slice(0, 4)

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
        <h3>Explore destinations</h3>
        <p className={styles.panelHint}>
          Choose a departure city first, then search. Previews come from stored snapshot trips, not live fares.
        </p>
        <div className={styles.previews}>
          {previews.map((destination) => {
            const city = destination.destination?.city || 'Destination'
            const country = destination.country?.common_name
            return (
              <button
                key={destination.id}
                type="button"
                className={styles.preview}
                onClick={() => onSelectDestination(destination)}
              >
                <DestinationPhoto destination={destination} sizes="180px" />
                <span>
                  <strong>{city}</strong>
                  {country && <em>{country}</em>}
                  {formatPrice(destination.flight) && <b>{formatPrice(destination.flight)}</b>}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
