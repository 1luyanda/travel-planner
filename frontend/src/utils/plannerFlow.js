/**
 * Planner orchestration helpers for POST /api/recommend and /api/refine.
 * Ranking stays on the backend. These functions only map UI state to the
 * Pydantic RecommendRequest / RefineRequest / RecommendationResponse fields.
 */

const IATA = /^[A-Za-z]{3}$/
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export const REFINEMENT_ACTIONS = [
  { label: 'Cheaper', text: 'Cheaper' },
  { label: 'Warmer', text: 'Warmer' },
  { label: 'Direct flights', text: 'Direct' },
  { label: 'Shorter travel', text: 'Shorter' },
]

export const INITIAL_PLANNER_FORM = {
  originId: '',
  originIata: '',
  maxBudget: 400,
  directOnly: false,
  preferWarm: false,
  mood: '',
  currency: 'EUR',
}

const FORM_FIELD_LABELS = [
  ['origin', 'origin'],
  ['departure_date', 'departure date'],
  ['return_date', 'return date'],
  ['duration_days', 'duration days'],
  ['budget', 'budget'],
  ['currency', 'currency'],
  ['moods', 'moods'],
  ['direct_flights_only', 'direct flights only'],
  ['weather_preference', 'weather preference'],
]

export function isIsoDate(value) {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

function trimText(value) {
  if (value == null) return ''
  return String(value).trim()
}

/**
 * Map the planner form onto backend FORM_FIELD_NAMES.
 * Does not invent dates, origin IATA codes, or ranking weights.
 */
export function formFieldsFromPlanner(form = {}, origin = null) {
  const fields = {}
  const iata = trimText(origin?.iata || form.originIata)
  if (IATA.test(iata)) fields.origin = iata.toUpperCase()

  const sendBudget = form.budgetTouched === true || form.includeBudget === true
  if (sendBudget) {
    const budget = Number(form.maxBudget)
    if (Number.isFinite(budget) && budget > 0) fields.budget = budget
    const currency = trimText(form.currency || 'EUR')
    if (/^[A-Za-z]{3}$/.test(currency)) fields.currency = currency.toUpperCase()
  }

  if (form.directOnly === true) fields.direct_flights_only = true
  if (form.preferWarm === true) fields.weather_preference = 'warmer'

  if (isIsoDate(form.departureDate)) fields.departure_date = form.departureDate
  if (isIsoDate(form.returnDate)) fields.return_date = form.returnDate

  const moods = Array.isArray(form.moods) ? form.moods.map(trimText).filter(Boolean) : []
  if (moods.length) fields.moods = moods

  return Object.keys(fields).length ? fields : null
}

export function buildRecommendPayload(text, form, origin) {
  const payload = { text: typeof text === 'string' ? text : '' }
  const formFields = formFieldsFromPlanner(form, origin)
  if (formFields) payload.form_fields = formFields
  return payload
}

export function buildRefinePayload(text, tripRequest) {
  return {
    text: typeof text === 'string' ? text : '',
    request: tripRequest,
  }
}

export function describeFormFields(formFields) {
  if (!formFields || typeof formFields !== 'object') return ''
  const lines = []
  for (const [key, label] of FORM_FIELD_LABELS) {
    if (!(key in formFields) || formFields[key] == null || formFields[key] === '') continue
    const raw = formFields[key]
    const value = Array.isArray(raw) ? raw.filter(Boolean).join(', ') : String(raw)
    if (!value.trim()) continue
    lines.push(`${label}: ${value}`)
  }
  return lines.join('\n')
}

export function createClarificationContext({ originalPrompt, formFields, questions = [] } = {}) {
  return {
    originalPrompt: trimText(originalPrompt),
    formSelectionsText: describeFormFields(formFields),
    questions: Array.isArray(questions) ? questions.filter(Boolean) : [],
    previousAnswers: [],
  }
}

export function recordClarificationAnswer(context, answer, questions = []) {
  const current = context || createClarificationContext()
  const nextAnswer = trimText(answer)
  return {
    ...current,
    questions: Array.isArray(questions) ? questions.filter(Boolean) : [],
    previousAnswers: nextAnswer
      ? [...(current.previousAnswers || []), nextAnswer]
      : [...(current.previousAnswers || [])],
  }
}

/**
 * Clarification follow-up for POST /api/recommend.
 * Puts initial form values in the text so they are not resent as stale form_fields.
 * The latest user answer is labeled authoritative and overrides conflicts.
 */
export function buildClarificationRecommendPayload({
  originalPrompt,
  formSelectionsText,
  previousAnswers = [],
  questions = [],
  answer,
} = {}) {
  const sections = []
  const prompt = trimText(originalPrompt)
  if (prompt) sections.push(`Original request:\n${prompt}`)

  const formText = trimText(formSelectionsText)
  if (formText) sections.push(`Initial form selections:\n${formText}`)

  const earlier = (previousAnswers || []).map(trimText).filter(Boolean)
  if (earlier.length) {
    sections.push(`Earlier clarifications:\n${earlier.map((item) => `- ${item}`).join('\n')}`)
  }

  const asked = (questions || []).map(trimText).filter(Boolean)
  if (asked.length) sections.push(`The planner asked:\n${asked.join('\n')}`)

  const latest = trimText(answer)
  if (latest) {
    sections.push(
      `Authoritative answer (this overrides any conflicting initial form values):\n${latest}`,
    )
  }

  return { text: sections.join('\n\n') }
}

export function newTripPlannerState() {
  return {
    tripRequest: null,
    clarification: null,
    clarifyKind: null,
    clarificationQuestions: [],
    pendingSearchText: '',
    results: [],
    rejected: [],
    error: '',
    appliedFilters: null,
    form: { ...INITIAL_PLANNER_FORM },
  }
}

export function tripRequestAfterRecommend(current, response) {
  if (response?.status === 'ready' && response.request) return response.request
  return current ?? null
}

export function tripRequestAfterRefine(current, response) {
  if (response?.status === 'ready' && response.updated_request) return response.updated_request
  return current ?? null
}

export function formPatchFromTripRequest(trip) {
  if (!trip || typeof trip !== 'object') return {}
  const patch = {}
  if (typeof trip.origin === 'string' && trip.origin.trim()) patch.originIata = trip.origin.trim()
  if (trip.budget != null && Number.isFinite(Number(trip.budget))) patch.maxBudget = Number(trip.budget)
  if (typeof trip.direct_flights_only === 'boolean') patch.directOnly = trip.direct_flights_only
  if (typeof trip.weather_preference === 'string') {
    patch.preferWarm = /warm/i.test(trip.weather_preference)
  }
  if (typeof trip.departure_date === 'string') patch.departureDate = trip.departure_date
  if (typeof trip.return_date === 'string') patch.returnDate = trip.return_date
  if (typeof trip.currency === 'string') patch.currency = trip.currency
  return patch
}

export function explanationView(destination) {
  const explanation = destination?.explanation || {}
  const summary = trimText(explanation.summary) || null
  const evidence = Array.isArray(explanation.evidence)
    ? explanation.evidence
        .map((item) => ({
          id: trimText(item?.id) || trimText(item?.code) || null,
          code: trimText(item?.code) || null,
          statement: trimText(item?.statement) || null,
        }))
        .filter((item) => item.statement)
    : []
  return { summary, evidence }
}

export function backendScoreItems(destination) {
  const scores = destination?.scores || {}
  return [
    { key: 'price', label: 'Price (cheaper is better)', score: scores.price },
    { key: 'weather', label: 'Weather score', score: scores.weather },
    { key: 'stops', label: 'Stops (fewer is better)', score: scores.stops },
    { key: 'duration', label: 'Duration (shorter is better)', score: scores.duration },
  ].filter((item) => item.score != null && Number.isFinite(Number(item.score)))
}

export function assistantTextForResponse(response, results = [], { unmappedCount = 0 } = {}) {
  if (!response) return 'The planner could not complete that request. Please try again.'

  if (response.status === 'needs_input') {
    const questions = response.clarification_questions || []
    if (questions.length) return questions.join('\n')
    const issues = response.issues || []
    if (issues.length) return issues.join('\n')
    return 'I need a bit more information to plan this trip.'
  }

  if (response.status === 'error') {
    const issues = response.issues || []
    if (issues.length) return issues.join('\n')
    return 'The planner could not complete that request. Please try again.'
  }

  const count = Array.isArray(results) ? results.length : 0
  const cities = [
    ...new Set((results || []).map((item) => item.destination?.city).filter(Boolean)),
  ]
  const issues = (response.issues || []).filter(Boolean)
  const issueLine = issues.length ? ` ${issues.join(' ')}` : ''
  const mapLine = unmappedCount
    ? ` ${unmappedCount} listed ${unmappedCount === 1 ? 'trip has' : 'trips have'} no mappable coordinates.`
    : ''

  if (count === 0) {
    return `No stored trips match that request.${issueLine} Recommendations come from the planner service and stored snapshot data. Not live or bookable.`
  }

  const noun = count === 1 ? 'trip' : 'trips'
  const cityLine = cities.length ? ` Shortlist: ${cities.join(', ')}.` : ''
  return `I found ${count} matching ${noun} from the planner service.${cityLine}${mapLine}${issueLine} Ranked from stored snapshot data. Not live or bookable.`
}

export function refinementFeedbackText(label) {
  const match = REFINEMENT_ACTIONS.find((item) => item.label === label)
  return match?.text || trimText(label)
}
