import { describe, expect, it } from 'vitest'
import {
  INITIAL_PLANNER_FORM,
  assistantTextForResponse,
  backendScoreItems,
  buildClarificationRecommendPayload,
  buildFilterRecommendPayload,
  buildRecommendPayload,
  buildRefinePayload,
  createClarificationContext,
  describeFormFields,
  explanationView,
  formFieldsFromPlanner,
  formForSelectedOrigin,
  formPatchFromTripRequest,
  localClarificationQuestions,
  newTripPlannerState,
  recordClarificationAnswer,
  refinementFeedbackText,
  tripRequestAfterRecommend,
  tripRequestAfterRefine,
} from './plannerFlow'

const tripRequest = {
  origin: 'ZAG',
  departure_date: '2026-09-21',
  return_date: '2026-09-25',
  budget: 400,
  currency: 'EUR',
}

describe('formFieldsFromPlanner', () => {
  it('maps frontend fields onto backend form_fields names', () => {
    expect(
      formFieldsFromPlanner(
        {
          maxBudget: 350,
          directOnly: true,
          preferWarm: true,
          budgetTouched: true,
          currency: 'EUR',
        },
        { iata: 'zag' },
      ),
    ).toEqual({
      origin: 'ZAG',
      budget: 350,
      currency: 'EUR',
      direct_flights_only: true,
      weather_preference: 'warmer',
    })
  })

  it('does not send the default budget before the user or backend sets one', () => {
    expect(formFieldsFromPlanner({ maxBudget: 400, currency: 'EUR' }, null)).toBeNull()
    expect(formFieldsFromPlanner({ maxBudget: 400 }, { iata: 'ZAG' })).toEqual({ origin: 'ZAG' })
  })
})

describe('localClarificationQuestions', () => {
  it('asks for currency without fetching when a budget has no currency', () => {
    const questions = localClarificationQuestions({
      text: 'warm, from 10.10. until 16.10. budget is 500, from LAX',
      form: {},
      origin: { iata: 'LAX' },
    })
    expect(questions).toEqual(['What currency is the budget in (for example EUR)?'])
  })

  it('does not ask when budget already includes a currency', () => {
    expect(
      localClarificationQuestions({
        text: 'warm, from 10.10. until 16.10. budget is 500eur, from LAX',
        origin: { iata: 'LAX' },
      }),
    ).toEqual([])
  })

  it('asks for missing required fields before a recommend fetch', () => {
    const questions = localClarificationQuestions({
      text: 'somewhere warm',
      form: { originIata: 'LAX' },
      origin: { iata: 'LAX' },
    })
    expect(questions).toContain('What is your departure date? For example: 12.10, 12/10/2026, or 2026-10-12.')
    expect(questions).toContain('What is your return date? For example: 16.10, 16/10/2026, or 2026-10-16.')
    expect(questions).toContain('What is your maximum budget?')
    expect(questions).toContain('What currency is the budget in (for example EUR)?')
    expect(questions).not.toContain(
      'What is your origin airport or city IATA code (for example ZAG)?',
    )
  })

  it('does not treat an old prompt as a date source when the form already has dates', () => {
    expect(
      localClarificationQuestions({
        text: '',
        form: {
          originIata: 'ZAG',
          departureDate: '2026-10-21',
          returnDate: '2026-10-30',
          budgetTouched: true,
          maxBudget: 400,
          currency: 'EUR',
        },
      }),
    ).toEqual([])
  })
})

describe('buildRecommendPayload', () => {
  it('sends text plus backend form field names', () => {
    expect(
      buildRecommendPayload('Warm trip from Zagreb', { originIata: 'ZAG', preferWarm: true }, null),
    ).toEqual({
      text: 'Warm trip from Zagreb',
      form_fields: { origin: 'ZAG', weather_preference: 'warmer' },
    })
  })

  it('does not send leftover form dates or budget the message already states', () => {
    expect(
      buildRecommendPayload(
        'From 2026-09-23 to 2026-10-02, budget 800',
        {
          originIata: 'ZAG',
          departureDate: '2026-09-30',
          returnDate: '2026-09-30',
          budgetTouched: true,
          maxBudget: 100,
          currency: 'EUR',
        },
        null,
      ),
    ).toEqual({
      text: 'From 2026-09-23 to 2026-10-02, budget 800',
      form_fields: { origin: 'ZAG', currency: 'EUR' },
    })
  })

  it('sends form_fields without the original prompt on a filter update', () => {
    expect(
      buildFilterRecommendPayload(
        {
          originIata: 'ZAG',
          departureDate: '2026-10-21',
          returnDate: '2026-10-30',
        },
        null,
      ),
    ).toEqual({
      text: '',
      form_fields: {
        origin: 'ZAG',
        departure_date: '2026-10-21',
        return_date: '2026-10-30',
      },
    })
  })
})

