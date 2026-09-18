import { getDestinationImage } from '../data/destinationImages'

export function resolveDestinationPhoto(destination) {
  const city = destination?.destination?.city || ''
  const apiSrc = destination?.photoUrlSmall || destination?.photoUrl || null
  if (apiSrc) return { kind: 'api', src: apiSrc }
  const bundled = getDestinationImage(city)
  if (bundled) return { kind: 'bundled', src: bundled.src, alt: bundled.alt, attribution: bundled.attribution }
  return { kind: 'fallback', src: null }
}

export function destinationPhotoAlt(destination, resolved) {
  if (resolved?.kind === 'bundled' && resolved.alt) return resolved.alt
  const city = destination?.destination?.city
  const country = destination?.country?.common_name
  if (city && country) return `Photo of ${city}, ${country}`
  if (city) return `Photo of ${city}`
  return 'Destination photo'
}
