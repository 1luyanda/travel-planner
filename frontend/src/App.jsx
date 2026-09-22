import { useEffect, useRef, useState } from 'react'
import { List, Map as MapIcon, Menu, SlidersHorizontal } from 'lucide-react'
import { useAuth } from './auth/AuthProvider'
import Sidebar from './components/Sidebar'
import Composer from './components/Composer'
import OriginSelect from './components/OriginSelect'
import TripDateFields from './components/TripDateFields'
import WelcomePane from './components/WelcomePane'
import InspirationPanel from './components/InspirationPanel'
import ConversationPane from './components/ConversationPane'
import SavedPane from './components/SavedPane'
import DestinationMap from './components/DestinationMap'
import FiltersPopover from './components/FiltersPopover'
import TripDetailsDrawer from './components/TripDetailsDrawer'
import LandingPage from './components/LandingPage'
import LoginPage from './components/LoginPage'
import SignupPage from './components/SignupPage'
import {
  deleteSavedFlight,
  fetchSavedFlights,
  recommendTrip,
  refineTrip,
  saveFlight,
  searchOrigins,
} from './services/travelApi'
import {
  adaptRecommendations,
  attachDestinationCityPhotos,
} from './utils/adaptRecommendations'
import {
  INITIAL_PLANNER_FORM,
  assistantTextForResponse,
  buildClarificationRecommendPayload,
  buildFilterRecommendPayload,
  buildRecommendPayload,
  composerPlaceholderFor,
  createClarificationContext,
  dateRangeError,
  describePlannerDates,
  formFieldsForClarification,
  formFieldsFromPlanner,
  formForSelectedOrigin,
  formPatchFromTripRequest,
  isClarificationQuestionText,
  localClarificationQuestions,
  newTripPlannerState,
  plannerDatesChangedSinceClarification,
  recordClarificationAnswer,
  refinementFeedbackText,
  shouldRecommendInsteadOfRefine,
  tripRequestAfterRecommend,
  tripRequestAfterRefine,
} from './utils/plannerFlow'
import { formatOriginLabel, parseOriginItem } from './utils/origins'
import {
  PLANNER_TIMEOUT_MESSAGE,
  createPlannerRequest,
  runPlannerRequest,
} from './utils/plannerRequest'
import {
  clearTripSelection,
  resolveSelectedTrip,
  selectTripFromResult,
  selectionAfterPoolChange,
  tripFromMarkerId,
} from './utils/tripDetailsSelection'
import {
  adaptSavedFlight,
  adaptSavedFlights,
  destinationsForView,
  flightReferenceFromDestination,
  keepSavedFlightPhotos,
  savedFlightIds,
  showPlannerComposer,
  showPlannerConversation,
  showPlannerFilters,
} from './utils/savedFlights'
import { AppLink, ROUTES, isAppPath, isAuthPath, isPlannerPath, useRoute } from './utils/routes.jsx'
import styles from './workspace.module.css'

const initialForm = INITIAL_PLANNER_FORM

function nextId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function unmappedTripCount(results) {
  return results.filter(
    (item) => item.destination?.latitude == null || item.destination?.longitude == null,
  ).length
}

