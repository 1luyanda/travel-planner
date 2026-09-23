import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import InspirationPanel from '../components/InspirationPanel'

describe('InspirationPanel', () => {
  it('keeps Get started and opens Explore activities instead of destination cards', () => {
    const onPlan = vi.fn()
    const onExplore = vi.fn()
    const html = renderToStaticMarkup(
      <InspirationPanel onPlan={onPlan} onExplore={onExplore} />,
    )

    expect(html).toContain('Get started')
    expect(html).toContain('Plan a getaway')
    expect(html).toContain('Explore activities')
    expect(html).not.toContain('Explore destinations')
    expect(html).not.toContain('Travel inspiration')
    expect(html).not.toContain('Explore from Zagreb')
    expect(html).not.toContain('Athens')
    expect(html).not.toContain('Lisbon')
    expect(html).not.toContain('Malta')
    expect(html).not.toContain('Rome')
    expect(html).not.toContain('Loading destinations')
    expect(html.match(/type="button"/g)).toHaveLength(2)
  })
})
