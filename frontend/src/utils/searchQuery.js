const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export function isIsoDate(value) {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

function optionalNumber(value, { integer = false, min = null, exclusiveMin = null } = {}) {
  if (value == null || value === '') return undefined
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return undefined
  if (integer && !Number.isInteger(numeric)) return undefined
  if (min != null && numeric < min) return undefined
  if (exclusiveMin != null && numeric <= exclusiveMin) return undefined
  return numeric
}

/**
 * Build `/api/candidates` query params from the planner form.
 * `origin_id` is the Cosmos origin document id (e.g. zagreb-hr), never an IATA code.
 */
export function buildCandidateQuery(form = {}) {
  const originId = typeof form.originId === 'string' ? form.originId.trim().toLowerCase() : ''
  if (originId.length < 3) return null
  // Origin ids are city-country slugs such as zagreb-hr. A bare 3-letter IATA code is not origin_id.
  if (/^[a-z]{3}$/.test(originId)) return null

  const query = { origin_id: originId }

  const departure = isIsoDate(form.departureDate) ? form.departureDate : null
  const returnDate = isIsoDate(form.returnDate) ? form.returnDate : null
  if (departure && returnDate && returnDate < departure) {
    // Invalid range: omit both rather than send a request the API will reject.
  } else {
    if (departure) query.departure_date = departure
    if (returnDate) query.return_date = returnDate
  }

  const maxPrice = optionalNumber(form.maxBudget, { exclusiveMin: 0 })
  if (maxPrice != null) query.max_price = maxPrice

  const minTemp = optionalNumber(form.minTemp)
  if (minTemp != null) query.min_temp = minTemp

  const country = typeof form.country === 'string' ? form.country.trim().toUpperCase() : ''
  if (country.length === 2) query.country = country

  if (form.directOnly === true) query.max_changeovers = 0
  else {
    const changeovers = optionalNumber(form.maxChangeovers, { integer: true, min: 0 })
    if (changeovers != null) query.max_changeovers = changeovers
  }

  const duration = optionalNumber(form.maxDurationMinutes, { integer: true, exclusiveMin: 0 })
  if (duration != null) query.max_duration_minutes = duration

  return query
}

/** `/api/flights` does not accept max_changeovers or max_duration_minutes. */
export function buildFlightQuery(candidateQuery) {
  if (!candidateQuery?.origin_id) return null
  const { max_changeovers, max_duration_minutes, ...rest } = candidateQuery
  return rest
}
