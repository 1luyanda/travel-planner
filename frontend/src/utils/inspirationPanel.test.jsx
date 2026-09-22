import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import InspirationPanel from '../components/InspirationPanel'
import { INSPIRATION_GENERIC_HEADING } from './inspiration'

describe('InspirationPanel', () => {
  it('keeps Get started and shows generic travel inspiration without prices', () => {
    const html = renderToStaticMarkup(<InspirationPanel />)
    expect(html).toContain('Get started')
    expect(html).toContain('Plan a getaway')
    expect(html).toContain('Explore destinations')
    expect(html).toContain(INSPIRATION_GENERIC_HEADING)
    expect(html).toContain('Athens')
    expect(html).toContain('Lisbon')
    expect(html).toContain('Malta')
    expect(html).toContain('Rome')
    expect(html).not.toMatch(/For you/i)
    expect(html).not.toMatch(/\d+ EUR/)
    expect(html).not.toMatch(/live fare|bookable|confirmed match/i)
    expect(html.match(/type="button"/g)?.length).toBeGreaterThanOrEqual(6)
  })

  it('uses the selected origin heading and a loading state before flights arrive', () => {
    const html = renderToStaticMarkup(
      <InspirationPanel origin={{ originId: 'zagreb-hr', city: 'Zagreb' }} />,
    )
    expect(html).toContain('Explore from Zagreb')
    expect(html).toContain('Loading destinations…')
    expect(html).toContain('Get started')
    expect(html).not.toContain(INSPIRATION_GENERIC_HEADING)
    expect(html).not.toMatch(/For you/i)
  })
})
