import { useState } from 'react'
import styles from '../landing.module.css'

export default function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  minLength,
  maxLength,
  required = true,
  describedBy,
  toggleLabel = 'password',
}) {
  const [visible, setVisible] = useState(false)

  return (
    <div className={styles.authField}>
      <label htmlFor={id}>{label}</label>
      <div className={styles.passwordWrap}>
        <input
          id={id}
          required={required}
          minLength={minLength}
          maxLength={maxLength}
          type={visible ? 'text' : 'password'}
          value={value}
          autoComplete={autoComplete}
          aria-invalid={Boolean(describedBy)}
          aria-describedby={describedBy}
          onChange={onChange}
        />
        <button
          type="button"
          className={styles.passwordToggle}
          aria-label={visible ? `Hide ${toggleLabel}` : `Show ${toggleLabel}`}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? 'Hide' : 'Show'}
        </button>
      </div>
    </div>
  )
}
