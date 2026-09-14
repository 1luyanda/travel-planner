import { percent } from '../utils/ranking'

/**
 * “Searching with” card: origin, budget, stops, temperature, optional mood note, and weights.
 * @param {object | null} filters Last applied filter snapshot.
 * @param {object | null} weights Current ranking weights shown as percentages.
 */
export default function SearchSummary({ filters, weights }) {
  if (!filters) return null

  return (
    <section className="search-summary" aria-labelledby="searching-with">
      <p className="eyebrow">Current request</p>
      <h2 id="searching-with">Searching with</h2>
      <dl>
        <div>
          <dt>Origin</dt>
          <dd>{filters.origin || 'All origins'}</dd>
        </div>
        <div>
          <dt>Budget</dt>
          <dd>up to €{filters.maxBudget}</dd>
        </div>
        <div>
          <dt>Stops</dt>
          <dd>{filters.directOnly ? 'Direct flights only' : 'Any number of stops'}</dd>
        </div>
        <div>
          <dt>Temperature</dt>
          <dd>{filters.preferWarm ? 'Prefer warmer weather' : 'Any weather'}</dd>
        </div>
        {filters.mood?.trim() && (
          <div className="summary-mood">
            <dt>Preference note</dt>
            <dd>{filters.mood.trim()}</dd>
          </div>
        )}
      </dl>
      {weights && (
        <p className="weights-line" aria-live="polite">
          Ranking weights: Price {percent(weights.price)} · Weather {percent(weights.weather)} · Stops{' '}
          {percent(weights.stops)} · Duration {percent(weights.duration)}
        </p>
      )}
    </section>
  )
}