describe('buildRefinePayload', () => {
  it('sends feedback text with the saved TripRequest', () => {
    expect(buildRefinePayload('Cheaper', tripRequest)).toEqual({
      text: 'Cheaper',
      request: tripRequest,
    })
  })
})

describe('clarification recommend payload', () => {
  const initialFields = {
    origin: 'ZAG',
    budget: 500,
    currency: 'EUR',
    weather_preference: 'warmer',
  }

  it('sends normal form_fields on the initial search', () => {
    const payload = buildRecommendPayload(
      'A warm getaway from Zagreb',
      { originIata: 'ZAG', maxBudget: 500, budgetTouched: true, preferWarm: true, currency: 'EUR' },
      null,
    )
    expect(payload.form_fields).toEqual({
      origin: 'ZAG',
      budget: 500,
      currency: 'EUR',
      weather_preference: 'warmer',
    })
    expect(payload.text).toBe('A warm getaway from Zagreb')
  })

  it('does not resend a stale budget of 500 when the user clarifies 400', () => {
    const context = createClarificationContext({
      originalPrompt: 'A warm getaway from Zagreb',
      formFields: initialFields,
      questions: ['The form has budget 500 but the message has 400. Which should we use?'],
    })
    const payload = buildClarificationRecommendPayload({
      ...context,
      answer: '400',
    })
    expect(payload).not.toHaveProperty('form_fields')
    expect(payload.text).not.toMatch(/form_fields/)
    expect(JSON.stringify(payload)).not.toMatch(/"budget":\s*500/)
  })

  it('labels the latest clarification as authoritative', () => {
    const payload = buildClarificationRecommendPayload({
      originalPrompt: 'A warm getaway from Zagreb',
      formSelectionsText: describeFormFields(initialFields),
      questions: ['The form has budget 500 but the message has 400. Which should we use?'],
      answer: '400',
    })
    expect(payload.text).toMatch(/Authoritative answer \(this overrides any conflicting initial form values\):\n400/)
    expect(payload.text).toContain('The planner asked:')
    expect(payload.text).toContain('Original request:\nA warm getaway from Zagreb')
  })

  it('keeps non-conflicting initial form values in the accumulated text', () => {
    const payload = buildClarificationRecommendPayload({
      originalPrompt: 'A warm getaway from Zagreb',
      formSelectionsText: describeFormFields(initialFields),
      questions: ['Which budget should we use?'],
      answer: '400',
    })
    expect(payload.text).toContain('origin: ZAG')
    expect(payload.text).toContain('currency: EUR')
    expect(payload.text).toContain('weather preference: warmer')
    expect(payload.text).toContain('budget: 500')
  })

  it('keeps earlier answers when asking a later clarification', () => {
    const first = createClarificationContext({
      originalPrompt: 'A warm getaway from Zagreb',
      formFields: initialFields,
      questions: ['Which budget should we use?'],
    })
    const second = recordClarificationAnswer(first, '400', ['What is your departure date (YYYY-MM-DD)?'])
    const payload = buildClarificationRecommendPayload({
      ...second,
      answer: '2026-09-21',
    })
    expect(payload.previousAnswers).toBeUndefined()
    expect(payload.text).toContain('Earlier clarifications:\n- 400')
    expect(payload.text).toMatch(/Authoritative answer[\s\S]*2026-09-21/)
    expect(payload).not.toHaveProperty('form_fields')
  })

  it('clears clarification, trip request, questions, results, and form values on new trip', () => {
    const cleared = newTripPlannerState()
    expect(cleared.clarification).toBeNull()
    expect(cleared.tripRequest).toBeNull()
    expect(cleared.clarifyKind).toBeNull()
    expect(cleared.clarificationQuestions).toEqual([])
    expect(cleared.pendingSearchText).toBe('')
    expect(cleared.results).toEqual([])
    expect(cleared.rejected).toEqual([])
    expect(cleared.error).toBe('')
    expect(cleared.appliedFilters).toBeNull()
    expect(cleared.form).toEqual(INITIAL_PLANNER_FORM)
    expect(cleared.form.maxBudget).toBe(400)
    expect(cleared.form.originIata).toBe('')
  })
})

