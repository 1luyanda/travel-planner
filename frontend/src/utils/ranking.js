// Preset weight sets applied when the user clicks a refinement button.
export const refinementPresets = {
  Cheaper: { price: 0.5, weather: 0.2, stops: 0.15, duration: 0.15 },
  Warmer: { price: 0.2, weather: 0.5, stops: 0.15, duration: 0.15 },
  'Direct flights': { price: 0.2, weather: 0.25, stops: 0.4, duration: 0.15 },
  'Shorter travel': { price: 0.2, weather: 0.25, stops: 0.15, duration: 0.4 },
}

/** Initial ranking weights. Weather only counts when warmer weather is preferred. */
export function defaultWeights(preferWarm) {
  return preferWarm
    ? { price: 0.3, weather: 0.35, stops: 0.2, duration: 0.15 }
    : { price: 0.45, weather: 0, stops: 0.3, duration: 0.25 }
}

export function uniqueOrigins(destinations) {
  return [...new Set(destinations.map((item) => item.originId).filter(Boolean))].sort()
}

/**
 * Keep destinations that match origin_id, max EUR budget, and optional direct-only.
 * Origin is required: an empty origin_id matches nothing.
 * Warm preference is not a hard filter; it only changes ranking weights.
 * Missing numeric fields stay missing in the record; score helpers treat them as 0
 * so a gap is not filled with invented prices, temperatures, or durations.
 */
export function filterDestinations(destinations, filters) {
  return destinations.filter((item) => {
    const flight = item.flight || {}
    if (!filters.originId || item.originId !== filters.originId) {
      return false
    }

    if (filters.maxBudget != null && filters.maxBudget !== '' && Number(flight.price) > Number(filters.maxBudget)) {
      return false
    }

    if (filters.directOnly && flight.outbound_stops !== 0) {
      return false
    }

    return true
  })
}

function minMax(values) {
  let min = Infinity
  let max = -Infinity

  for (const value of values) {
    if (value == null || Number.isNaN(Number(value))) continue
    const numeric = Number(value)
    if (numeric < min) min = numeric
    if (numeric > max) max = numeric
  }

  if (!Number.isFinite(min)) {
    return { min: 0, max: 0 }
  }

  return { min, max }
}

// Min-max normalisation to 0–1. Equal values all score 1 so a flat set is not penalised.
function higherIsBetter(value, min, max) {
  if (value == null || Number.isNaN(Number(value))) return 0
  if (max === min) return 1
  return (Number(value) - min) / (max - min)
}

function lowerIsBetter(value, min, max) {
  if (value == null || Number.isNaN(Number(value))) return 0
  if (max === min) return 1
  return 1 - (Number(value) - min) / (max - min)
}

function withoutScores(destination) {
  const { scores, ...rest } = destination
  return rest
}

/** Rank adapted candidates exactly once with the current weight set. */
export function applyBrowserRanking(destinations, preferWarm, refinement = null) {
  const weights =
    refinement && refinementPresets[refinement]
      ? refinementPresets[refinement]
      : defaultWeights(preferWarm)
  return { weights, ranked: rankDestinations(destinations, weights) }
}

/**
 * Score each destination against the current filtered set, then sort highest first.
 * Cheaper, fewer stops, and shorter duration score higher; warmer weather scores higher
 * when that weight is non-zero. Refinement only changes `weights` and calls this again.
 */
export function rankDestinations(destinations, weights) {
  const plain = destinations.map(withoutScores)
  const priceRange = minMax(plain.map((item) => item.flight?.price))
  const tempRange = minMax(plain.map((item) => item.weather?.average_max_temperature_c))
  const stopsRange = minMax(plain.map((item) => item.flight?.outbound_stops))
  const durationRange = minMax(plain.map((item) => item.flight?.duration_minutes))

  return plain
    .map((destination) => {
      const priceScore = lowerIsBetter(destination.flight?.price, priceRange.min, priceRange.max)
      const weatherScore = higherIsBetter(
        destination.weather?.average_max_temperature_c,
        tempRange.min,
        tempRange.max,
      )
      const stopsScore = lowerIsBetter(destination.flight?.outbound_stops, stopsRange.min, stopsRange.max)
      const durationScore = lowerIsBetter(destination.flight?.duration_minutes, durationRange.min, durationRange.max)
      const total =
        priceScore * weights.price +
        weatherScore * weights.weather +
        stopsScore * weights.stops +
        durationScore * weights.duration

      return {
        ...destination,
        scores: {
          price: priceScore,
          weather: weatherScore,
          stops: stopsScore,
          duration: durationScore,
          total,
        },
      }
    })
    .sort((a, b) => b.scores.total - a.scores.total)
}

export function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

/** One-line reason from the highest weighted contribution. */
export function rankingReason(destination, weights = {}) {
  const rows = scoreBreakdown(destination, weights)
    .filter((item) => Number(item.weight) > 0)
    .sort((a, b) => b.contribution - a.contribution)
  const top = rows[0]
  if (!top) return null
  const name = top.label.replace(/\s*\(.*\)$/, '').toLowerCase()
  return `Weighted score favours ${name}.`
}

/** Turn stored scores and current weights into labelled contribution rows for the UI. */
export function scoreBreakdown(destination, weights = {}) {
  const scores = destination?.scores || {}
  return [
    { key: 'price', label: 'Price (cheaper is better)', score: scores.price, weight: weights.price },
    { key: 'weather', label: 'Weather (warmer is better)', score: scores.weather, weight: weights.weather },
    { key: 'stops', label: 'Stops (fewer is better)', score: scores.stops, weight: weights.stops },
    { key: 'duration', label: 'Duration (shorter is better)', score: scores.duration, weight: weights.duration },
  ].map((item) => ({
    ...item,
    contribution: (Number(item.score) || 0) * (Number(item.weight) || 0),
  }))
}
