import styles from '../workspace.module.css'

function openDatePicker(event) {
  const input = event.currentTarget.querySelector('input[type="date"]')
  if (!input || input.disabled) return
  try {
    input.showPicker?.()
  } catch {
    input.focus()
  }
}

export default function TripDateFields({
  departureDate = '',
  returnDate = '',
  onChange,
  error = '',
  disabled = false,
}) {
  const departureInvalid = Boolean(error) && departureDate && returnDate
  const returnInvalid = Boolean(error) && departureDate && returnDate

  return (
    <>
      <div className={styles.dateField}>
        <label htmlFor="departure-date">Departure date</label>
        <div className={styles.dateFieldControl} onClick={openDatePicker}>
          <input
            id="departure-date"
            type="date"
            value={departureDate}
            disabled={disabled}
            max={returnDate || undefined}
            aria-invalid={departureInvalid}
            aria-describedby={error ? 'trip-date-error trip-date-hint' : 'trip-date-hint'}
            onChange={(event) => onChange?.('departureDate', event.target.value)}
          />
        </div>
      </div>
      <div className={styles.dateField}>
        <label htmlFor="return-date">Return date</label>
        <div className={styles.dateFieldControl} onClick={openDatePicker}>
          <input
            id="return-date"
            type="date"
            value={returnDate}
            disabled={disabled}
            min={departureDate || undefined}
            aria-invalid={returnInvalid}
            aria-describedby={error ? 'trip-date-error trip-date-hint' : 'trip-date-hint'}
            onChange={(event) => onChange?.('returnDate', event.target.value)}
          />
        </div>
      </div>
    </>
  )
}
