import { useEffect, useRef, useState } from 'react'
import { List, Map as MapIcon, Menu, SlidersHorizontal } from 'lucide-react'
import Sidebar from './components/Sidebar'
import Composer from './components/Composer'
import WelcomePane from './components/WelcomePane'
import InspirationPanel from './components/InspirationPanel'
import ConversationPane from './components/ConversationPane'
import SavedPane from './components/SavedPane'
import DestinationMap from './components/DestinationMap'
import FiltersPopover from './components/FiltersPopover'
import TripDetailsDrawer from './components/TripDetailsDrawer'
import LandingPage from './components/LandingPage'
import { fetchDestinations } from './services/destinationApi'
import { parsePrompt } from './utils/parsePrompt'
import { loadSavedIds, persistSavedIds, toggleSavedId } from './utils/savedDestinations'
import { AppLink, ROUTES, isPlannerPath, useRoute } from './utils/routes.jsx'
import {
  defaultWeights,
  filterDestinations,
  rankDestinations,
  refinementPresets,
  uniqueOrigins,
} from './utils/ranking'
import styles from './workspace.module.css'

const initialForm = {
  origin: '',
  maxBudget: 400,
  directOnly: false,
  preferWarm: false,
  mood: '',
}

function nextId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function describeResults(results, filters) {
  const count = results.length
  const cities = [...new Set(results.map((item) => item.destination?.city).filter(Boolean))]
  const budget = filters?.maxBudget != null ? ` up to €${filters.maxBudget}` : ''
  if (count === 0) {
    return `No mock destinations match those filters${budget}. Try a higher budget or fewer constraints. This is a demo — not a live search or AI.`
  }
  const noun = count === 1 ? 'trip' : 'trips'
  const cityLine = cities.length ? ` Shortlist: ${cities.join(', ')}.` : ''
  return `I found ${count} matching ${noun} in the mock dataset${budget}.${cityLine} Ranked locally by price, weather, stops, and duration. This is a demo — not a live search or AI.`
}

