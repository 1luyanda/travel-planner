import { describe, expect, it } from 'vitest'
import { ROUTES, isAppPath, isAuthPath, isPlannerPath, sessionRedirect } from './routes.jsx'

describe('routes', () => {
  it('sends the planner and docs compatibility path to the workspace', () => {
    expect(isPlannerPath(ROUTES.planner)).toBe(true)
    expect(isPlannerPath(ROUTES.docs)).toBe(true)
    expect(isPlannerPath(ROUTES.home)).toBe(false)
    expect(isPlannerPath(ROUTES.login)).toBe(false)
  })

  it('keeps login and signup as dedicated public auth routes', () => {
    expect(ROUTES.login).toBe('/login')
    expect(ROUTES.signup).toBe('/signup')
    expect(isAuthPath(ROUTES.login)).toBe(true)
    expect(isAuthPath(ROUTES.signup)).toBe(true)
    expect(isAuthPath(ROUTES.home)).toBe(false)
    expect(isAppPath(ROUTES.login)).toBe(true)
    expect(isAppPath(ROUTES.signup)).toBe(true)
    expect(isAppPath('/unknown')).toBe(false)
  })

  it('lets guests stay on the planner and sends signed-in auth pages to the planner', () => {
    expect(sessionRedirect(ROUTES.planner, null)).toBeNull()
    expect(sessionRedirect(ROUTES.docs, null)).toBeNull()
    expect(sessionRedirect(ROUTES.login, { id: 'user-1' })).toBe(ROUTES.planner)
    expect(sessionRedirect(ROUTES.signup, { id: 'user-1' })).toBe(ROUTES.planner)
    expect(sessionRedirect(ROUTES.planner, { id: 'user-1' })).toBeNull()
    expect(sessionRedirect(ROUTES.login, null)).toBeNull()
    expect(sessionRedirect(ROUTES.home, null)).toBeNull()
    expect(sessionRedirect('https://evil.example/phish', null)).toBeNull()
    expect(sessionRedirect('/login?next=https://evil.example', null)).toBeNull()
  })
})
