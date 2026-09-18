import { percent } from '../utils/format'

/**
 * Shows planner-provided component scores. Missing scores are omitted.
 */
export default function ScoreBreakdown({ items, total }) {
  return (
    <div className="score-breakdown">
      {items.map((item) => (
        <div key={item.key} className="score-line">
          <span>{item.label}</span>
          <strong>{percent(item.score)}</strong>
        </div>
      ))}
      {total != null && (
        <div className="score-line total">
          <span>Total score</span>
          <strong>{percent(total)}</strong>
        </div>
      )}
    </div>
  )
}
