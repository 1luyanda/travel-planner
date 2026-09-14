/** Chip labels that fill the mood note. Warm/cool chips also set preferWarm. */
const suggestions = [
  { label: 'Warm and relaxing', mood: 'Warm and relaxing', preferWarm: true },
  { label: 'Budget escape', mood: 'Budget escape' },
  { label: 'Cool weather', mood: 'Cool weather', preferWarm: false },
  { label: 'Short flight', mood: 'Short flight' },
]

/**
 * Centred search form.
 * @param {object} form Current search fields, including UI-only `mood`.
 * @param {string[]} origins Origin IATA codes from the loaded mock payload.
 * @param {(field: string, value: unknown) => void} onChange
 * @param {(event: SubmitEvent) => void} onSubmit Starts the FastAPI-backed search.
 * @param {boolean} loading Disables the submit button while destinations are fetched.
 */
export default function SearchPanel({ form, origins, onChange, onSubmit, loading }) {
  function applySuggestion(suggestion) {
    onChange('mood', suggestion.mood)
    if ('preferWarm' in suggestion) {
      onChange('preferWarm', suggestion.preferWarm)
    }
  }

  return (
    <form className="search-panel" onSubmit={onSubmit}>
      <p className="eyebrow">Plan a getaway</p>
      <h1>What would feel right?</h1>
      <p className="search-copy">
        Add a preference note if you like. It is only a UI hint for now and does not run AI parsing.
      </p>

      <label htmlFor="mood">Trip preference</label>
      <textarea
        id="mood"
        rows="3"
        value={form.mood}
        onChange={(event) => onChange('mood', event.target.value)}
        placeholder="Warm, relaxing, close, inexpensive..."
      />

      <div className="chip-row" role="group" aria-label="Preference suggestions">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion.label}
            type="button"
            className="chip"
            aria-pressed={form.mood === suggestion.mood}
            onClick={() => applySuggestion(suggestion)}
          >
            {suggestion.label}
          </button>
        ))}
      </div>

      <div className="form-grid">
        <label htmlFor="origin">
          Origin airport
          <select
            id="origin"
            value={form.origin}
            onChange={(event) => onChange('origin', event.target.value)}
          >
            <option value="">All origins</option>
            {origins.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>

        <label htmlFor="budget">
          Maximum budget (EUR)
          <input
            id="budget"
            required
            min="1"
            type="number"
            value={form.maxBudget}
            onChange={(event) => onChange('maxBudget', Number(event.target.value))}
          />
        </label>
      </div>

      <div className="check-row">
        <label className="check">
          <input
            type="checkbox"
            checked={form.directOnly}
            onChange={(event) => onChange('directOnly', event.target.checked)}
          />
          Direct flights only
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={form.preferWarm}
            onChange={(event) => onChange('preferWarm', event.target.checked)}
          />
          Prefer warmer weather
        </label>
      </div>

      <button className="primary" disabled={loading}>
        {loading ? 'Finding trips...' : 'Find my getaway'}
      </button>
    </form>
  )
}
