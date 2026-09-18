import { useEffect, useState } from 'react'
import { cityTone } from '../utils/format'
import { destinationPhotoAlt, resolveDestinationPhoto } from '../utils/photos'
import styles from '../workspace.module.css'

/**
 * Photo order: API url, exact bundled city match, then a teal placeholder.
 * Never uses another destination's image.
 */
export default function DestinationPhoto({ destination, className, sizes = '320px' }) {
  const city = destination?.destination?.city || 'Destination'
  const resolved = resolveDestinationPhoto(destination)
  const src = resolved.src
  const alt = destinationPhotoAlt(destination, resolved)
  const title = resolved.kind === 'api' ? 'Stored city photo' : resolved.attribution
  const [failedSrc, setFailedSrc] = useState(null)
  const destinationId = destination?.id
  const failed = Boolean(src) && failedSrc === src

  useEffect(() => {
    setFailedSrc(null)
  }, [destinationId])

  if (!src || failed) {
    return (
      <div
        className={`${styles.photoFallback} ${className || ''}`}
        style={{ '--tone': cityTone(city) }}
        role="img"
        aria-label={city}
      >
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
      width={640}
      height={400}
      loading="lazy"
      decoding="async"
      sizes={sizes}
      onError={() => setFailedSrc(src)}
    />
  )
}
