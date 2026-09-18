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
  departureDate: '',
  returnDate: '',
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
  const [year, month, day] = value.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  )
}

export function plannerDateValue(value) {
  return isIsoDate(value) ? value : ''
}

export function dateRangeError(form = {}) {
  const departure = plannerDateValue(form.departureDate)
  const returnDate = plannerDateValue(form.returnDate)
  if (form.departureDate && !departure) return 'Enter a valid departure date as YYYY-MM-DD.'
  if (form.returnDate && !returnDate) return 'Enter a valid return date as YYYY-MM-DD.'
  if (departure && returnDate && returnDate < departure) {
    return 'Return date must be on or after the departure date.'
  }
  return ''
}

export function datesChangedFromTrip(form, trip) {
  if (!trip) return false
  return (
    plannerDateValue(form?.departureDate) !== plannerDateValue(trip.departure_date) ||
    plannerDateValue(form?.returnDate) !== plannerDateValue(trip.return_date)
  )
}

export function shouldRecommendInsteadOfRefine(form, tripRequest, { clarifying = false } = {}) {
  if (clarifying || !tripRequest) return false
  return datesChangedFromTrip(form, tripRequest)
}

export function describePlannerDates(form = {}) {
  const lines = []
  if (plannerDateValue(form.departureDate)) lines.push(`departure date: ${form.departureDate}`)
  if (plannerDateValue(form.returnDate)) lines.push(`return date: ${form.returnDate}`)
  return lines.join('\n')
}

function describedFormDate(formSelectionsText, label) {
  const match = String(formSelectionsText || '').match(new RegExp(`${label}: (\\d{4}-\\d{2}-\\d{2})`))
  return match ? match[1] : ''
}

