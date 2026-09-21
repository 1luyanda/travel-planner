import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import TripDateFields from '../components/TripDateFields'

describe('TripDateFields', () => {
  it('renders labelled native date inputs', () => {
    const html = renderToStaticMarkup(
      <TripDateFields departureDate="2026-10-08" returnDate="2026-10-16" onChange={() => {}} />,
    )
    expect(html).toContain('Departure date')
    expect(html).toContain('Return date')
    expect(html).toContain('type="date"')
    expect(html).toContain('id="departure-date"')
    expect(html).toContain('id="return-date"')
    expect(html).toContain('value="2026-10-08"')
    expect(html).toContain('value="2026-10-16"')
    expect(html).toContain('for="departure-date"')
    expect(html).toContain('for="return-date"')
  })
})
