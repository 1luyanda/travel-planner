import { useState } from 'react'
import { getDestinationImage } from '../data/destinationImages'
import styles from '../workspace.module.css'

/**
 * Local demo photo with a named colour fallback from mock flag data.
 * Image metadata stays out of the destination records.
 */
export default function DestinationPhoto({ destination, className, sizes = '320px' }) {
  const city = destination?.destination?.city || 'Destination'
  const image = getDestinationImage(city)
  const [failed, setFailed] = useState(false)
  const fallbackColor = destination?.country?.flag?.colors?.dominant || '#1b3354'

  if (!image || failed) {
    return (
      <div className={`${styles.photoFallback} ${className || ''}`} style={{ background: fallbackColor }}>
        <span>{city}</span>
      </div>
    )
  }

  return (
    <img
      className={`${styles.photo} ${className || ''}`}
      src={image.src}
      alt={image.alt}
      title={image.attribution}
      loading="lazy"
      sizes={sizes}
      onError={() => setFailed(true)}
    />
  )
}
