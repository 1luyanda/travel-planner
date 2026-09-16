import { useState } from 'react'
import { getDestinationImage } from '../data/destinationImages'
import { resolveDestinationPhoto } from '../utils/photos'
import styles from '../workspace.module.css'

/**
 * Photo order: API url, exact bundled city match, then a neutral placeholder.
 * Never uses another destination's image.
 */
export default function DestinationPhoto({ destination, className, sizes = '320px' }) {
  const city = destination?.destination?.city || 'Destination'
  const resolved = resolveDestinationPhoto(destination)
  const bundled = getDestinationImage(city)
  const src = resolved.src
  const alt = resolved.kind === 'api' ? city : bundled?.alt || city
  const title = resolved.kind === 'api' ? 'Stored city photo' : bundled?.attribution
  const [failed, setFailed] = useState(false)

  if (!src || failed) {
    return (
      <div className={`${styles.photoFallback} ${className || ''}`}>
        <span>{city}</span>
      </div>
    )
  }

  return (
    <img
      className={`${styles.photo} ${className || ''}`}
      src={src}
      alt={alt}
      title={title}
      loading="lazy"
      sizes={sizes}
      onError={() => setFailed(true)}
    />
  )
}
