import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import TripDetailsDrawer from '../components/TripDetailsDrawer'
import { SNAPSHOT_NOTICE } from '../components/TripDetailsContent'
import { NOT_AVAILABLE } from '../utils/format'

const rome = {
  id: 'ZAG-ROM-2026-09-18',
  originCity: 'Zagreb',
  originCountry: 'Croatia',
  originIata: 'ZAG',
  scores: { price: 1, weather: 0.4, stops: 1, duration: 0.8, total: 0.82 },
  explanation: {
    summary: 'Rome stays within budget.',
    evidence: [{ id: 'e1', statement: 'Fare is EUR 65 against a EUR 400 budget.' }],
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

describe('TripDetailsDrawer', () => {
  it('renders photo, explanation, and known trip fields', () => {
    const html = renderToStaticMarkup(
      <TripDetailsDrawer destination={rome} onClose={() => {}} isSaved={false} onToggleSaved={() => {}} />,
    )
    expect(html).toContain('role="dialog"')
    expect(html).toContain(SNAPSHOT_NOTICE)
    expect(html).toContain('Rome stays within budget.')
    expect(html).toContain('Zagreb, Croatia (ZAG)')
    expect(html).toContain('65 EUR')
    expect(html).toContain('Direct')
    expect(html).toContain('OU')
    expect(html).toContain('27.8°C')
    expect(html).toContain('Close')
    expect(html).toContain('aria-label="Close trip details"')
    expect(html).toContain('Save')
  })

  it('labels missing fields Not available and does not invent them', () => {
    const html = renderToStaticMarkup(
      <TripDetailsDrawer
        destination={{
          id: 'x',
          destination: { city: 'Namangan' },
          country: {},
          flight: {},
          weather: {},
          scores: {},
        }}
        onClose={() => {}}
      />,
    )
    expect(html).toContain(NOT_AVAILABLE)
    expect(html).toContain('Namangan')
    expect(html).not.toMatch(/Ryanair|invented/i)
    expect((html.match(/Not available/g) || []).length).toBeGreaterThan(3)
  })
})
