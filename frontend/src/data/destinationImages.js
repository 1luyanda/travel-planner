import rome from '../assets/rome.jpg'
import malta from '../assets/malta.jpg'
import lisbon from '../assets/lisbon.jpg'
import athens from '../assets/athens.jpg'
import tileGetaway from '../assets/tile-getaway.jpg'
import tileExplore from '../assets/tile-explore.jpg'
import welcomeMark from '../assets/welcome-mark.png'

/**
 * Presentation-only images. Keys are city names from the mock records.
 * These assets are not part of normalized_destinations.json.
 */
const byCity = {
  rome: {
    src: rome,
    alt: 'The Colosseum in Rome at golden hour',
    attribution: 'Original demo illustration',
  },
  malta: {
    src: malta,
    alt: 'Harbour buildings in Valletta, Malta',
    attribution: 'Original demo illustration',
  },
  lisbon: {
    src: lisbon,
    alt: 'A yellow tram on a Lisbon street',
    attribution: 'Original demo illustration',
  },
  athens: {
    src: athens,
    alt: 'The Parthenon on the Acropolis in Athens',
    attribution: 'Original demo illustration',
  },
}

export const workspaceImages = {
  welcomeMark: {
    src: welcomeMark,
    alt: 'Small travel landmarks illustration',
    attribution: 'Original demo illustration',
  },
  tileGetaway: {
    src: tileGetaway,
    alt: 'Colourful van and flamingo illustration for planning a getaway',
    attribution: 'Original demo illustration',
  },
  tileExplore: {
    src: tileExplore,
    alt: 'Colourful archway illustration for exploring destinations',
    attribution: 'Original demo illustration',
  },
}

export function getDestinationImage(city = '') {
  return byCity[city.trim().toLowerCase()] || null
}

/** Stable city keys that have bundled planner photos. */
export function bundledInspirationCities() {
  return Object.keys(byCity).sort((left, right) => left.localeCompare(right))
}
