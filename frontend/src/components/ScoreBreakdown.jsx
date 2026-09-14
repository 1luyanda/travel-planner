import { percent } from '../utils/ranking'

/**
 * Shows score × weight = contribution for each ranking factor.
 * @param {Array<{key: string, label: string, score: number, weight: number, contribution: number}>} items
 * @param {number} total Combined weighted score.
 */
export default function ScoreBreakdown({ items, total }) {
  return (
    <div className="score-breakdown">
      {items.map((item) => (
        <div key={item.key} className="score-line">
          <span>{item.label}</span>
          <strong>
            {percent(item.score)} × {percent(item.weight)} = {percent(item.contribution)}
          </strong>
        </div>
      ))}
      <div className="score-line total">
        <span>Total weighted score</span>
        <strong>{percent(total)}</strong>
      </div>
    </div>
  )
}
