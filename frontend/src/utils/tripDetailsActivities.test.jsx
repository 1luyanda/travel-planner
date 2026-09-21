import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { TripDetailsActivitiesView } from '../components/TripDetailsActivities'

const colosseum = {
  place_id: 'ChIJA',
  name: 'Colosseum',
  address: 'Rome, Italy',
  rating: 4.6,
  user_ratings_total: 1200,
  business_status: 'OPERATIONAL',
  price_level: 'PRICE_LEVEL_MODERATE',
}

describe('TripDetailsActivitiesView', () => {
  it('renders compact cards and keeps missing optional fields off the card', () => {
    const html = renderToStaticMarkup(
      <TripDetailsActivitiesView
        titleId="details"
        state={{ status: 'ready', activities: [colosseum, { place_id: 'park', name: 'Villa Borghese' }] }}
      />,
    )
    expect(html).toContain('Activities')
    expect(html).toContain('Colosseum')
    expect(html).toContain('Rome, Italy')
    expect(html).toContain('4.6 · 1200 reviews')
    expect(html).toContain('Operational')
    expect(html).not.toContain('>Open<')
    expect(html).not.toContain('open now')
    expect(html).toContain('Price level: Moderate')
    expect(html).toContain('Villa Borghese')
    expect(html).not.toContain('€')
    expect(html).not.toContain('GOOGLE_PLACES_API_KEY')
    expect((html.match(/trip-details-activity-card/g) || []).length).toBe(2)
  })

  it('shows loading, empty, error with retry, and unavailable states', () => {
    expect(
      renderToStaticMarkup(
        <TripDetailsActivitiesView titleId="details" state={{ status: 'loading', activities: [] }} />,
      ),
    ).toContain('Loading activities…')

    expect(
      renderToStaticMarkup(
        <TripDetailsActivitiesView titleId="details" state={{ status: 'ready', activities: [] }} />,
      ),
    ).toContain('No activities found for this destination.')

    const errorHtml = renderToStaticMarkup(
      <TripDetailsActivitiesView
        titleId="details"
        state={{ status: 'error', activities: [colosseum], error: 'Activity data is temporarily unavailable.' }}
        onRetry={() => {}}
      />,
    )
    expect(errorHtml).toContain('Activity data is temporarily unavailable.')
    expect(errorHtml).toContain('Retry')
    expect(errorHtml).not.toContain('Colosseum')

    expect(
      renderToStaticMarkup(
        <TripDetailsActivitiesView titleId="details" state={{ status: 'unavailable', activities: [] }} />,
      ),
    ).toContain('Activities are unavailable because this trip has no city.')

    expect(renderToStaticMarkup(<TripDetailsActivitiesView titleId="details" state={{ status: 'idle' }} />)).toBe('')
  })

  it('keeps a numeric zero rating visible', () => {
    const html = renderToStaticMarkup(
      <TripDetailsActivitiesView
        titleId="details"
        state={{
          status: 'ready',
          activities: [{ place_id: 'zero', name: 'Quiet Square', rating: 0, user_ratings_total: 0 }],
        }}
      />,
    )
    expect(html).toContain('Quiet Square')
    expect(html).toContain('0 · 0 reviews')
  })
})