export default function App() {
  const { path, navigate } = useRoute()
  const { user, loading: authLoading, logout } = useAuth()
  const userId = user?.id || null
  const [form, setForm] = useState(initialForm)
  const [selectedOrigin, setSelectedOrigin] = useState(null)
  const [searchSnapshot, setSearchSnapshot] = useState(initialForm)
  const [tripRequest, setTripRequest] = useState(null)
  const [rankingPreferences, setRankingPreferences] = useState(null)
  const [pendingSearchText, setPendingSearchText] = useState('')
  const [clarifyKind, setClarifyKind] = useState(null)
  const [clarification, setClarification] = useState(null)
  const [clarificationQuestions, setClarificationQuestions] = useState([])
  const [parsedPreferences, setParsedPreferences] = useState(null)
  const [rejected, setRejected] = useState([])
  const [dataSource, setDataSource] = useState(null)
  const [dateFallback, setDateFallback] = useState(null)
  const [results, setResults] = useState([])
  const [previousRanks, setPreviousRanks] = useState({})
  const [appliedFilters, setAppliedFilters] = useState(null)
  const [selectedTrip, setSelectedTrip] = useState(null)
  const [selectedDestinationId, setSelectedDestinationId] = useState(null)
  const [viewportMode, setViewportMode] = useState('bounds')
  const [loading, setLoading] = useState(false)
  const [refining, setRefining] = useState(false)
  const [error, setError] = useState('')
  const [flightWarning, setFlightWarning] = useState('')
  const [hasSearched, setHasSearched] = useState(false)
  const [view, setView] = useState('explore')
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState([])
  const [history, setHistory] = useState([])
  const [savedItems, setSavedItems] = useState([])
  const [savedLoading, setSavedLoading] = useState(false)
  const [savedError, setSavedError] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mobilePane, setMobilePane] = useState('list')
  const [pendingSelectId, setPendingSelectId] = useState(null)
  const [originError, setOriginError] = useState('')
  const [focusOrigin, setFocusOrigin] = useState(false)
  const [activeRefinement, setActiveRefinement] = useState(null)
  const [isNarrow, setIsNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 780px)').matches,
  )
  const lastFocusRef = useRef(null)
  const composerRef = useRef(null)
  const originInputRef = useRef(null)
  const searchAbortRef = useRef(null)
  const searchSeqRef = useRef(0)
  const tripRequestRef = useRef(null)
  const rankingPreferencesRef = useRef(null)
  const resultsRef = useRef([])

  useEffect(() => {
    tripRequestRef.current = tripRequest
  }, [tripRequest])

  useEffect(() => {
    rankingPreferencesRef.current = rankingPreferences
  }, [rankingPreferences])

  useEffect(() => {
    resultsRef.current = results
  }, [results])

  const prices = results.map((item) => Number(item.flight?.price)).filter((value) => Number.isFinite(value))
  const maxBudgetCap = prices.length
    ? Math.max(...prices, Number(form.maxBudget) || 0)
    : Math.max(500, Number(form.maxBudget) || 0)
  const savedIds = savedFlightIds(savedItems)
  const visibleDestinations = destinationsForView(view, { results, savedItems })
  const mapResults = visibleDestinations
  const detailsTrip = resolveSelectedTrip(mapResults, selectedTrip)
  const showMap = view === 'saved' || hasSearched
  const showInspiration = view === 'explore' && !hasSearched
  const dateError = dateRangeError(form)
  const busy = loading || refining
  const conversationPhase = loading
    ? 'loading'
    : refining
      ? 'refining'
      : clarifyKind
        ? 'clarifying'
        : error && results.length === 0
          ? 'error'
          : 'ready'

  useEffect(() => {
    setSavedItems([])
    setSavedError('')
    if (!userId) {
      setSavedLoading(false)
      return undefined
    }

    const controller = new AbortController()
    setSavedLoading(true)
    loadAdaptedSavedFlights(controller.signal)
      .then((items) => {
        setSavedItems(items)
        setSavedError('')
      })
      .catch((error) => {
        if (error?.name === 'AbortError') return
        setSavedItems([])
        setSavedError(error?.message || 'Could not load saved flights.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setSavedLoading(false)
      })

    return () => controller.abort()
  }, [userId])

  const previousWorkspaceUserRef = useRef(undefined)
  useEffect(() => {
    if (previousWorkspaceUserRef.current === userId) return
    previousWorkspaceUserRef.current = userId

    searchAbortRef.current?.abort()
    searchSeqRef.current += 1
    setForm(initialForm)
    setSelectedOrigin(null)
    setSearchSnapshot(initialForm)
    setRejected([])
    setDataSource(null)
    setDateFallback(null)
    setResults([])
    setRankingPreferences(null)
    setPreviousRanks({})
    setAppliedFilters(null)
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setViewportMode('bounds')
    setLoading(false)
    setError('')
    setFlightWarning('')
    setHasSearched(false)
    setView('explore')
    setDraft('')
    setMessages([])
    setHistory([])
    setFiltersOpen(false)
    setSidebarOpen(false)
    setMobilePane('list')
    setPendingSelectId(null)
    setOriginError('')
    setFocusOrigin(false)
  }, [userId])

  useEffect(() => {
    if (!isAppPath(path)) {
      navigate(ROUTES.home, { replace: true })
    }
  }, [navigate, path])

  useEffect(() => {
    if (authLoading) return
    if (isPlannerPath(path) && !user) {
      navigate(ROUTES.home, { replace: true })
    }
    if (isAuthPath(path) && user) {
      navigate(ROUTES.planner, { replace: true })
    }
  }, [authLoading, navigate, path, user])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 780px)')
    const sync = () => setIsNarrow(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  useEffect(() => {
    if (!focusOrigin || !isPlannerPath(path)) return
    originInputRef.current?.focus()
    setFocusOrigin(false)
  }, [focusOrigin, path])

  useEffect(() => {
    const pool = visibleDestinations
    const next = selectionAfterPoolChange(pool, selectedTrip, selectedDestinationId)
    if (next.selectedDestinationId !== selectedDestinationId) {
      setSelectedDestinationId(next.selectedDestinationId)
    }
    if ((next.selectedTrip?.id || null) !== (selectedTrip?.id || null)) {
      setSelectedTrip(next.selectedTrip)
    }
  }, [results, visibleDestinations, selectedDestinationId, selectedTrip, view])

  useEffect(() => {
    if (!pendingSelectId) return
    const pool = visibleDestinations
    if (pool.some((item) => item.id === pendingSelectId)) {
      setSelectedDestinationId(pendingSelectId)
      setViewportMode('selected')
      setPendingSelectId(null)
    }
  }, [pendingSelectId, results, visibleDestinations, view])

  function invalidateResults(nextOrigin = selectedOrigin) {
    searchAbortRef.current?.abort()
    searchAbortRef.current?.dispose?.()
    searchAbortRef.current = null
    searchSeqRef.current += 1
    const nextForm = formForSelectedOrigin(nextOrigin)
    setHasSearched(false)
    setResults([])
    setRejected([])
    setRankingPreferences(null)
    setDataSource(null)
    setDateFallback(null)
    setAppliedFilters(null)
    setPreviousRanks({})
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setTripRequest(null)
    setPendingSearchText('')
    setClarifyKind(null)
    setClarification(null)
    setClarificationQuestions([])
    setParsedPreferences(null)
    setActiveRefinement(null)
    setMessages([])
    setError('')
    setFlightWarning('')
    setFiltersOpen(false)
    setViewportMode('bounds')
    setView('explore')
    setLoading(false)
    setRefining(false)
    setForm(nextForm)
    setSearchSnapshot(nextForm)
  }

  function handleOriginChange(origin) {
    const same = origin?.originId && origin.originId === selectedOrigin?.originId
    setSelectedOrigin(origin)
    setOriginError('')
    if (hasSearched && !same) {
      invalidateResults(origin)
      return
    }
    setForm((current) => formForSelectedOrigin(origin, current))
  }

  async function enrichMappedResults(mapped, signal, seq) {
    if (seq != null && seq !== searchSeqRef.current) return mapped
    return attachCityPhotos(mapped, signal)
  }

  async function attachCityPhotos(results, signal) {
    const cities = [
      ...new Set(results.map((item) => item?.destination?.city).filter(Boolean)),
    ]
    if (!cities.length) return results
    try {
      const batches = await Promise.all(
        cities.map(async (city) => {
          try {
            return await searchOrigins(city, { signal })
          } catch (err) {
            if (err?.name === 'AbortError') throw err
            return []
          }
        }),
      )
      return attachDestinationCityPhotos(results, batches.flat())
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      return results
    }
  }

  async function loadAdaptedSavedFlights(signal) {
    const payload = await fetchSavedFlights({ signal })
    return attachCityPhotos(adaptSavedFlights(payload), signal)
  }

  async function runRecommend(userText, options = {}) {
    const {
      nextForm = form,
      origin = selectedOrigin,
      mode = 'fresh',
      userMessage = null,
      preserveRankingPreferences = true,
    } = options
    const typed = (userText || '').trim()
    const apiText = mode === 'filters' ? '' : typed
    if (mode === 'filters') {
      if (!formFieldsFromPlanner(nextForm, origin)?.origin) return
    } else if (mode !== 'clarify' && !apiText) {
      return
    }
    if (mode === 'clarify' && !typed) return

    const seq = ++searchSeqRef.current
    searchAbortRef.current?.abort()
    searchAbortRef.current?.dispose?.()
    searchAbortRef.current = null

    const clarifySource =
      mode === 'clarify'
        ? clarification || createClarificationContext({ originalPrompt: pendingSearchText })
        : null
    const localText =
      mode === 'clarify'
        ? [
            clarifySource?.originalPrompt,
            ...(clarifySource?.previousAnswers || []),
            typed,
          ]
            .filter(Boolean)
            .join('\n')
        : apiText
    const localQuestions = localClarificationQuestions({
      text: localText,
      form: nextForm,
      origin,
    })

    setRefining(false)
    setError('')
    setFlightWarning('')
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setViewportMode('bounds')
    setView('explore')
    setMobilePane('list')
    setSidebarOpen(false)
    setFiltersOpen(false)
    setHasSearched(true)
    setForm(nextForm)
    if (mode === 'fresh') {
      setPendingSearchText(typed)
      setClarifyKind(null)
      setClarification(null)
      setClarificationQuestions([])
      setParsedPreferences(null)
      setTripRequest(null)
      setResults([])
      setDateFallback(null)
      setRejected([])
      setRankingPreferences(null)
      setPreviousRanks({})
      setActiveRefinement(null)
    } else if (mode === 'clarify') {
      setResults([])
      setDateFallback(null)
    }
    if (userMessage || typed) {
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'user', text: userMessage || typed },
      ])
    }

    if (localQuestions.length) {
      setLoading(false)
      const nextContext =
        mode === 'clarify'
          ? recordClarificationAnswer(clarifySource, typed, localQuestions)
          : createClarificationContext({
              originalPrompt: mode === 'filters' ? pendingSearchText || typed : typed,
              formFields: formFieldsFromPlanner(nextForm, origin),
              questions: localQuestions,
              rankingPreferences: mode === 'filters' && preserveRankingPreferences ? rankingPreferences : null,
            })
      setClarifyKind('recommend')
      setClarification(nextContext)
      setClarificationQuestions(localQuestions)
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: 'assistant',
          text: assistantTextForResponse(
            { status: 'needs_input', clarification_questions: localQuestions },
            [],
          ),
        },
      ])
      return
    }

    const request = createPlannerRequest()
    searchAbortRef.current = request
    setLoading(true)
    if (mode === 'fresh') {
      setClarifyKind(null)
      setClarification(null)
      setClarificationQuestions([])
    }

    try {
      const payload =
        mode === 'clarify'
          ? buildClarificationRecommendPayload({
              ...(clarification || createClarificationContext({ originalPrompt: pendingSearchText })),
              answer: typed,
              updatedFormDatesText: plannerDatesChangedSinceClarification(
                nextForm,
                (clarification || {}).formSelectionsText,
              )
                ? describePlannerDates(nextForm)
                : '',
              formFields: formFieldsForClarification({
                form: nextForm,
                origin,
                preferences: (clarification || {}).preferences,
                questions: (clarification || {}).questions,
                answer: typed,
              }),
            })
          : mode === 'filters'
            ? buildFilterRecommendPayload(nextForm, origin, rankingPreferencesRef.current, {
                preserveRankingPreferences,
              })
            : buildRecommendPayload(apiText, nextForm, origin)

      const outcome = await runPlannerRequest({
      request,
      seq,
      isCurrent: (value) => value === searchSeqRef.current,
      setBusy: (busy) => {
        if (!busy) {
          setLoading(false)
          setRefining(false)
        }
      },
      execute: (signal) => recommendTrip(payload, { signal }),
    })

    if (seq !== searchSeqRef.current || outcome.status === 'stale') return

    if (outcome.status === 'aborted') {
      setError(PLANNER_TIMEOUT_MESSAGE)
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'assistant', text: PLANNER_TIMEOUT_MESSAGE },
      ])
      return
    }

    if (outcome.status === 'failed') {
      const message = outcome.error?.message || 'Could not reach the planner service. Please try again.'
      setError(message)
      setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
      return
    }

    const response = outcome.result
    if (response.status === 'needs_input') {
      const nextContext =
        mode === 'clarify'
          ? recordClarificationAnswer(
              clarification,
              typed,
              response.clarification_questions,
            )
          : createClarificationContext({
              originalPrompt: mode === 'filters' ? pendingSearchText || typed : typed,
              formFields: formFieldsFromPlanner(nextForm, origin),
              preferences: response.preferences,
              questions: response.clarification_questions,
              rankingPreferences: mode === 'filters' && preserveRankingPreferences ? rankingPreferences : null,
            })
      setClarifyKind('recommend')
      setClarification(nextContext)
      setClarificationQuestions(response.clarification_questions)
      setParsedPreferences(response.preferences || null)
      setResults([])
      setRejected(response.rejected)
      setDateFallback(null)
      setDataSource(response.data_source)
      setAppliedFilters(nextForm)
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'assistant', text: assistantTextForResponse(response, []) },
      ])
      return
    }

    if (response.status === 'error') {
      const message = assistantTextForResponse(response, [])
      setError(message)
      setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
      return
    }

    const nextTrip = tripRequestAfterRecommend(null, response)
    setTripRequest(nextTrip)
    setClarifyKind(null)
    setClarification(null)
    setClarificationQuestions([])
    setParsedPreferences(response.preferences || null)
    if (nextTrip) {
      setForm((current) => ({
        ...current,
        ...formPatchFromTripRequest(nextTrip),
        budgetTouched: true,
      }))
    }
    if (response.origin) {
      const parsed = parseOriginItem(response.origin)
      if (parsed) {
        setSelectedOrigin(parsed)
        setForm((current) => ({
          ...current,
          originId: parsed.originId,
          originIata: parsed.iata || current.originIata,
        }))
      }
    }

    const adapted = adaptRecommendations(response, { selectedOrigin: origin })
    setRejected(adapted.rejected)
    setDataSource(adapted.dataSource)
    setDateFallback(adapted.dateFallback)
    setAppliedFilters(nextForm)
    setResults(adapted.results)
    setRankingPreferences(response.ranking_preferences || rankingPreferencesRef.current)
    setPreviousRanks({})
    setActiveRefinement(null)
    setSearchSnapshot(nextForm)
    setMessages((current) => [
      ...current,
      {
        id: nextId(),
        role: 'assistant',
        text: assistantTextForResponse(response, adapted.results, {
          unmappedCount: unmappedTripCount(adapted.results),
        }),
      },
    ])
    setHistory((current) => {
      const item = {
        id: nextId(),
        title: apiText.slice(0, 52),
        text: apiText,
        filters: nextForm,
        origin: origin || selectedOrigin,
      }
      return [item, ...current.filter((entry) => entry.title !== item.title)].slice(0, 8)
    })

    try {
      const enriched = await enrichMappedResults(adapted.results, request.signal, seq)
      if (seq !== searchSeqRef.current) return
      setResults(enriched)
    } catch (err) {
      if (err?.name === 'AbortError' || seq !== searchSeqRef.current) return
      setFlightWarning('Destination photos are unavailable.')
    }
    } catch (err) {
      if (err?.name === 'AbortError' || seq !== searchSeqRef.current) return
      const message = err.message || 'Could not reach the planner service. Please try again.'
      setError(message)
      setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
    } finally {
      request.dispose()
      if (seq === searchSeqRef.current) {
        setLoading(false)
        setRefining(false)
      }
    }
  }

  async function runRefine(feedbackText, { label = null } = {}) {
    const savedRequest = tripRequestRef.current
    const text = (feedbackText || '').trim()
    if (!savedRequest || !text || loading || refining) return

    const seq = ++searchSeqRef.current
    searchAbortRef.current?.abort()
    searchAbortRef.current?.dispose?.()
    const request = createPlannerRequest()
    searchAbortRef.current = request

    setRefining(true)
    setError('')
    setFlightWarning('')
    setViewportMode('bounds')
    setClarifyKind(null)
    setMessages((current) => [...current, { id: nextId(), role: 'user', text: label || text }])

    try {
      const outcome = await runPlannerRequest({
        request,
        seq,
        isCurrent: (value) => value === searchSeqRef.current,
        setBusy: (busy) => {
          if (!busy) {
            setLoading(false)
            setRefining(false)
          }
        },
        execute: (signal) =>
          refineTrip(
            {
              text,
              request: savedRequest,
              ranking_preferences: rankingPreferencesRef.current,
            },
            { signal },
          ),
      })

      if (seq !== searchSeqRef.current || outcome.status === 'stale') return

      if (outcome.status === 'aborted') {
        setError(PLANNER_TIMEOUT_MESSAGE)
        setMessages((current) => [
          ...current,
          { id: nextId(), role: 'assistant', text: PLANNER_TIMEOUT_MESSAGE },
        ])
        return
      }

      if (outcome.status === 'failed') {
        const message = outcome.error?.message || 'Could not update recommendations. Please try again.'
        setError(message)
        setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
        return
      }

      const response = outcome.result
      if (response.status === 'needs_input') {
        setClarifyKind('refine')
        setClarificationQuestions(response.clarification_questions)
        setMessages((current) => [
          ...current,
          { id: nextId(), role: 'assistant', text: assistantTextForResponse(response, resultsRef.current) },
        ])
        return
      }

      if (response.status === 'error') {
        const message = assistantTextForResponse(response, [])
        setError(message)
        setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
        return
      }

      const nextTrip = tripRequestAfterRefine(savedRequest, response)
      setTripRequest(nextTrip)
      setClarifyKind(null)
      setClarification(null)
      setClarificationQuestions([])
      if (label) setActiveRefinement(label)
      if (nextTrip) {
        setForm((current) => ({
          ...current,
          ...formPatchFromTripRequest(nextTrip),
          budgetTouched: true,
        }))
      }

      const oldRanks = Object.fromEntries(
        resultsRef.current.map((item, index) => [item.id, item.rank || index + 1]),
      )
      const adapted = adaptRecommendations(response, { selectedOrigin })
      setPreviousRanks(oldRanks)
      setResults(adapted.results)
      setRankingPreferences(response.ranking_preferences || rankingPreferencesRef.current)
      setRejected(adapted.rejected)
      setDataSource(adapted.dataSource)
      setDateFallback(adapted.dateFallback)
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: 'assistant',
          text: assistantTextForResponse(response, adapted.results, {
            unmappedCount: unmappedTripCount(adapted.results),
          }),
        },
      ])

      try {
        const enriched = await enrichMappedResults(adapted.results, request.signal, seq)
        if (seq !== searchSeqRef.current) return
        setResults(enriched)
      } catch (err) {
        if (err?.name === 'AbortError' || seq !== searchSeqRef.current) return
        setFlightWarning('Destination photos are unavailable.')
      }
    } catch (err) {
      if (err?.name === 'AbortError' || seq !== searchSeqRef.current) return
      const message = err.message || 'Could not update recommendations. Please try again.'
      setError(message)
      setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
    } finally {
      request.dispose()
      if (seq === searchSeqRef.current) {
        setLoading(false)
        setRefining(false)
      }
    }
  }

  function handleComposerSubmit(event) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    if (dateRangeError(form)) return
    if (isClarificationQuestionText(text, clarificationQuestions)) return
    setDraft('')

    if (clarifyKind === 'recommend') {
      runRecommend(text, { mode: 'clarify' })
      return
    }
    if (shouldRecommendInsteadOfRefine(form, tripRequest, { clarifying: false })) {
      runRecommend(text, { mode: 'fresh' })
      return
    }
    if (clarifyKind === 'refine' && tripRequest) {
      runRefine(text)
      return
    }
    if (tripRequest) {
      runRefine(text)
      return
    }
    runRecommend(text, { mode: 'fresh' })
  }

  function handleStarter(prompt) {
    setDraft('')
    runRecommend(prompt, {
      mode: 'fresh',
      nextForm: {
        ...initialForm,
        originId: selectedOrigin?.originId || '',
        originIata: selectedOrigin?.iata || '',
        departureDate: form.departureDate,
        returnDate: form.returnDate,
      },
      origin: selectedOrigin,
    })
  }

  function handleDateChange(field, value) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }))
  }

  function handleFilterChange(field, value) {
    const next = {
      ...form,
      [field]: value,
      budgetTouched: field === 'maxBudget' ? true : form.budgetTouched,
    }
    setForm(next)
    if (!hasSearched || !pendingSearchText || busy || clarifyKind) return
    // Re-search from the form only. Reusing the original prompt fights the new dates.
    runRecommend(pendingSearchText, {
      nextForm: next,
      mode: 'filters',
      userMessage: 'Updated filters',
      // Selecting Warmer is new intent; budget/direct/date changes are not.
      preserveRankingPreferences: field !== 'preferWarm' || value !== true,
    })
  }

  function handleResetFilters() {
    const restored = searchSnapshot || initialForm
    setForm(restored)
    if (!hasSearched || !pendingSearchText || clarifyKind) return
    runRecommend(pendingSearchText, {
      nextForm: restored,
      mode: 'filters',
      userMessage: 'Reset filters',
    })
  }

  function handleNewTrip() {
    const cleared = newTripPlannerState()
    searchAbortRef.current?.abort()
    searchAbortRef.current?.dispose?.()
    searchAbortRef.current = null
    searchSeqRef.current += 1
    setHasSearched(false)
    setView('explore')
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setError(cleared.error)
    setFlightWarning('')
    setPreviousRanks({})
    setResults(cleared.results)
    setRejected(cleared.rejected)
    setRankingPreferences(null)
    setDataSource(null)
    setDateFallback(null)
    setAppliedFilters(cleared.appliedFilters)
    setTripRequest(cleared.tripRequest)
    setPendingSearchText(cleared.pendingSearchText)
    setClarifyKind(cleared.clarifyKind)
    setClarification(cleared.clarification)
    setClarificationQuestions(cleared.clarificationQuestions)
    setParsedPreferences(null)
    setActiveRefinement(null)
    setMessages([])
    setDraft('')
    setForm(cleared.form)
    setSelectedOrigin(null)
    setOriginError('')
    setFiltersOpen(false)
    setSidebarOpen(false)
    setMobilePane('list')
    setViewportMode('bounds')
    setLoading(false)
    setRefining(false)
  }

  function handleSelectDestination(destination) {
    const next = selectTripFromResult(destination)
    if (!next) return
    setSelectedDestinationId(next.selectedDestinationId)
    setViewportMode(next.viewportMode)
    if (isNarrow) {
      setMobilePane('map')
      return
    }
    setSelectedTrip(next.selectedTrip)
  }

  function handleMarkerSelect(resultId) {
    const pool = visibleDestinations
    const match = tripFromMarkerId(pool, resultId)
    if (!match) return
    setSelectedDestinationId(match.id)
    setViewportMode('selected')
    if (!isNarrow) setSelectedTrip(match)
  }

  function handleShowAll() {
    setViewportMode('bounds')
  }

  function handleViewDetails(destination, event) {
    lastFocusRef.current = event?.currentTarget ?? document.activeElement
    const next = selectTripFromResult(destination)
    if (!next) return
    setSelectedDestinationId(next.selectedDestinationId)
    setSelectedTrip(next.selectedTrip)
    setViewportMode(next.viewportMode)
  }

  function handleCloseDetails() {
    const cleared = clearTripSelection()
    setSelectedTrip(cleared.selectedTrip)
    setSelectedDestinationId(cleared.selectedDestinationId)
    setViewportMode(cleared.viewportMode)
    if (isNarrow) {
      requestAnimationFrame(() => lastFocusRef.current?.focus?.())
    }
  }

  function handleRefine(preference) {
    if (!tripRequest || busy) return
    if (dateRangeError(form)) return
    const feedback = refinementFeedbackText(preference)
    if (shouldRecommendInsteadOfRefine(form, tripRequest)) {
      runRecommend(feedback, { mode: 'fresh', userMessage: preference })
      return
    }
    runRefine(feedback, { label: preference })
  }

  async function refreshSavedFlights() {
    if (!userId) return
    setSavedLoading(true)
    try {
      setSavedItems(await loadAdaptedSavedFlights())
      setSavedError('')
    } catch (error) {
      if (error?.name === 'AbortError') return
      setSavedError(error?.message || 'Could not load saved flights.')
    } finally {
      setSavedLoading(false)
    }
  }

  async function handleToggleSaved(destination) {
    const reference = flightReferenceFromDestination(destination)
    if (!reference.flight_id) return
    const alreadySaved = savedIds.includes(reference.flight_id) || savedIds.includes(destination.id)
    const previous = savedItems

    if (alreadySaved) {
      setSavedItems((current) =>
        current.filter((item) => item.id !== reference.flight_id && item.id !== destination.id),
      )
      try {
        await deleteSavedFlight(reference.flight_id)
        setSavedError('')
      } catch (error) {
        setSavedItems(previous)
        setSavedError(error?.message || 'Could not remove that saved flight.')
      }
      return
    }

    const optimistic = adaptSavedFlight({
      flight_id: reference.flight_id,
      origin_id: reference.origin_id,
      saved_at: new Date().toISOString(),
      last_checked_at: new Date().toISOString(),
      saved_price: reference.price,
      last_checked_price: reference.price,
      price_changed: false,
      availability: 'available',
      explanation: destination.explanation,
      flight: {
        id: reference.flight_id,
        origin_id: reference.origin_id,
        origin_iata: destination.originIata,
        destination_city: destination.destination?.city,
        destination_country: destination.country?.common_name,
        destination_country_code: destination.destination?.country_code,
        price_eur: reference.price,
        currency: destination.flight?.currency,
        latitude: destination.destination?.latitude,
        longitude: destination.destination?.longitude,
        photo_url: destination.photoUrl,
        photo_url_small: destination.photoUrlSmall,
      },
    })
    setSavedItems((current) => [
      optimistic,
      ...current.filter((item) => item.id !== reference.flight_id),
    ])
    try {
      const saved = await saveFlight(reference)
      const adapted = keepSavedFlightPhotos(adaptSavedFlight(saved), destination)
      const withPhotos = await attachCityPhotos([adapted])
      setSavedItems((current) => [
        withPhotos[0] || adapted,
        ...current.filter((item) => item.id !== adapted.id && item.id !== reference.flight_id),
      ])
      setSavedError('')
    } catch (error) {
      setSavedItems(previous)
      setSavedError(error?.message || 'Could not save that flight.')
    }
  }

  function handlePreview(destination) {
    const city = destination.destination?.city || 'this destination'
    const price = Number(destination.flight?.price)
    const nextForm = {
      ...initialForm,
      originId: selectedOrigin?.originId || '',
      originIata: selectedOrigin?.iata || '',
      maxBudget: Number.isFinite(price) ? Math.max(400, price) : 400,
    }
    setPendingSelectId(destination.id)
    runRecommend(`A getaway to ${city}`, { nextForm, origin: selectedOrigin, mode: 'fresh' })
  }

  function handleExploreDestinations() {
    document.getElementById('destination-previews')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function handleHistory(item) {
    const origin = item.origin || selectedOrigin
    if (origin) setSelectedOrigin(origin)
    runRecommend(item.text || item.title, {
      mode: 'fresh',
      nextForm: item.filters || form,
      origin,
    })
  }

  if (path === ROUTES.login) {
    return <LoginPage />
  }

  if (path === ROUTES.signup) {
    return <SignupPage />
  }

  if (!isPlannerPath(path)) {
    return <LandingPage />
  }

  if (authLoading || !user) {
    return <div className={styles.workspace}>Loading your account…</div>
  }

  const composerPlaceholder = composerPlaceholderFor(clarifyKind)

  return (
    <div
      className={styles.workspace}
      data-mode={showMap ? 'results' : 'welcome'}
      data-pane={mobilePane}
    >
      <Sidebar
        view={view}
        history={history}
        savedCount={savedIds.length}
        user={user}
        onLogout={logout}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewTrip={handleNewTrip}
        onExplore={() => {
          setView('explore')
          setSidebarOpen(false)
        }}
        onSaved={() => {
          setView('saved')
          setFiltersOpen(false)
          setSidebarOpen(false)
          setMobilePane('list')
          refreshSavedFlights()
        }}
        onHistory={handleHistory}
      />

      <div className={styles.center}>
        <div className={styles.mobileBar}>
          <button type="button" className={styles.iconBtn} aria-label="Open navigation" onClick={() => setSidebarOpen(true)}>
            <Menu size={18} />
          </button>
          <AppLink to={ROUTES.home} className={styles.mobileTitle}>
            Travel Planner
          </AppLink>
          {showMap && (
            <div className={styles.paneToggle} role="group" aria-label="List or map">
              <button
                type="button"
                className={mobilePane === 'list' ? styles.paneOn : styles.paneOff}
                aria-pressed={mobilePane === 'list'}
                onClick={() => setMobilePane('list')}
              >
                <List size={16} />
                List
              </button>
              <button
                type="button"
                className={mobilePane === 'map' ? styles.paneOn : styles.paneOff}
                aria-pressed={mobilePane === 'map'}
                onClick={() => setMobilePane('map')}
              >
                <MapIcon size={16} />
                Map
              </button>
            </div>
          )}
          {hasSearched && showPlannerFilters(view) && (
            <button type="button" className={styles.iconBtn} aria-label="Open filters" onClick={() => setFiltersOpen(true)}>
              <SlidersHorizontal size={18} />
            </button>
          )}
        </div>

        <div className={styles.centerMain}>
          <div className={styles.centerScroll}>
          {error && showPlannerConversation(view, hasSearched) && <p className={styles.noticeError}>{error}</p>}
          {flightWarning && showPlannerConversation(view, hasSearched) && <p className={styles.notice}>{flightWarning}</p>}
          {savedError && view === 'explore' && <p className={styles.noticeError}>{savedError}</p>}

          {view === 'saved' ? (
            <SavedPane
              destinations={savedItems}
              loading={savedLoading}
              error={savedError}
              selectedId={selectedDestinationId}
              savedIds={savedIds}
              onSelect={handleSelectDestination}
              onToggleSaved={handleToggleSaved}
              onViewDetails={handleViewDetails}
              onExplore={() => setView('explore')}
            />
          ) : showPlannerConversation(view, hasSearched) ? (
            <>
              <div className={styles.desktopTools}>
                <button type="button" className={styles.ghostBtn} onClick={() => setFiltersOpen(true)}>
                  <SlidersHorizontal size={16} />
                  Filters
                </button>
              </div>
              <ConversationPane
                messages={messages}
                filters={appliedFilters}
                originLabel={formatOriginLabel(selectedOrigin)}
                tripRequest={tripRequest}
                preferences={parsedPreferences}
                dataSource={dataSource}
                dateFallback={dateFallback}
                rejectedCount={rejected.length}
                results={results}
                previousRanks={previousRanks}
                selectedId={selectedDestinationId}
                savedIds={savedIds}
                loading={loading}
                refining={refining}
                phase={conversationPhase}
                activeRefinement={activeRefinement}
                canRefine={Boolean(tripRequest)}
                onRefine={handleRefine}
                onSelect={handleSelectDestination}
                onToggleSaved={handleToggleSaved}
                onViewDetails={handleViewDetails}
              />
            </>
          ) : (
            <>
              {messages.length > 0 && (
                <div className={styles.welcomeMessages}>
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={message.role === 'user' ? styles.bubbleUser : styles.bubbleAssistant}
                    >
                      {message.role !== 'user' && <small>Planner service</small>}
                      <p>{message.text}</p>
                    </div>
                  ))}
                </div>
              )}
              <WelcomePane onPrompt={handleStarter} composerRef={composerRef} />
              {isNarrow && (
                <InspirationPanel
                  destinations={[]}
                  onPlan={() => originInputRef.current?.focus()}
                  onExplore={handleExploreDestinations}
                  onSelectDestination={handlePreview}
                />
              )}
            </>
          )}
        </div>

          {showPlannerComposer(view) && (
            <div className={styles.composerFields}>
              <div className={styles.tripFields}>
                <OriginSelect
                  value={selectedOrigin}
                  onChange={handleOriginChange}
                  error={originError}
                  inputRef={originInputRef}
                />
                <TripDateFields
                  departureDate={form.departureDate || ''}
                  returnDate={form.returnDate || ''}
                  onChange={handleDateChange}
                  error={dateError}
                  disabled={busy}
                />
              </div>
              <p id="trip-date-hint" className={styles.dateHint}>
                Form dates are used when filled. Leave them blank to use dates from your message. Dates
                you type in the message take precedence over the date fields.
              </p>
              {dateError ? (
                <p id="trip-date-error" className={styles.originError} role="alert">
                  {dateError}
                </p>
              ) : null}
            </div>
          )}

          <TripDetailsDrawer
            destination={detailsTrip}
            onClose={handleCloseDetails}
            isSaved={Boolean(detailsTrip && savedIds.includes(detailsTrip.id))}
            onToggleSaved={handleToggleSaved}
            moods={parsedPreferences?.moods}
            activitiesEnabled={Boolean(detailsTrip)}
          />
        </div>

        {showPlannerComposer(view) && (
          <div className={styles.composerDock}>
            <Composer
              inputRef={composerRef}
              draft={draft}
              onDraftChange={setDraft}
              onSubmit={handleComposerSubmit}
              loading={busy}
              placeholder={composerPlaceholder}
            />
          </div>
        )}
      </div>

      <div className={styles.right}>
        {showInspiration && !isNarrow && (
          <InspirationPanel
            destinations={[]}
            onPlan={() => originInputRef.current?.focus()}
            onExplore={handleExploreDestinations}
            onSelectDestination={handlePreview}
          />
        )}
        {showMap && (
          <DestinationMap
            results={mapResults}
            selectedId={selectedDestinationId}
            viewportMode={viewportMode}
            onSelectMarker={handleMarkerSelect}
            onShowAll={handleShowAll}
          />
        )}
      </div>

      {showPlannerFilters(view) && (
        <FiltersPopover
          open={filtersOpen}
          form={form}
          maxBudgetCap={maxBudgetCap}
          onChange={handleFilterChange}
          onReset={handleResetFilters}
          onClose={() => setFiltersOpen(false)}
        />
      )}
    </div>
  )
}
