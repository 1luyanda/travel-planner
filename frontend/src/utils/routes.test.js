import { describe, expect, it } from 'vitest'
import { ROUTES, isAppPath, isAuthPath, isPlannerPath } from './routes.jsx'

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
})
