import { getDestinationImage } from '../data/destinationImages'

export function resolveDestinationPhoto(destination) {
  const city = destination?.destination?.city || ''
  const apiSrc = destination?.photoUrlSmall || destination?.photoUrl || null
  if (apiSrc) return { kind: 'api', src: apiSrc }
  const bundled = getDestinationImage(city)
  if (bundled) return { kind: 'bundled', src: bundled.src }
  return { kind: 'fallback', src: null }
}
