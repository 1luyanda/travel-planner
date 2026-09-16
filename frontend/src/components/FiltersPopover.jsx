import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import styles from '../workspace.module.css'

export default function FiltersPopover({
  open,
  form,
  maxBudgetCap,
  onChange,
  onReset,
  onClose,
}) {
  const titleId = useId()
  const closeRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    closeRef.current?.focus()
    function onKeyDown(event) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  const sliderMax = Math.max(maxBudgetCap, Number(form.maxBudget) || 0, 1)

  return (
    <div className={styles.popoverRoot}>
      <button type="button" className={styles.popoverScrim} aria-label="Close filters" onClick={onClose} />
      <section className={styles.popover} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <header>
          <h2 id={titleId}>Filters</h2>
          <button ref={closeRef} type="button" className={styles.iconBtn} onClick={onClose} aria-label="Close filters">
            <X size={18} />
          </button>
        </header>
        <p className={styles.panelHint}>
          Budget and direct-flight changes request an updated stored shortlist. Weather preference
          only re-ranks the trips already loaded. Origin is set in Flying from.
        </p>

        <label htmlFor="filter-budget">
          Maximum budget
          <div className={styles.sliderRow}>
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
          <label className={styles.check}>
            <input
              type="radio"
              name="temperature"
              checked={!form.preferWarm}
              onChange={() => onChange('preferWarm', false)}
            />
            Any weather
          </label>
          <label className={styles.check}>
            <input
              type="radio"
              name="temperature"
              checked={form.preferWarm}
              onChange={() => onChange('preferWarm', true)}
            />
            Prefer warmer
          </label>
        </fieldset>

        <label className={styles.check}>
          <input
            type="checkbox"
            checked={form.directOnly}
            onChange={(event) => onChange('directOnly', event.target.checked)}
          />
          Direct flights only
        </label>

        <button type="button" className={styles.secondaryBtn} onClick={onReset}>
          Reset filters
        </button>
      </section>
    </div>
  )
}
