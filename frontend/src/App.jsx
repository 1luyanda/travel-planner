import { useEffect, useRef, useState } from 'react'
import { List, Map as MapIcon, Menu, SlidersHorizontal } from 'lucide-react'
import { useAuth } from './auth/AuthProvider'
import Sidebar from './components/Sidebar'
import Composer from './components/Composer'
import OriginSelect from './components/OriginSelect'
import WelcomePane from './components/WelcomePane'
import InspirationPanel from './components/InspirationPanel'
import ConversationPane from './components/ConversationPane'
import SavedPane from './components/SavedPane'
import DestinationMap from './components/DestinationMap'
import FiltersPopover from './components/FiltersPopover'
import TripDetailsDrawer from './components/TripDetailsDrawer'
import LandingPage from './components/LandingPage'
import { fetchCandidates, fetchFlights } from './services/travelApi'
import { adaptSearchResults, snapshotLabel } from './utils/adaptResults'
import { parsePrompt } from './utils/parsePrompt'
import { ORIGIN_REQUIRED_MESSAGE, formatOriginLabel, requireSelectedOrigin } from './utils/origins'
import { loadSavedIds, persistSavedIds, toggleSavedId } from './utils/savedDestinations'
import { AppLink, ROUTES, isPlannerPath, useRoute } from './utils/routes.jsx'
import { buildCandidateQuery, buildFlightQuery } from './utils/searchQuery'
import { applyBrowserRanking } from './utils/ranking'
import styles from './workspace.module.css'

const initialForm = {
  originId: '',
  originIata: '',
  maxBudget: 400,
  directOnly: false,
  preferWarm: false,
  mood: '',
}

function nextId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function describeResults(results, filters, { dataSource, unmappedCount, rejectedCount } = {}) {
  const count = results.length
  const cities = [...new Set(results.map((item) => item.destination?.city).filter(Boolean))]
  const budget = filters?.maxBudget != null ? ` up to €${filters.maxBudget}` : ''
  const source = snapshotLabel(dataSource)
  const sourceLine = source ? ` ${source}.` : ' Stored travel data.'
  if (count === 0) {
    const rejected = rejectedCount ? ` ${rejectedCount} stored offer(s) were excluded as incomplete.` : ''
    return `No stored trips match those filters${budget}.${rejected} This is a snapshot — not a live search, booking, or AI.`
  }
  const noun = count === 1 ? 'trip' : 'trips'
  const cityLine = cities.length ? ` Shortlist: ${cities.join(', ')}.` : ''
  const mapLine = unmappedCount
    ? ` ${unmappedCount} listed ${unmappedCount === 1 ? 'trip has' : 'trips have'} no mappable coordinates.`
    : ''
  return `I found ${count} matching ${noun} in the stored snapshot${budget}.${cityLine}${mapLine} Ranked in the browser by price, weather, stops, and duration.${sourceLine} Not live or bookable.`
}