describe('formForSelectedOrigin', () => {
  it('keeps the new origin and drops leftover dates and budget', () => {
    expect(
      formForSelectedOrigin({ originId: 'zagreb-hr', iata: 'ZAG' }),
    ).toEqual({
      ...INITIAL_PLANNER_FORM,
      originId: 'zagreb-hr',
      originIata: 'ZAG',
    })
  })
})

describe('trip request state', () => {
  it('stores request on ready recommend and ignores needs_input/error', () => {
    expect(tripRequestAfterRecommend(null, { status: 'ready', request: tripRequest })).toEqual(tripRequest)
    expect(
      tripRequestAfterRecommend(tripRequest, {
        status: 'needs_input',
        request: null,
        clarification_questions: ['What is your departure date?'],
      }),
    ).toEqual(tripRequest)
    expect(tripRequestAfterRecommend(tripRequest, { status: 'error', issues: ['down'] })).toEqual(tripRequest)
  })

  it('replaces the saved request with updated_request after a ready refine', () => {
    const updated = { ...tripRequest, direct_flights_only: true }
    expect(
      tripRequestAfterRefine(tripRequest, {
        status: 'ready',
        request: tripRequest,
        updated_request: updated,
      }),
    ).toEqual(updated)
  })

  it('preserves the last valid request when refine needs input or errors', () => {
    expect(
      tripRequestAfterRefine(tripRequest, {
        status: 'needs_input',
        request: tripRequest,
        updated_request: null,
        clarification_questions: ['Which budget should we use?'],
      }),
    ).toEqual(tripRequest)
    expect(
      tripRequestAfterRefine(tripRequest, {
        status: 'error',
        request: tripRequest,
        updated_request: { ...tripRequest, budget: 1 },
      }),
    ).toEqual(tripRequest)
  })

  it('does not fall back to the old snapshot request when updated_request is missing', () => {
    expect(
      tripRequestAfterRefine(tripRequest, {
        status: 'ready',
        request: { ...tripRequest, budget: 50 },
        updated_request: null,
      }),
    ).toEqual(tripRequest)
  })
})

describe('assistant copy', () => {
  it('shows clarification questions instead of an empty-result message', () => {
    const text = assistantTextForResponse(
      {
        status: 'needs_input',
        clarification_questions: ['What is your departure date (YYYY-MM-DD)?'],
        issues: ['Departure date is missing.'],
      },
      [],
    )
    expect(text).toContain('departure date')
    expect(text).not.toMatch(/No trips match/i)
    expect(text).not.toMatch(/ranked in the browser/i)
  })

  it('describes ready recommendations without snapshot disclaimers', () => {
    const text = assistantTextForResponse(
      { status: 'ready', issues: [] },
      [{ destination: { city: 'Rome' } }, { destination: { city: 'Lisbon' } }],
    )
    expect(text).toMatch(/I found 2 matching trips/)
    expect(text).toMatch(/Rome/)
    expect(text).not.toMatch(/snapshot|not live or bookable/i)
    expect(text).not.toMatch(/ranked in the browser/i)
  })
})

describe('explanations and scores', () => {
  it('exposes backend summary and evidence without inventing ranking copy', () => {
    const view = explanationView({
      explanation: {
        summary: 'Rome stays within budget.',
        evidence: [{ id: 'e1', statement: 'Fare is EUR 65 against a EUR 400 budget.' }, { statement: '' }],
      },
    })
    expect(view.summary).toBe('Rome stays within budget.')
    expect(view.evidence.map((item) => item.statement)).toEqual([
      'Fare is EUR 65 against a EUR 400 budget.',
    ])
  })

  it('copies backend scores and omits missing ones', () => {
    expect(
      backendScoreItems({
        scores: { price: 0.8, weather: null, stops: 1, duration: 0.4, total: 0.7 },
      }).map((item) => item.key),
    ).toEqual(['price', 'stops', 'duration'])
  })

  it('maps chip labels to backend feedback text', () => {
    expect(refinementFeedbackText('Direct flights')).toBe('Direct')
    expect(refinementFeedbackText('Shorter travel')).toBe('Shorter')
  })

  it('patches the form from a returned TripRequest without inventing values', () => {
    expect(formPatchFromTripRequest(tripRequest)).toMatchObject({
      originIata: 'ZAG',
      maxBudget: 400,
      departureDate: '2026-09-21',
    })
  })
})
