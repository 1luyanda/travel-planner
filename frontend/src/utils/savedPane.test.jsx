import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SavedPane from '../components/SavedPane'
import ConversationPane from '../components/ConversationPane'
import Composer from '../components/Composer'

const rome = {
  id: 'ZAG-ROM-2026-09-18',
  availability: 'available',
  priceChanged: true,
  savedAt: '2026-09-18T12:40:00Z',
  flight: { price: 70, currency: 'EUR' },
  destination: { city: 'Rome' },
  country: { common_name: 'Italy' },
  explanation: { summary: null, evidence: [] },
}

describe('SavedPane', () => {
  it('renders server-backed saved flights independently of recommendation results', () => {
    const html = renderToStaticMarkup(
      <SavedPane
        destinations={[rome]}
        selectedId={null}
        savedIds={[rome.id]}
        onExplore={() => {}}
      />,
    )
    expect(html).toContain('Rome')
    expect(html).toContain('Price changed')
    expect(html).toContain('Saved')
    expect(html).not.toContain('matching trip')
    expect(html).not.toContain('Ask for a mood')
  })

  it('shows loading, error, empty, and unavailable states', () => {
    const loading = renderToStaticMarkup(
      <SavedPane destinations={[]} loading selectedId={null} savedIds={[]} onExplore={() => {}} />,
    )
    expect(loading).toContain('Loading saved flights')

    const failed = renderToStaticMarkup(
      <SavedPane
        destinations={[]}
        error="Could not load saved flights."
        selectedId={null}
        savedIds={[]}
        onExplore={() => {}}
      />,
    )
    expect(failed).toContain('Could not load saved flights.')

    const empty = renderToStaticMarkup(
      <SavedPane destinations={[]} selectedId={null} savedIds={[]} onExplore={() => {}} />,
    )
    expect(empty).toContain('No saved flights yet.')

    const missing = renderToStaticMarkup(
      <SavedPane
        destinations={[
          {
            ...rome,
            id: 'missing',
            availability: 'unavailable',
            priceChanged: false,
            destination: { city: 'Lisbon' },
          },
        ]}
        selectedId={null}
        savedIds={['missing']}
        onExplore={() => {}}
      />,
    )
    expect(missing).toContain('Flight no longer available')
  })

  it('does not render ConversationPane or Composer', () => {
    const saved = renderToStaticMarkup(
      <SavedPane destinations={[rome]} selectedId={null} savedIds={[rome.id]} onExplore={() => {}} />,
    )
    const conversation = renderToStaticMarkup(
      <ConversationPane
        messages={[{ id: '1', role: 'user', text: 'Warm trip from ZAG' }]}
        results={[]}
        previousRanks={{}}
        savedIds={[]}
      />,
    )
    const composer = renderToStaticMarkup(
      <Composer draft="" onDraftChange={() => {}} onSubmit={() => {}} placeholder="Ask for a mood, dates, or budget…" />,
    )
    expect(saved).not.toContain('Warm trip from ZAG')
    expect(saved).not.toContain('Ask for a mood, dates, or budget')
    expect(conversation).toContain('Warm trip from ZAG')
    expect(composer).toContain('Ask for a mood, dates, or budget')
  })
})
