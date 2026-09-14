import { useEffect, useRef, useState } from 'react'
import SearchPanel from './components/SearchPanel'
import SearchSummary from './components/SearchSummary'
import FiltersPanel from './components/FiltersPanel'
import ResultsList from './components/ResultsList'
import RefinementControls from './components/RefinementControls'
import TripDetailsDrawer from './components/TripDetailsDrawer'
import { fetchDestinations } from './services/destinationApi'
import {
  defaultWeights,
  filterDestinations,
  rankDestinations,
  refinementPresets,
  uniqueOrigins,
} from './utils/ranking'

const initialForm = {
  origin: '',
  maxBudget: 400,
  directOnly: false,
  preferWarm: false,
  mood: '',
}

function CompassMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="13" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="16" cy="16" r="2" fill="currentColor" />
      <path d="M16 5.5 18.2 16 16 26.5 13.8 16Z" fill="#2a9d8f" />
      <path d="M5.5 16 16 13.8 26.5 16 16 18.2Z" fill="#1b3354" opacity="0.85" />
    </svg>
  )
}

/**
 * Root workflow: fetch destinations once from FastAPI, then filter and rank in the browser.
 * Search shows the form; a successful submit switches to the results layout.
 */
export default function App() {
  const [form, setForm] = useState(initialForm)
  const [searchSnapshot, setSearchSnapshot] = useState(initialForm) // last submitted search, used by Reset
  const [allDestinations, setAllDestinations] = useState([]) // full payload from GET /api/destinations
  const [results, setResults] = useState([]) // currently filtered and ranked shortlist
  const [weights, setWeights] = useState(null)
  const [previousRanks, setPreviousRanks] = useState({}) // used to show movement after refinement
  const [appliedFilters, setAppliedFilters] = useState(null)
  const [selectedTrip, setSelectedTrip] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasSearched, setHasSearched] = useState(false)
  const lastFocusRef = useRef(null)

  const origins = uniqueOrigins(allDestinations)
  const drawerTrip = selectedTrip
    ? results.find((item) => item.id === selectedTrip.id) || selectedTrip
    : null

  // Prefetch so the origin dropdown is populated before the first search.
  useEffect(() => {
    fetchDestinations()
      .then(setAllDestinations)
      .catch(() => {})
  }, [])

  function changeForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function applyFilters(filters, nextWeights, destinations = allDestinations) {
    const ranked = rankDestinations(filterDestinations(destinations, filters), nextWeights)
    setAppliedFilters(filters)
    setWeights(nextWeights)
    setResults(ranked)
  }

  async function handleSearch(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setSelectedTrip(null)
    setPreviousRanks({})

    try {
      const destinations = allDestinations.length ? allDestinations : await fetchDestinations()
      if (!allDestinations.length) setAllDestinations(destinations)
      const nextWeights = defaultWeights(form.preferWarm)
      applyFilters(form, nextWeights, destinations)
      setSearchSnapshot(form)
      setHasSearched(true)
    } catch (err) {
      setResults([])
      setWeights(null)
      setAppliedFilters(null)
      setHasSearched(false)
      setError(err.message || 'Something went wrong while loading destinations.')
    } finally {
      setLoading(false)
    }
  }

  function handleFilterChange(field, value) {
    const next = { ...form, [field]: value }
    setForm(next)
    if (!hasSearched) return
    const nextWeights = field === 'preferWarm' ? defaultWeights(value) : weights || defaultWeights(next.preferWarm)
    applyFilters(next, nextWeights)
    setPreviousRanks({})
  }

  function handleReset() {
    const restored = searchSnapshot || initialForm
    setForm(restored)
    if (!hasSearched) return
    applyFilters(restored, defaultWeights(restored.preferWarm))
    setPreviousRanks({})
  }

  function handleNewSearch() {
    setHasSearched(false)
    setSelectedTrip(null)
    setError('')
    setPreviousRanks({})
  }

  function handleViewDetails(destination, event) {
    lastFocusRef.current = event?.currentTarget ?? document.activeElement
    setSelectedTrip(destination)
  }

  function handleCloseDrawer() {
    setSelectedTrip(null)
    requestAnimationFrame(() => lastFocusRef.current?.focus?.())
  }

  // Change ranking weights only. Do not refetch; the shortlist is already in memory.
  function handleRefine(preference) {
    const nextWeights = refinementPresets[preference]
    if (!nextWeights || !results.length) return
    const oldRanks = Object.fromEntries(results.map((item, index) => [item.id, index + 1]))
    setPreviousRanks(oldRanks)
    setWeights(nextWeights)
    setResults(rankDestinations(results, nextWeights))
  }

  return (
    <div className={hasSearched ? 'app results-mode' : 'app'}>
      <header>
        <a className="brand" href="#top" onClick={(event) => {
          if (hasSearched) {
            event.preventDefault()
            handleNewSearch()
          }
        }}>
          <CompassMark />
          Travel<span>Planner</span>
        </a>
        {hasSearched && (
          <button type="button" className="text-button" onClick={handleNewSearch}>
            New search
          </button>
        )}
      </header>

      {!hasSearched && (
        <section className="search-screen" id="top">
          <SearchPanel
            form={form}
            origins={origins}
            onChange={changeForm}
            onSubmit={handleSearch}
            loading={loading}
          />
          {error && <p className="notice error">{error}</p>}
        </section>
      )}

      {hasSearched && (
        <section className="results-screen" id="top">
          {loading && <p className="notice">Loading destinations…</p>}
          {error && <p className="notice error">{error}</p>}
          <SearchSummary filters={appliedFilters} weights={weights} />
          <div className="results-grid">
            <FiltersPanel
              form={form}
              onChange={handleFilterChange}
              onReset={handleReset}
              onNewSearch={handleNewSearch}
            />
            <ResultsList
              results={results}
              previousRanks={previousRanks}
              weights={weights}
              onViewDetails={handleViewDetails}
            />
            <RefinementControls onRefine={handleRefine} loading={loading || results.length === 0} weights={weights} />
          </div>
        </section>
      )}

      <TripDetailsDrawer
        destination={drawerTrip}
        weights={weights}
        onClose={handleCloseDrawer}
      />
    </div>
  )
}
