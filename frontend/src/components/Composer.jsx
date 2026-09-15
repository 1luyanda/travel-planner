import { ArrowUp } from 'lucide-react'
import styles from '../workspace.module.css'

export default function Composer({ draft, onDraftChange, onSubmit, loading, placeholder, inputRef }) {
  return (
    <form className={styles.composer} onSubmit={onSubmit}>
      <label htmlFor="trip-composer" className={styles.srOnly}>
        Trip request
      </label>
      <textarea
        ref={inputRef}
        id="trip-composer"
        rows={1}
        value={draft}
        placeholder={placeholder}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            event.currentTarget.form?.requestSubmit()
          }
        }}
      />
      <button type="submit" className={styles.send} disabled={loading || !draft.trim()} aria-label="Send trip request">
        <ArrowUp size={18} strokeWidth={2.2} />
      </button>
    </form>
  )
}
