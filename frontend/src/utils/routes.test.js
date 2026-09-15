import { describe, expect, it } from 'vitest'
import { ROUTES, isPlannerPath } from './routes.jsx'

describe('routes', () => {
  it('sends the planner and docs compatibility path to the workspace', () => {
    expect(isPlannerPath(ROUTES.planner)).toBe(true)
    expect(isPlannerPath(ROUTES.docs)).toBe(true)
    expect(isPlannerPath(ROUTES.home)).toBe(false)
  })
})