export function plannerDatesChangedSinceClarification(form, formSelectionsText) {
  return (
    plannerDateValue(form?.departureDate) !== describedFormDate(formSelectionsText, 'departure date') ||
    plannerDateValue(form?.returnDate) !== describedFormDate(formSelectionsText, 'return date')
  )
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

function isoDateFromUnknown(value) {
  if (isIsoDate(value)) return value
  if (value && typeof value === 'string' && isIsoDate(value.slice(0, 10))) return value.slice(0, 10)
  return ''
}

export function formFieldsFromPreferences(preferences) {
  if (!preferences || typeof preferences !== 'object') return {}
  const fields = {}
  const origin = trimText(preferences.origin)
  if (IATA.test(origin)) fields.origin = origin.toUpperCase()
  const departure = isoDateFromUnknown(preferences.departure_date)
  const returnDate = isoDateFromUnknown(preferences.return_date)
  if (departure) fields.departure_date = departure
  if (returnDate) fields.return_date = returnDate
  const budget = Number(preferences.budget)
  if (Number.isFinite(budget) && budget > 0) fields.budget = budget
  const currency = trimText(preferences.currency)
  if (/^[A-Za-z]{3}$/.test(currency)) fields.currency = currency.toUpperCase()
  if (typeof preferences.weather_preference === 'string' && preferences.weather_preference.trim()) {
    fields.weather_preference = preferences.weather_preference.trim()
  }
  if (typeof preferences.direct_flights_only === 'boolean') {
    fields.direct_flights_only = preferences.direct_flights_only
  }
  const moods = Array.isArray(preferences.moods) ? preferences.moods.map(trimText).filter(Boolean) : []
  if (moods.length) fields.moods = moods
  const duration = Number(preferences.duration_days)
  if (Number.isFinite(duration) && duration > 0) fields.duration_days = duration
  return fields
}

export function fieldsOmittedForClarification(questions = [], answer = '') {
  const omitted = new Set()
  for (const raw of questions) {
    const question = String(raw || '')
    if (/currency is the budget|currency/i.test(question)) omitted.add('currency')
    if (/form has origin|disagree about origin|IATA code/i.test(question)) omitted.add('origin')
    if (/departure date/i.test(question)) omitted.add('departure_date')
    if (/return date/i.test(question)) omitted.add('return_date')
    if (/must be on or after the departure date|confirm both dates/i.test(question)) {
      omitted.add('departure_date')
      omitted.add('return_date')
    }
    if (/currency is the budget/i.test(question)) {
      omitted.delete('budget')
    } else if (/\bbudget\b/i.test(question)) {
      omitted.add('budget')
    }
    if (/weather/i.test(question)) omitted.add('weather_preference')
    if (/direct[- ]flight/i.test(question)) omitted.add('direct_flights_only')
    if (/\bmood/i.test(question)) omitted.add('moods')
  }
  for (const key of fieldsStatedInAnswer(answer)) omitted.add(key)
  return omitted
}

export function fieldsStatedInAnswer(answer = '') {
  const stated = new Set()
  const text = String(answer || '')
  const dates = text.match(/\d{4}-\d{2}-\d{2}/g) || []
  if (dates.length >= 2) {
    stated.add('departure_date')
    stated.add('return_date')
  } else if (dates.length === 1) {
    if (/\breturn\b/i.test(text) && !/\bdepart/i.test(text)) stated.add('return_date')
    else stated.add('departure_date')
  }
  const withoutDates = text.replace(/\d{4}-\d{2}-\d{2}/g, ' ')
  if (
    /(?:€|£|\$|eur|usd|gbp)\s*\d|\d\s*(?:€|£|\$|eur|usd|gbp)/i.test(withoutDates) ||
    /budget\s*(?:is\s+now\s+)?\d/i.test(withoutDates)
  ) {
    stated.add('budget')
  } else if (/^\s*\d{2,5}(?:[.,]\d+)?\s*$/i.test(withoutDates) && !/^\s*20[2-9]\d\s*$/.test(withoutDates)) {
    stated.add('budget')
  }
  if (/\b(eur|usd|gbp)\b|€|£|\$/i.test(text)) stated.add('currency')
  if (/\b(not\s+(?:want\s+)?(?:a\s+)?)?(warm|cool|hot|cold|sunny)/i.test(text)) {
    stated.add('weather_preference')
  }
  return stated
}

export function formFieldsForClarification({ form, origin, preferences, questions, answer } = {}) {
  const omitted = fieldsOmittedForClarification(questions, answer)
  const fromPreferences = formFieldsFromPreferences(preferences)
  const fromForm =
    formFieldsFromPlanner(
      {
        ...form,
        budgetTouched: false,
        includeBudget: false,
        preferWarm: false,
        directOnly: form?.directOnly === true,
      },
      origin,
    ) || {}
  const merged = { ...fromPreferences, ...fromForm }
  for (const key of omitted) delete merged[key]
  return Object.keys(merged).length ? merged : null
}

export function plannerRequestSummary(filters, originLabel, tripRequest, preferences) {
  const parsed = tripRequest || preferences
  if (
    parsed &&
    (parsed.origin ||
      parsed.budget != null ||
      parsed.weather_preference ||
      parsed.departure_date ||
      parsed.return_date)
  ) {
    const departure = isoDateFromUnknown(parsed.departure_date)
    const returnDate = isoDateFromUnknown(parsed.return_date)
    return [
      originLabel || parsed.origin,
      parsed.budget != null ? `${parsed.currency || ''} ${parsed.budget}`.trim() : null,
      parsed.direct_flights_only ? 'Direct only' : null,
      parsed.weather_preference || null,
      departure && returnDate ? `${departure} → ${returnDate}` : null,
    ]
      .filter(Boolean)
      .join(' · ')
  }
  if (!filters) return ''
  return [originLabel || filters.originIata || filters.originId].filter(Boolean).join(' · ')
}

export function composerPlaceholderFor(clarifyKind) {
  return clarifyKind ? 'Type your answer…' : 'Ask for a mood, dates, or budget…'
}

export function isClarificationQuestionText(text, questions = []) {
  const value = trimText(text)
  if (!value) return false
  return (questions || []).some((item) => trimText(item) === value)
}

export function createClarificationContext({ originalPrompt, formFields, preferences, questions = [] } = {}) {
  const combined = {
    ...formFieldsFromPreferences(preferences),
    ...(formFields && typeof formFields === 'object' ? formFields : {}),
  }
  return {
    originalPrompt: trimText(originalPrompt),
    formSelectionsText: describeFormFields(combined),
    preferences: preferences || null,
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
  updatedFormDatesText,
  formFields,
} = {}) {
  const sections = []
  const prompt = trimText(originalPrompt)
  if (prompt) sections.push(`Original request:\n${prompt}`)

  const formText = trimText(formSelectionsText)
  if (formText) sections.push(`Initial form selections:\n${formText}`)

  const updatedDates = trimText(updatedFormDatesText)
  if (updatedDates) {
    sections.push(`Updated form dates (this overrides earlier form dates):\n${updatedDates}`)
  }

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

  const payload = { text: sections.join('\n\n') }
  if (formFields && typeof formFields === 'object' && !Array.isArray(formFields) && Object.keys(formFields).length) {
    payload.form_fields = formFields
  }
  return payload
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
  if (isIsoDate(trip.departure_date)) patch.departureDate = trip.departure_date
  if (isIsoDate(trip.return_date)) patch.returnDate = trip.return_date
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

function normalizeExplanationText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

/** Drop evidence bullets that repeat the summary verbatim. */
export function uniqueExplanationView(destination) {
  const { summary, evidence } = explanationView(destination)
  if (!summary) return { summary, evidence }
  const summaryKey = normalizeExplanationText(summary)
  return {
    summary,
    evidence: evidence.filter((item) => normalizeExplanationText(item.statement) !== summaryKey),
  }
}

export function backendScoreItems(destination) {
  const scores = destination?.scores || {}
  return [
    { key: 'price', label: 'Price (cheaper is better)', score: scores.price },
    { key: 'weather', label: 'Weather (warmer is better)', score: scores.weather },
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
