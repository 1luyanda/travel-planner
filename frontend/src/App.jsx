import { useEffect, useRef, useState } from 'react'
import { List, Map as MapIcon, Menu, SlidersHorizontal } from 'lucide-react'
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
import TripDetailsPanel from './components/TripDetailsPanel'
import LandingPage from './components/LandingPage'
import { fetchFlights, recommendTrip, refineTrip, searchOrigins } from './services/travelApi'
import {
  adaptRecommendations,
  attachDestinationCityPhotos,
  enrichRecommendations,
} from './utils/adaptRecommendations'
import {
  INITIAL_PLANNER_FORM,
  assistantTextForResponse,
  buildClarificationRecommendPayload,
  buildRecommendPayload,
  composerPlaceholderFor,
  createClarificationContext,
  dateRangeError,
  describePlannerDates,
  formFieldsForClarification,
  formFieldsFromPlanner,
  formPatchFromTripRequest,
  isClarificationQuestionText,
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
import { loadSavedIds, persistSavedIds, toggleSavedId } from './utils/savedDestinations'
import {
  clearTripSelection,
  resolveSelectedTrip,
  selectTripFromResult,
  selectionAfterPoolChange,
  tripFromMarkerId,
} from './utils/tripDetailsSelection'
import { AppLink, ROUTES, isPlannerPath, useRoute } from './utils/routes.jsx'
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
  const [form, setForm] = useState(initialForm)
  const [selectedOrigin, setSelectedOrigin] = useState(null)
  const [searchSnapshot, setSearchSnapshot] = useState(initialForm)
  const [tripRequest, setTripRequest] = useState(null)
  const [pendingSearchText, setPendingSearchText] = useState('')
  const [clarifyKind, setClarifyKind] = useState(null)
  const [clarification, setClarification] = useState(null)
  const [clarificationQuestions, setClarificationQuestions] = useState([])
  const [parsedPreferences, setParsedPreferences] = useState(null)
  const [rejected, setRejected] = useState([])
  const [dataSource, setDataSource] = useState(null)
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
  const [savedIds, setSavedIds] = useState(() => loadSavedIds())
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
  const resultsRef = useRef([])

  useEffect(() => {
    tripRequestRef.current = tripRequest
  }, [tripRequest])

  useEffect(() => {
    resultsRef.current = results
  }, [results])

  const prices = results.map((item) => Number(item.flight?.price)).filter((value) => Number.isFinite(value))
  const maxBudgetCap = prices.length
    ? Math.max(...prices, Number(form.maxBudget) || 0)
    : Math.max(500, Number(form.maxBudget) || 0)
  const savedDestinations = results.filter((item) => savedIds.includes(item.id))
  const rankedSaved = results.filter((item) => savedIds.includes(item.id))
  const mapResults = view === 'saved' ? rankedSaved : results
  const detailsTrip = resolveSelectedTrip(mapResults, selectedTrip)
  const showMap = view === 'saved' || hasSearched
  const showInspiration = view === 'explore' && !hasSearched
  const splitRight = showMap && !isNarrow
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
    persistSavedIds(savedIds)
  }, [savedIds])

  useEffect(() => {
    if (path !== ROUTES.home && !isPlannerPath(path)) {
      navigate(ROUTES.home, { replace: true })
    }
  }, [navigate, path])

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
    const pool = view === 'saved' ? savedDestinations : results
    const next = selectionAfterPoolChange(pool, selectedTrip, selectedDestinationId)
    if (next.selectedDestinationId !== selectedDestinationId) {
      setSelectedDestinationId(next.selectedDestinationId)
    }
    if ((next.selectedTrip?.id || null) !== (selectedTrip?.id || null)) {
      setSelectedTrip(next.selectedTrip)
    }
  }, [results, savedDestinations, selectedDestinationId, selectedTrip, view])

  useEffect(() => {
    if (!pendingSelectId) return
    const pool = view === 'saved' ? savedDestinations : results
    if (pool.some((item) => item.id === pendingSelectId)) {
      setSelectedDestinationId(pendingSelectId)
      setViewportMode('selected')
      setPendingSelectId(null)
    }
  }, [pendingSelectId, results, savedDestinations, view])

  function invalidateResults() {
    setHasSearched(false)
    setResults([])
    setRejected([])
    setDataSource(null)
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
  }

  function handleOriginChange(origin) {
    const same = origin?.originId && origin.originId === selectedOrigin?.originId
    setSelectedOrigin(origin)
    setForm((current) => ({
      ...current,
      originId: origin?.originId || '',
      originIata: origin?.iata || '',
    }))
    setOriginError('')
    if (hasSearched && !same) invalidateResults()
  }

  async function enrichMappedResults(mapped, originId, signal, seq) {
    let next = mapped
    if (originId) {
      try {
        const flights = await fetchFlights({ origin_id: originId }, { signal })
        if (seq !== searchSeqRef.current) return mapped
        next = enrichRecommendations(mapped, flights)
      } catch (err) {
        if (err?.name === 'AbortError') throw err
        if (seq === searchSeqRef.current) {
          setFlightWarning('Trips loaded from stored data, but map pins and some flight details are unavailable.')
        }
      }
    }

    const cities = [
      ...new Set(next.map((item) => item?.destination?.city).filter(Boolean)),
    ]
    if (!cities.length) return next
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
      if (seq !== searchSeqRef.current) return next
      return attachDestinationCityPhotos(next, batches.flat())
    } catch (err) {
      if (err?.name === 'AbortError') throw err
      return next
    }
  }

  async function runRecommend(userText, options = {}) {
    const {
      nextForm = form,
      origin = selectedOrigin,
      mode = 'fresh',
      userMessage = null,
    } = options
    const typed = (userText || '').trim()
    const apiText = mode === 'filters' ? pendingSearchText || typed : typed
    if (mode !== 'clarify' && !apiText) return
    if (mode === 'clarify' && !typed) return

    const seq = ++searchSeqRef.current
    searchAbortRef.current?.abort()
    searchAbortRef.current?.dispose?.()
    const request = createPlannerRequest()
    searchAbortRef.current = request

    setLoading(true)
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
    }
    if (userMessage || typed) {
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'user', text: userMessage || typed },
      ])
    }

    if (mode === 'fresh') {
      setTripRequest(null)
      setResults([])
      setRejected([])
      setPreviousRanks({})
      setActiveRefinement(null)
    } else if (mode === 'clarify') {
      setResults([])
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
            })
      setClarifyKind('recommend')
      setClarification(nextContext)
      setClarificationQuestions(response.clarification_questions)
      setParsedPreferences(response.preferences || null)
      setResults([])
      setRejected(response.rejected)
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
    setAppliedFilters(nextForm)
    setResults(adapted.results)
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
      const enriched = await enrichMappedResults(
        adapted.results,
        adapted.originId || response.origin_id,
        request.signal,
        seq,
      )
      if (seq !== searchSeqRef.current) return
      setResults(enriched)
    } catch (err) {
      if (err?.name === 'AbortError' || seq !== searchSeqRef.current) return
      setFlightWarning('Trips loaded from stored data, but map pins and some flight details are unavailable.')
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
        execute: (signal) => refineTrip({ text, request: savedRequest }, { signal }),
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
      setRejected(adapted.rejected)
      setDataSource(adapted.dataSource)
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
        const enriched = await enrichMappedResults(
          adapted.results,
          adapted.originId || response.origin_id,
          request.signal,
          seq,
        )
        if (seq !== searchSeqRef.current) return
        setResults(enriched)
      } catch (err) {
        if (err?.name === 'AbortError' || seq !== searchSeqRef.current) return
        setFlightWarning('Trips loaded from stored data, but map pins and some flight details are unavailable.')
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
    runRecommend(pendingSearchText, {
      nextForm: next,
      mode: 'filters',
      userMessage: 'Updated filters',
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
    setDataSource(null)
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
    const pool = view === 'saved' ? rankedSaved : results
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

  function handleToggleSaved(destination) {
    setSavedIds((current) => toggleSavedId(current, destination.id))
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

  if (!isPlannerPath(path)) {
    return <LandingPage />
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
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewTrip={handleNewTrip}
        onExplore={() => {
          setView('explore')
          setSidebarOpen(false)
        }}
        onSaved={() => {
          setView('saved')
          setSidebarOpen(false)
          setMobilePane('list')
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
          {hasSearched && view === 'explore' && (
            <button type="button" className={styles.iconBtn} aria-label="Open filters" onClick={() => setFiltersOpen(true)}>
              <SlidersHorizontal size={18} />
            </button>
          )}
        </div>

        <div className={styles.centerScroll}>
          {error && hasSearched && view === 'explore' && <p className={styles.noticeError}>{error}</p>}
          {flightWarning && hasSearched && view === 'explore' && <p className={styles.notice}>{flightWarning}</p>}

          {view === 'saved' ? (
            <SavedPane
              destinations={rankedSaved}
              selectedId={selectedDestinationId}
              savedIds={savedIds}
              onSelect={handleSelectDestination}
              onToggleSaved={handleToggleSaved}
              onViewDetails={handleViewDetails}
              onExplore={() => setView('explore')}
            />
          ) : hasSearched ? (
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

        <div className={styles.composerDock}>
          <p className={styles.dockHint}>Stored travel data · Snapshot, not live fares</p>
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
            Form dates are used when filled. Leave them blank to use dates from your message. If
            they disagree, the planner will ask which to keep.
          </p>
          {dateError ? (
            <p id="trip-date-error" className={styles.originError} role="alert">
              {dateError}
            </p>
          ) : null}
          <Composer
            inputRef={composerRef}
            draft={draft}
            onDraftChange={setDraft}
            onSubmit={handleComposerSubmit}
            loading={busy}
            placeholder={composerPlaceholder}
          />
        </div>
      </div>

      <div className={splitRight ? `${styles.right} ${styles.rightSplit}` : styles.right}>
        {showInspiration && !isNarrow && (
          <InspirationPanel
            destinations={[]}
            onPlan={() => originInputRef.current?.focus()}
            onExplore={handleExploreDestinations}
            onSelectDestination={handlePreview}
          />
        )}
        {splitRight && (
          <TripDetailsPanel
            destination={detailsTrip}
            isSaved={Boolean(detailsTrip && savedIds.includes(detailsTrip.id))}
            onToggleSaved={handleToggleSaved}
            onClose={handleCloseDetails}
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

      <FiltersPopover
        open={filtersOpen}
        form={form}
        maxBudgetCap={maxBudgetCap}
        onChange={handleFilterChange}
        onReset={handleResetFilters}
        onClose={() => setFiltersOpen(false)}
      />

      {isNarrow && (
        <TripDetailsDrawer
          destination={detailsTrip}
          onClose={handleCloseDetails}
          isSaved={Boolean(detailsTrip && savedIds.includes(detailsTrip.id))}
          onToggleSaved={handleToggleSaved}
        />
      )}
    </div>
  )
}