export default function App() {
  const { path, navigate } = useRoute()
  const { user, loading: authLoading, logout } = useAuth()
  const userId = user?.id || null
  const [form, setForm] = useState(initialForm)
  const [selectedOrigin, setSelectedOrigin] = useState(null)
  const [searchSnapshot, setSearchSnapshot] = useState(initialForm)
  const [adaptedResults, setAdaptedResults] = useState([])
  const [rejected, setRejected] = useState([])
  const [dataSource, setDataSource] = useState(null)
  const [results, setResults] = useState([])
  const [weights, setWeights] = useState(null)
  const [previousRanks, setPreviousRanks] = useState({})
  const [appliedFilters, setAppliedFilters] = useState(null)
  const [selectedTrip, setSelectedTrip] = useState(null)
  const [selectedDestinationId, setSelectedDestinationId] = useState(null)
  const [viewportMode, setViewportMode] = useState('bounds')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [flightWarning, setFlightWarning] = useState('')
  const [hasSearched, setHasSearched] = useState(false)
  const [view, setView] = useState('explore')
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState([])
  const [history, setHistory] = useState([])
  const [savedIds, setSavedIds] = useState([])
  const [savedOwner, setSavedOwner] = useState(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mobilePane, setMobilePane] = useState('list')
  const [pendingSelectId, setPendingSelectId] = useState(null)
  const [originError, setOriginError] = useState('')
  const [focusOrigin, setFocusOrigin] = useState(false)
  const [isNarrow, setIsNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 780px)').matches,
  )
  const lastFocusRef = useRef(null)
  const composerRef = useRef(null)
  const originInputRef = useRef(null)
  const searchAbortRef = useRef(null)
  const searchSeqRef = useRef(0)

  const prices = adaptedResults.map((item) => Number(item.flight?.price)).filter((value) => Number.isFinite(value))
  const maxBudgetCap = prices.length ? Math.max(...prices, Number(form.maxBudget) || 0) : Math.max(500, Number(form.maxBudget) || 0)
  const savedDestinations = adaptedResults.filter((item) => savedIds.includes(item.id))
  const rankedSaved = results.filter((item) => savedIds.includes(item.id))
  const mapResults = view === 'saved' ? rankedSaved : results
  const drawerTrip = selectedTrip
    ? (view === 'saved' ? rankedSaved : results).find((item) => item.id === selectedTrip.id) || selectedTrip
    : null
  const showMap = view === 'saved' || hasSearched
  const showInspiration = view === 'explore' && !hasSearched

  useEffect(() => {
    const ownerId = user?.id || null
    setSavedIds(ownerId ? loadSavedIds(ownerId) : [])
    setSavedOwner(ownerId)
  }, [user])

  useEffect(() => {
    if (user && savedOwner === user.id) {
      persistSavedIds(user.id, savedIds)
    }
  }, [savedIds, savedOwner, user])

  const previousWorkspaceUserRef = useRef(undefined)
  useEffect(() => {
    if (previousWorkspaceUserRef.current === userId) return
    previousWorkspaceUserRef.current = userId

    searchAbortRef.current?.abort()
    searchSeqRef.current += 1
    setForm(initialForm)
    setSelectedOrigin(null)
    setSearchSnapshot(initialForm)
    setAdaptedResults([])
    setRejected([])
    setDataSource(null)
    setResults([])
    setWeights(null)
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
    if (path !== ROUTES.home && !isPlannerPath(path)) {
      navigate(ROUTES.home, { replace: true })
    }
  }, [navigate, path])

  useEffect(() => {
    if (!authLoading && isPlannerPath(path) && !user) {
      navigate(ROUTES.home, { replace: true })
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
    const pool = view === 'saved' ? savedDestinations : results
    if (selectedDestinationId && !pool.some((item) => item.id === selectedDestinationId)) {
      setSelectedDestinationId(null)
    }
    if (selectedTrip && !pool.some((item) => item.id === selectedTrip.id)) {
      setSelectedTrip(null)
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

  function ensureOrigin(origin = selectedOrigin) {
    const check = requireSelectedOrigin(origin)
    if (check.ok) {
      setOriginError('')
      return true
    }
    setOriginError(ORIGIN_REQUIRED_MESSAGE)
    setFocusOrigin(true)
    return false
  }

  function invalidateResults() {
    setHasSearched(false)
    setResults([])
    setAdaptedResults([])
    setRejected([])
    setDataSource(null)
    setAppliedFilters(null)
    setWeights(null)
    setPreviousRanks({})
    setSelectedTrip(null)
    setSelectedDestinationId(null)
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

  async function runSearch(nextForm, userText, refinement = null, origin = selectedOrigin) {
    if (!ensureOrigin(origin)) {
      if (userText) setDraft(userText)
      return
    }

    const requestForm = {
      ...nextForm,
      originId: origin.originId,
      originIata: origin.iata || '',
    }
    const candidateQuery = buildCandidateQuery(requestForm)
    if (!candidateQuery) {
      setOriginError(ORIGIN_REQUIRED_MESSAGE)
      setFocusOrigin(true)
      return
    }

    const seq = ++searchSeqRef.current
    searchAbortRef.current?.abort()
    const controller = new AbortController()
    searchAbortRef.current = controller

    setLoading(true)
    setError('')
    setFlightWarning('')
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setViewportMode('bounds')
    setView('explore')
    setMobilePane('list')
    setSidebarOpen(false)
    setFiltersOpen(false)
    const text = userText || requestForm.mood || 'Find my getaway'
    setForm(requestForm)
    setMessages((current) => [...current, { id: nextId(), role: 'user', text }])

    try {
      const flightQuery = buildFlightQuery(candidateQuery)
      const [candidateResult, flightResult] = await Promise.allSettled([
        fetchCandidates(candidateQuery, { signal: controller.signal }),
        fetchFlights(flightQuery, { signal: controller.signal }),
      ])

      if (seq !== searchSeqRef.current) return
      if (candidateResult.status === 'rejected') throw candidateResult.reason

      const candidatesResponse = candidateResult.value
      let flightsResponse = null
      if (flightResult.status === 'fulfilled') {
        flightsResponse = flightResult.value
      } else if (flightResult.reason?.name !== 'AbortError') {
        setFlightWarning('Trips loaded from stored data, but map pins and some flight details are unavailable.')
      }

      const adapted = adaptSearchResults({
        candidatesResponse,
        flightsResponse,
        selectedOrigin: origin,
      })
      const { weights: nextWeights, ranked } = applyBrowserRanking(
        adapted.results,
        requestForm.preferWarm,
        refinement,
      )
      const unmappedCount = ranked.filter(
        (item) => item.destination?.latitude == null || item.destination?.longitude == null,
      ).length

      setAdaptedResults(adapted.results)
      setRejected(adapted.rejected)
      setDataSource(adapted.dataSource)
      setAppliedFilters(requestForm)
      setWeights(nextWeights)
      setResults(ranked)
      setSearchSnapshot(requestForm)
      setPreviousRanks({})
      setHasSearched(true)
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: 'assistant',
          text: describeResults(ranked, requestForm, {
            dataSource: adapted.dataSource,
            unmappedCount,
            rejectedCount: adapted.rejected.length,
          }),
        },
      ])
      setHistory((current) => {
        const item = {
          id: nextId(),
          title: text.slice(0, 52),
          filters: requestForm,
          origin,
          refinement,
        }
        return [item, ...current.filter((entry) => entry.title !== item.title)].slice(0, 8)
      })
    } catch (err) {
      if (err?.name === 'AbortError' || seq !== searchSeqRef.current) return
      const message = err.message || 'Could not load stored travel data.'
      setResults([])
      setAdaptedResults([])
      setRejected([])
      setDataSource(null)
      setWeights(null)
      setAppliedFilters(null)
      setHasSearched(true)
      setError(message)
      setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
    } finally {
      if (seq === searchSeqRef.current) setLoading(false)
    }
  }

  function handleComposerSubmit(event) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || loading) return
    if (!ensureOrigin()) return
    setDraft('')
    const parsed = parsePrompt(text)
    if (!parsed.ok) {
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'user', text },
        { id: nextId(), role: 'assistant', text: parsed.message },
      ])
      return
    }
    runSearch(
      {
        ...form,
        ...parsed.filters,
        originId: selectedOrigin.originId,
        originIata: selectedOrigin.iata || '',
      },
      text,
      parsed.refinement,
    )
  }

  function handleStarter(prompt) {
    if (!ensureOrigin()) {
      setDraft(prompt)
      return
    }
    setDraft('')
    const parsed = parsePrompt(prompt)
    if (!parsed.ok) return
    runSearch(
      {
        ...initialForm,
        ...parsed.filters,
        originId: selectedOrigin.originId,
        originIata: selectedOrigin.iata || '',
      },
      prompt,
      parsed.refinement,
    )
  }

  function handleFilterChange(field, value) {
    const next = { ...form, [field]: value }
    setForm(next)
    if (!hasSearched) return
    if (field === 'preferWarm') {
      const { weights: nextWeights, ranked } = applyBrowserRanking(adaptedResults, value)
      setWeights(nextWeights)
      setResults(ranked)
      setPreviousRanks({})
      return
    }
    if (field === 'maxBudget' || field === 'directOnly') {
      runSearch(next, next.mood || 'Updated filters')
    }
  }

  function handleResetFilters() {
    const restored = searchSnapshot || initialForm
    setForm(restored)
    if (!hasSearched) return
    runSearch(restored, restored.mood || 'Reset filters')
  }

  function handleNewTrip() {
    searchAbortRef.current?.abort()
    setHasSearched(false)
    setView('explore')
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setError('')
    setFlightWarning('')
    setPreviousRanks({})
    setResults([])
    setAdaptedResults([])
    setRejected([])
    setDataSource(null)
    setWeights(null)
    setAppliedFilters(null)
    setMessages([])
    setDraft('')
    setForm(initialForm)
    setSelectedOrigin(null)
    setOriginError('')
    setFiltersOpen(false)
    setSidebarOpen(false)
    setMobilePane('list')
    setViewportMode('bounds')
  }

  function handleSelectDestination(destination) {
    if (!destination?.id) return
    setSelectedDestinationId(destination.id)
    setViewportMode('selected')
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 780px)').matches) {
      setMobilePane('map')
    }
  }

  function handleMarkerSelect(resultId) {
    const pool = view === 'saved' ? rankedSaved : results
    const match = pool.find((item) => item.id === resultId)
    if (match) {
      setSelectedDestinationId(match.id)
      setViewportMode('selected')
    }
  }

  function handleShowAll() {
    setViewportMode('bounds')
  }

  function handleViewDetails(destination, event) {
    lastFocusRef.current = event?.currentTarget ?? document.activeElement
    setSelectedDestinationId(destination.id)
    setSelectedTrip(destination)
  }

  function handleCloseDrawer() {
    setSelectedTrip(null)
    requestAnimationFrame(() => lastFocusRef.current?.focus?.())
  }

  function handleRefine(preference) {
    if (!adaptedResults.length) return
    const oldRanks = Object.fromEntries(results.map((item, index) => [item.id, index + 1]))
    const { weights: nextWeights, ranked } = applyBrowserRanking(adaptedResults, form.preferWarm, preference)
    setPreviousRanks(oldRanks)
    setWeights(nextWeights)
    setResults(ranked)
    setViewportMode('bounds')
  }

  function handleToggleSaved(destination) {
    setSavedIds((current) => toggleSavedId(current, destination.id))
  }

  function handlePreview(destination) {
    const city = destination.destination?.city || 'this destination'
    const price = Number(destination.flight?.price)
    if (!ensureOrigin()) {
      setDraft(`A getaway to ${city}`)
      setPendingSelectId(destination.id)
      return
    }
    const nextForm = {
      ...initialForm,
      originId: selectedOrigin.originId,
      originIata: selectedOrigin.iata || '',
      mood: `A getaway to ${city}`,
      maxBudget: Number.isFinite(price) ? Math.max(400, price) : 400,
    }
    setPendingSelectId(destination.id)
    runSearch(nextForm, nextForm.mood)
  }

  function handleExploreDestinations() {
    document.getElementById('destination-previews')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function handleHistory(item) {
    const origin = item.origin || selectedOrigin
    if (!ensureOrigin(origin)) return
    setSelectedOrigin(origin)
    runSearch(item.filters, item.title, item.refinement, origin)
  }

  if (!isPlannerPath(path)) {
    return (
      <LandingPage />
    )
  }

  if (authLoading || !user) {
    return <div className={styles.workspace}>Loading your account…</div>
  }

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
              weights={weights}
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
                dataSource={dataSource}
                rejectedCount={rejected.length}
                weights={weights}
                results={results}
                previousRanks={previousRanks}
                selectedId={selectedDestinationId}
                savedIds={savedIds}
                loading={loading}
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
                      {message.role !== 'user' && <small>Stored snapshot</small>}
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
          <OriginSelect
            value={selectedOrigin}
            onChange={handleOriginChange}
            error={originError}
            inputRef={originInputRef}
          />
          <Composer
            inputRef={composerRef}
            draft={draft}
            onDraftChange={setDraft}
            onSubmit={handleComposerSubmit}
            loading={loading}
            placeholder="Ask for a mood or budget…"
          />
        </div>
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

      <FiltersPopover
        open={filtersOpen}
        form={form}
        maxBudgetCap={maxBudgetCap}
        onChange={handleFilterChange}
        onReset={handleResetFilters}
        onClose={() => setFiltersOpen(false)}
      />

      <TripDetailsDrawer destination={drawerTrip} weights={weights} onClose={handleCloseDrawer} />
    </div>
  )
}
