import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import TripDetailsPanel from '../components/TripDetailsPanel'
import { DETAILS_EMPTY_MESSAGE } from '../components/TripDetailsContent'

const rome = {
  id: 'ZAG-ROM-2026-09-18',
  originCity: 'Zagreb',
  originCountry: 'Croatia',
  originIata: 'ZAG',
  scores: { price: 1, weather: 0.4, stops: 1, duration: 0.8, total: 0.82 },
  explanation: {
    summary: 'Rome stays within budget.',
    evidence: [{ id: 'e1', statement: 'Rome stays within budget.' }],
  },
  flight: {
    price: 65,
    currency: 'EUR',
    outbound_stops: 0,
    duration_minutes: 170,
    airline_code: 'OU',
    departure_at: '2026-09-16T05:50:00+02:00',
    return_at: '2026-09-23T08:45:00+03:00',
  },
  destination: { city: 'Rome' },
  country: { common_name: 'Italy' },
  weather: { average_max_temperature_c: 27.8 },
}

describe('TripDetailsPanel', () => {
  it('shows an empty state when no trip is selected', () => {
    const html = renderToStaticMarkup(<TripDetailsPanel destination={null} onClose={() => {}} />)
    expect(html).toContain(DETAILS_EMPTY_MESSAGE)
    expect(html).not.toContain('role="dialog"')
    expect(html).not.toContain('drawer-overlay')
  })

  it('renders selected trip details without a modal overlay and drops duplicate summary bullets', () => {
    const html = renderToStaticMarkup(
      <TripDetailsPanel destination={rome} onClose={() => {}} isSaved={false} onToggleSaved={() => {}} />,
    )
    expect(html).not.toMatch(/snapshot|not live or bookable/i)
    expect(html).toContain('Rome stays within budget.')
    expect(html).toContain('65 EUR')
    expect(html).toContain('Close')
    expect(html).not.toContain('role="dialog"')
    expect(html).not.toContain('aria-modal="true"')
    expect(html).not.toContain('aria-label="Close trip details"')
    expect((html.match(/Rome stays within budget\./g) || []).length).toBe(1)
  })
})
