// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Sidebar from '../components/Sidebar'
import { ROUTES, RouteProvider } from './routes.jsx'

const user = { display_name: 'Luyanda' }

function renderSidebar(props) {
  return renderToStaticMarkup(
    <RouteProvider>
    <Sidebar
      view="explore"
      path={ROUTES.planner}
      history={[]}
      savedCount={0}
      user={user}
      onLogout={() => {}}
      onClose={() => {}}
      onNewTrip={() => {}}
      onPlanTrip={() => {}}
      onExplore={() => {}}
      onSaved={() => {}}
      onHistory={() => {}}
      {...props}
    />
    </RouteProvider>,
  )
}

describe('workspace navigation', () => {
  it('keeps planning on /planner and points Explore at /explore', () => {
    const html = renderSidebar()
    expect(html).toContain('href="/planner"')
    expect(html).toContain('Plan a trip')
    expect(html).toContain('href="/explore"')
    expect(html).toContain('>Explore<')
    expect(html).toContain('New trip')
    expect(html).toContain('Saved')
    expect(html).toMatch(/href="\/planner"[^>]*aria-current="page"/)
    expect(html).not.toMatch(/href="\/explore"[^>]*aria-current="page"/)
  })

  it('highlights Explore and Saved separately from planning', () => {
    const explore = renderSidebar({ path: ROUTES.explore, view: 'saved' })
    expect(explore).toMatch(/href="\/explore"[^>]*aria-current="page"/)
    expect(explore).not.toMatch(/href="\/planner"[^>]*aria-current="page"/)
    expect(explore).not.toMatch(/<button[^>]*aria-current="page"/)

    const saved = renderSidebar({ path: ROUTES.planner, view: 'saved', savedCount: 2 })
    expect(saved).toContain('Saved (2)')
    expect(saved).toMatch(/<button[^>]*aria-current="page"[^>]*>[\s\S]*Saved \(2\)/)
    expect(saved).not.toMatch(/href="\/planner"[^>]*aria-current="page"/)
    expect(saved).not.toMatch(/href="\/explore"[^>]*aria-current="page"/)
  })
})
