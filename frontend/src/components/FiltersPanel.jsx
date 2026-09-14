/**
 * Results-page sidebar. Changing a control refilters the already loaded destinations.
 * @param {object} form Live filter values (budget, warm preference, direct only).
 * @param {(field: string, value: unknown) => void} onChange
 * @param {() => void} onReset Restore the last submitted search snapshot.
 * @param {() => void} onNewSearch Return to the search screen.
 */
export default function FiltersPanel({ form, onChange, onReset, onNewSearch }) {
  const sliderMax = Math.max(500, Number(form.maxBudget) || 500)

  return (
    <section className="side-panel filters-panel" aria-labelledby="filters-title">
      <h2 id="filters-title">Filters</h2>
      <p className="panel-copy">These update the shortlist already loaded from mock data.</p>

      <label htmlFor="filter-budget">
        Maximum budget
        <div className="slider-row">
          <input
            id="filter-budget"
            type="range"
            min="1"
            max={sliderMax}
            step="1"
            value={form.maxBudget}
            onChange={(event) => onChange('maxBudget', Number(event.target.value))}
          />
          <span>€{form.maxBudget}</span>
        </div>
      </label>

      <fieldset>
        <legend>Temperature preference</legend>
        <label className="check">
          <input
            type="radio"
            name="temperature"
            checked={!form.preferWarm}
            onChange={() => onChange('preferWarm', false)}
          />
          Any weather
        </label>
        <label className="check">
          <input
            type="radio"
            name="temperature"
            checked={form.preferWarm}
            onChange={() => onChange('preferWarm', true)}
          />
          Prefer warmer
        </label>
      </fieldset>

      <label className="switch">
        <input
          type="checkbox"
          checked={form.directOnly}
          onChange={(event) => onChange('directOnly', event.target.checked)}
        />
        <span>Direct flights only</span>
      </label>

      <div className="panel-actions">
        <button type="button" className="secondary" onClick={onReset}>
          Reset filters
        </button>
        <button type="button" className="text-button" onClick={onNewSearch}>
          New search
        </button>
      </div>
    </section>
  )
}
