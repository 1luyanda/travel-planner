import { percent, refinementPresets } from '../utils/ranking'

// Labels must match keys in refinementPresets so clicks only change local weights.
const actions = ['Cheaper', 'Warmer', 'Direct flights', 'Shorter travel']

function isActive(action, weights) {
  const preset = refinementPresets[action]
  if (!preset || !weights) return false
  return Object.keys(preset).every((key) => preset[key] === weights[key])
}

/**
 * Right sidebar. Buttons rerank the in-memory shortlist; they do not call FastAPI.
 * @param {(preference: string) => void} onRefine
 * @param {boolean} loading Disables buttons while a search is in progress or the list is empty.
 * @param {object | null} weights Visible current weight summary.
 */
export default function RefinementControls({ onRefine, loading, weights }) {
  return (
    <section className="side-panel refine-panel" aria-labelledby="refine-title">
      <h2 id="refine-title">Refine your shortlist</h2>
      <p className="panel-copy">
        These buttons only update local ranking weights. They do not call a backend or reload mock data.
      </p>

      <div className="action-stack">
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            className={isActive(action, weights) ? 'refine-button active' : 'refine-button'}
            aria-pressed={isActive(action, weights)}
            onClick={() => onRefine(action)}
            disabled={loading}
          >
            {action}
          </button>
        ))}
      </div>

      {weights && (
        <div className="weight-list" aria-live="polite">
          <h3>Current weights</h3>
          <ul>
            <li>Price {percent(weights.price)}</li>
            <li>Weather {percent(weights.weather)}</li>
            <li>Stops {percent(weights.stops)}</li>
            <li>Duration {percent(weights.duration)}</li>
          </ul>
        </div>
      )}
    </section>
  )
}
