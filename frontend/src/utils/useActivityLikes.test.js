import { describe, expect, it, vi } from 'vitest'
import { followActivityLikeResult } from './useActivityLikes'
import { ROUTES } from './routes.jsx'

describe('followActivityLikeResult', () => {
  it('uses the existing login route when a like requires authentication', () => {
    const navigate = vi.fn()
    expect(followActivityLikeResult({ requiresAuth: true }, navigate)).toEqual({ requiresAuth: true })
    expect(navigate).toHaveBeenCalledWith(ROUTES.login)
    expect(ROUTES.login).toBe('/login')
  })

  it('does not navigate after a successful like', () => {
    const navigate = vi.fn()
    expect(followActivityLikeResult({ ok: true, liked: true }, navigate)).toEqual({
      ok: true,
      liked: true,
    })
    expect(navigate).not.toHaveBeenCalled()
  })
})
