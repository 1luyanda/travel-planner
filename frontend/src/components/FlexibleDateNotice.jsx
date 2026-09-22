export default function FlexibleDateNotice({ destination, className }) {
  if (!destination?.isFlexibleDateOption) return null
  const range = (departure, returning) =>
    `${departure || 'Not available'} to ${returning || 'Not available'}`

  return (
    <p className={className}>
      <strong>Alternative dates.</strong>{' '}
      Actual: {range(destination.actualDepartureDate, destination.actualReturnDate)}.
      {' '}Requested: {range(destination.requestedDepartureDate, destination.requestedReturnDate)}.
    </p>
  )
}
