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

export function formForSelectedOrigin(origin, base = INITIAL_PLANNER_FORM) {
  return {
    ...base,
    originId: origin?.originId || '',
    originIata: origin?.iata || '',
  }
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

const FORM_FIELDS_STATED_IN_TEXT = [
  'origin',
  'departure_date',
  'return_date',
  'budget',
  'currency',
]

/** Keep form_fields the message did not already state, so leftover dates/budget cannot fight the prompt. */
export function formFieldsForRecommendText(text, form, origin) {
  const fields = formFieldsFromPlanner(form, origin)
  if (!fields) return null
  const trimmed = typeof text === 'string' ? text.trim() : ''
  if (!trimmed) return fields
  const hints = hintsFromPlannerText(trimmed)
  const next = { ...fields }
  for (const key of FORM_FIELDS_STATED_IN_TEXT) {
    if (hints[key]) delete next[key]
  }
  return Object.keys(next).length ? next : null
}

export function buildRecommendPayload(text, form, origin) {
  const payload = { text: typeof text === 'string' ? text : '' }
  const formFields = formFieldsForRecommendText(payload.text, form, origin)
  if (formFields) payload.form_fields = formFields
  return payload
}

/** Filter updates send form_fields only so the original prompt cannot fight the form. */
export function buildFilterRecommendPayload(form, origin) {
  return buildRecommendPayload('', form, origin)
}

const MONTH =
  'january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec'
const DATE_TOKEN = new RegExp(
  String.raw`\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:${MONTH})[a-z]*\.?,?\s+\d{4}|(?:${MONTH})[a-z]*\.?,?\s+\d{1,2},?\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{1,2}[./-]\d{1,2}\.?(?![./-]?\d)`,
  'gi',
)
const DATE_RANGE = new RegExp(
  String.raw`\d{1,2}\s*(?:[–-]|to|until|till)\s*\d{1,2}\s+(?:${MONTH})[a-z]*\.?,?\s+\d{4}`,
  'i',
)
const MAYBE_UNPARSED_DATES = new RegExp(
  String.raw`(?:${MONTH})|\bweekend\b|\bnext week\b|\d+(?:st|nd|rd|th)\b`,
  'i',
)
const CURRENCY_FROM_TEXT =
  /(?:€|\beuros?\b|\beur\b)|(?:\bpounds?\b|\bgbp\b|£)|(?:\bdollars?\b|\busd\b|\$)/i
const AMOUNT_WITH_CURRENCY =
  /(?:€|£|\$)\s*\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*(?:€|£|\$|eur|euros?|usd|gbp|dollars?|pounds?)/i
const BUDGET_AMOUNT = /budget(?:\s+is|\s+of)?\s*[:\s]*(\d+(?:[.,]\d+)?)/i
const FROM_IATA = /\b(?:from|origin)\s+([A-Za-z]{3})\b/i
const ORIGIN_LINE = /^origin:\s*([A-Za-z]{3})\s*$/im
const BUDGET_LINE = /^budget:\s*(\d+(?:[.,]\d+)?)\s*$/im
const CURRENCY_LINE = /^currency:\s*([A-Za-z]{3})\s*$/im
const CURRENCY_CODES = /\b(EUR|USD|GBP|CHF|HRK|CAD|AUD)\b/i
const SKIP_ORIGIN_CODES = new Set(['EUR', 'USD', 'GBP', 'CHF', 'CAD', 'AUD', 'THE', 'AND', 'FOR', 'ARE'])

export const LOCAL_PLANNER_QUESTIONS = {
  origin: 'What is your origin airport or city IATA code (for example ZAG)?',
  departure:
    'What is your departure date? For example: 12.10, 12/10/2026, or 2026-10-12.',
  return: 'What is your return date? For example: 16.10, 16/10/2026, or 2026-10-16.',
  budget: 'What is your maximum budget?',
  currency: 'What currency is the budget in (for example EUR)?',
}

function authoredPlannerText(text) {
  const raw = trimText(text)
  if (!raw) return ''
  const lowered = raw.toLowerCase()
  if (!lowered.includes('the planner asked:') && !lowered.includes('original request:')) {
    return raw
  }
  return raw
    .split(/\n\s*\n/)
    .filter((part) => {
      const first = part.trim().split('\n', 1)[0].trim().toLowerCase()
      return !first.startsWith('the planner asked:') && !first.startsWith('initial form selections:')
    })
    .join('\n\n')
}

function currencyFromMatch(text) {
  if (/€|\beuros?\b|\beur\b/i.test(text)) return 'EUR'
  if (/£|\bpounds?\b|\bgbp\b/i.test(text)) return 'GBP'
  if (/\$|\bdollars?\b|\busd\b/i.test(text)) return 'USD'
  const code = text.match(CURRENCY_CODES)
  return code ? code[1].toUpperCase() : null
}

export function hintsFromPlannerText(text) {
  const raw = authoredPlannerText(text)
  const hints = {}
  if (!raw) return hints

  const originMatch = raw.match(ORIGIN_LINE) || raw.match(FROM_IATA)
  if (originMatch) {
    const code = originMatch[1].toUpperCase()
    if (IATA.test(code) && !SKIP_ORIGIN_CODES.has(code)) hints.origin = code
  }

  const dateRange = DATE_RANGE.test(raw)
  const dateTokens = raw.match(DATE_TOKEN) || []
  if (dateRange || dateTokens.length >= 2) {
    hints.departure_date = true
    hints.return_date = true
  } else if (dateTokens.length === 1) {
    hints.departure_date = true
  }

  const budgetLine = raw.match(BUDGET_LINE)
  const budgetPhrase = raw.match(BUDGET_AMOUNT)
  const priced = AMOUNT_WITH_CURRENCY.test(raw)
  if (budgetLine || budgetPhrase || priced) hints.budget = true

  const currencyLine = raw.match(CURRENCY_LINE)
  if (currencyLine && IATA.test(currencyLine[1])) hints.currency = currencyLine[1].toUpperCase()
  else if (priced || CURRENCY_FROM_TEXT.test(raw)) {
    hints.currency = currencyFromMatch(raw) || true
  }

  return hints
}

/**
 * Required-field questions we can ask without calling /api/recommend.
 * Does not invent values. If the message still might contain dates or budget
 * the local scanner missed, the caller should send the request to the API.
 */
export function localClarificationQuestions({ text = '', form = {}, origin = null } = {}) {
  const formFields = formFieldsFromPlanner(form, origin) || {}
  const hints = hintsFromPlannerText(text)
  const questions = []

  const originCode = formFields.origin || hints.origin
  const departure = formFields.departure_date || hints.departure_date
  const ret = formFields.return_date || hints.return_date
  const budget = formFields.budget != null || hints.budget
  const currency = formFields.currency || hints.currency
  const deferDates = !departure && MAYBE_UNPARSED_DATES.test(trimText(text))

  if (!originCode) questions.push(LOCAL_PLANNER_QUESTIONS.origin)
  if (!departure && !deferDates) questions.push(LOCAL_PLANNER_QUESTIONS.departure)
  if (!ret && !deferDates) questions.push(LOCAL_PLANNER_QUESTIONS.return)
  if (!budget) questions.push(LOCAL_PLANNER_QUESTIONS.budget)
  if (!currency) questions.push(LOCAL_PLANNER_QUESTIONS.currency)
  return questions
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
    return `No trips match that request.${issueLine}`
  }

  const noun = count === 1 ? 'trip' : 'trips'
  const cityLine = cities.length ? ` Shortlist: ${cities.join(', ')}.` : ''
  return `I found ${count} matching ${noun}.${cityLine}${mapLine}${issueLine}`
}

export function refinementFeedbackText(label) {
  const match = REFINEMENT_ACTIONS.find((item) => item.label === label)
  return match?.text || trimText(label)
}
