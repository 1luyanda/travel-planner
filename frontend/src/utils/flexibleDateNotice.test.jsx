import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DestinationCard from '../components/DestinationCard'
import TripDetailsContent from '../components/TripDetailsContent'
import ConversationPane from '../components/ConversationPane'

const alternative = {
  id: 'alternative', rank: 1, isFlexibleDateOption: true,
  requestedDepartureDate: '2026-09-21', requestedReturnDate: '2026-09-25',
  actualDepartureDate: '2026-09-22', actualReturnDate: '2026-09-26',
}

describe('flexible-date rendering', () => {
  it.each(['card', 'details'])('labels alternative dates in %s', (surface) => {
    const render = (destination) => renderToStaticMarkup(surface === 'card'
      ? <DestinationCard destination={destination} rank={1} />
      : <TripDetailsContent destination={destination} titleId="details" />)
    const html = render(alternative)
    expect(html).toContain('Alternative dates.')
    expect(html).toContain('Actual: 2026-09-22 to 2026-09-26')
    expect(html).toContain('Requested: 2026-09-21 to 2026-09-25')
    expect(render({ ...alternative, isFlexibleDateOption: false })).not.toContain('Alternative dates.')
    expect(render({ id: 'legacy' })).not.toContain('Alternative dates.')
  })

  it('shows backend fallback counts and preserves alternative-first order', () => {
    const html = renderToStaticMarkup(<ConversationPane messages={[]} results={[
      { ...alternative, destination: { city: 'Alternative city' } },
      { id: 'exact', destination: { city: 'Exact city' }, rank: 2 },
    ]} dateFallback={{ used: true, exactMatchCount: 1, fallbackCount: 1 }}
      previousRanks={{}} savedIds={[]} />)
    expect(html).toContain('Exact-date matches: 1.')
    expect(html).toContain('Alternative-date options: 1.')
    expect(html.indexOf('Alternative city')).toBeLessThan(html.indexOf('Exact city'))
  })
})
