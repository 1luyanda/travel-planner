import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DestinationCard from '../components/DestinationCard'
import { explanationView } from './plannerFlow'

const destination = {
  id: 'ZAG-ROM-2026-09-18',
  rank: 1,
  scores: { price: 1, weather: 0.4, stops: 1, duration: 0.8, total: 0.82 },
  explanation: {
    summary: 'Rome stays within budget and is a short hop from Zagreb.',
    evidence: [{ id: 'e1', statement: 'Fare is EUR 65 against a EUR 400 budget.' }],
  },
  flight: { price: 65, currency: 'EUR', outbound_stops: 0, duration_minutes: 170 },
  destination: { city: 'Rome', country_code: 'IT' },
  country: { common_name: 'Italy' },
  weather: { average_max_temperature_c: 27.8 },
}

describe('DestinationCard explanations', () => {
  it('renders backend summary and evidence instead of browser ranking copy', () => {
    const html = renderToStaticMarkup(
      <DestinationCard destination={destination} rank={1} previousRank={null} />,
    )
    expect(html).toContain('Rome stays within budget and is a short hop from Zagreb.')
    expect(html).toContain('Fare is EUR 65 against a EUR 400 budget.')
    expect(html).not.toMatch(/Weighted score favours/i)
    expect(html).not.toMatch(/ranked in the browser/i)
    expect(explanationView(destination).summary).toBe(destination.explanation.summary)
  })
})