export default function App() {
  const { path, navigate } = useRoute()
  const [form, setForm] = useState(initialForm)
  const [searchSnapshot, setSearchSnapshot] = useState(initialForm)
  const [allDestinations, setAllDestinations] = useState([])
  const [results, setResults] = useState([])
  const [weights, setWeights] = useState(null)
  const [previousRanks, setPreviousRanks] = useState({})
  const [appliedFilters, setAppliedFilters] = useState(null)
  const [selectedTrip, setSelectedTrip] = useState(null)
  const [selectedDestinationId, setSelectedDestinationId] = useState(null)
  const [viewportMode, setViewportMode] = useState('bounds')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [prefetchError, setPrefetchError] = useState('')
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
  const [isNarrow, setIsNarrow] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 780px)').matches)
  const lastFocusRef = useRef(null)
  const composerRef = useRef(null)

  const origins = uniqueOrigins(allDestinations)
  const cities = [...new Set(allDestinations.map((item) => item.destination?.city).filter(Boolean))]
  const prices = allDestinations.map((item) => Number(item.flight?.price)).filter((value) => Number.isFinite(value))
  const maxBudgetCap = prices.length ? Math.max(...prices, Number(form.maxBudget) || 0) : Math.max(500, Number(form.maxBudget) || 0)
  const savedDestinations = allDestinations.filter((item) => savedIds.includes(item.id))
  const rankedSaved = weights ? rankDestinations(savedDestinations, weights) : savedDestinations
  const mapResults = view === 'saved' ? rankedSaved : results
  const drawerTrip = selectedTrip
    ? (view === 'saved' ? rankedSaved : results).find((item) => item.id === selectedTrip.id) || selectedTrip
    : null
  const showMap = view === 'saved' || hasSearched
  const showInspiration = view === 'explore' && !hasSearched

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
    fetchDestinations()
      .then((destinations) => {
        setAllDestinations(destinations)
        setPrefetchError('')
      })
      .catch((err) => setPrefetchError(err.message || 'Could not load destinations.'))
  }, [])

  useEffect(() => {
    const pool = view === 'saved'
      ? allDestinations.filter((item) => savedIds.includes(item.id))
      : results
    if (selectedDestinationId && !pool.some((item) => item.id === selectedDestinationId)) {
      setSelectedDestinationId(null)
    }
    if (selectedTrip && !pool.some((item) => item.id === selectedTrip.id)) {
      setSelectedTrip(null)
    }
  }, [results, allDestinations, savedIds, selectedDestinationId, selectedTrip, view])

  useEffect(() => {
    if (!pendingSelectId) return
    const pool = view === 'saved'
      ? allDestinations.filter((item) => savedIds.includes(item.id))
      : results
    if (pool.some((item) => item.id === pendingSelectId)) {
      setSelectedDestinationId(pendingSelectId)
      setViewportMode('selected')
      setPendingSelectId(null)
    }
  }, [pendingSelectId, results, allDestinations, savedIds, view])

  function changeForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function applyFilters(filters, nextWeights, destinations = allDestinations) {
    const ranked = rankDestinations(filterDestinations(destinations, filters), nextWeights)
    setAppliedFilters(filters)
    setWeights(nextWeights)
    setResults(ranked)
    setViewportMode('bounds')
  }

  async function runSearch(nextForm, userText, refinement = null) {
    setLoading(true)
    setError('')
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setViewportMode('bounds')
    setView('explore')
    setMobilePane('list')
    setSidebarOpen(false)
    setFiltersOpen(false)
    const text = userText || nextForm.mood || 'Find my getaway'
    setForm(nextForm)
    setMessages((current) => [...current, { id: nextId(), role: 'user', text }])

    try {
      const destinations = allDestinations.length ? allDestinations : await fetchDestinations()
      if (!allDestinations.length) setAllDestinations(destinations)
      let nextWeights = defaultWeights(nextForm.preferWarm)
      if (refinement && refinementPresets[refinement]) nextWeights = refinementPresets[refinement]
      const ranked = rankDestinations(filterDestinations(destinations, nextForm), nextWeights)
      applyFilters(nextForm, nextWeights, destinations)
      setSearchSnapshot(nextForm)
      setPreviousRanks({})
      setHasSearched(true)
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'assistant', text: describeResults(ranked, nextForm) },
      ])
      setHistory((current) => {
        const item = { id: nextId(), title: text.slice(0, 52), filters: nextForm, refinement }
        return [item, ...current.filter((entry) => entry.title !== item.title)].slice(0, 8)
      })
    } catch (err) {
      const message = err.message || 'Something went wrong while loading destinations.'
      setResults([])
      setWeights(null)
      setAppliedFilters(null)
      setHasSearched(true)
      setError(message)
      setMessages((current) => [...current, { id: nextId(), role: 'assistant', text: message }])
    } finally {
      setLoading(false)
    }
  }

  function handleComposerSubmit(event) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || loading) return
    setDraft('')
    const parsed = parsePrompt(text, { origins, cities })
    if (!parsed.ok) {
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'user', text },
        { id: nextId(), role: 'assistant', text: parsed.message },
      ])
      return
    }
    runSearch({ ...form, ...parsed.filters }, text, parsed.refinement)
  }

  function handleStarter(prompt) {
    setDraft('')
    const parsed = parsePrompt(prompt, { origins, cities })
    if (!parsed.ok) return
    runSearch({ ...initialForm, ...parsed.filters }, prompt, parsed.refinement)
  }

  function handleFilterChange(field, value) {
    const next = { ...form, [field]: value }
    setForm(next)
    if (!hasSearched) return
    const nextWeights = field === 'preferWarm' ? defaultWeights(value) : weights || defaultWeights(next.preferWarm)
    applyFilters(next, nextWeights)
    setPreviousRanks({})
  }

  function handleResetFilters() {
    const restored = searchSnapshot || initialForm
    setForm(restored)
    if (!hasSearched) return
    applyFilters(restored, defaultWeights(restored.preferWarm))
    setPreviousRanks({})
  }

  function handleNewTrip() {
    setHasSearched(false)
    setView('explore')
    setSelectedTrip(null)
    setSelectedDestinationId(null)
    setError('')
    setPreviousRanks({})
    setResults([])
    setWeights(null)
    setAppliedFilters(null)
    setMessages([])
    setDraft('')
    setForm(initialForm)
    setFiltersOpen(false)
    setSidebarOpen(false)
    setMobilePane('list')
    setViewportMode('bounds')
  }

  function handleLandingDestination(destination) {
    handlePreview(destination)
    navigate(ROUTES.planner)
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
    const nextWeights = refinementPresets[preference]
    if (!nextWeights || !results.length) return
    const oldRanks = Object.fromEntries(results.map((item, index) => [item.id, index + 1]))
    const filtered = filterDestinations(allDestinations, appliedFilters || form)
    setPreviousRanks(oldRanks)
    setWeights(nextWeights)
    setResults(rankDestinations(filtered, nextWeights))
    setViewportMode('bounds')
  }

  function handleToggleSaved(destination) {
    setSavedIds((current) => toggleSavedId(current, destination.id))
  }

  function handlePreview(destination) {
    const city = destination.destination?.city || 'this destination'
    const price = Number(destination.flight?.price)
    const nextForm = {
      ...initialForm,
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
    runSearch(item.filters, item.title, item.refinement)
  }

  if (!isPlannerPath(path)) {
    return (
      <LandingPage
        destinations={allDestinations}
        onSelectDestination={handleLandingDestination}
      />
    )
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
          {prefetchError && !hasSearched && <p className={styles.noticeError}>{prefetchError}</p>}
          {error && hasSearched && view === 'explore' && <p className={styles.noticeError}>{error}</p>}

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
                      {message.role !== 'user' && <small>Demo response</small>}
                      <p>{message.text}</p>
                    </div>
                  ))}
                </div>
              )}
              <WelcomePane onPrompt={handleStarter} composerRef={composerRef} />
              {isNarrow && (
                <InspirationPanel
                  destinations={allDestinations}
                  onPlan={() => composerRef.current?.focus()}
                  onExplore={handleExploreDestinations}
                  onSelectDestination={handlePreview}
                />
              )}
            </>
          )}
        </div>

        <div className={styles.composerDock}>
          <p className={styles.dockHint}>Demo · Mock data</p>
          <Composer
            inputRef={composerRef}
            draft={draft}
            onDraftChange={setDraft}
            onSubmit={handleComposerSubmit}
            loading={loading}
            placeholder="Ask for a mood, budget, or departure airport…"
          />
        </div>
      </div>

      <div className={styles.right}>
        {showInspiration && !isNarrow && (
          <InspirationPanel
            destinations={allDestinations}
            onPlan={() => composerRef.current?.focus()}
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
        origins={origins}
        maxBudgetCap={maxBudgetCap}
        onChange={handleFilterChange}
        onReset={handleResetFilters}
        onClose={() => setFiltersOpen(false)}
      />

      <TripDetailsDrawer destination={drawerTrip} weights={weights} onClose={handleCloseDrawer} />
    </div>
  )
}
