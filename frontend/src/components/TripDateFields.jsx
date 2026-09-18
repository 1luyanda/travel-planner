import styles from '../workspace.module.css'

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
      <div className={styles.dateField}>
        <label htmlFor="return-date">Return date</label>
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
    </>
  )
}
