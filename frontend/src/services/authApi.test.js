import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchCurrentUser, loginUser, logoutUser, registerUser } from './authApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('local auth API', () => {
  it('registers with credentials included and returns the safe user', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_path, options) => {
        expect(options.credentials).toBe('include')
        expect(options.method).toBe('POST')
        return {
          ok: true,
          status: 201,
          json: async () => ({
            user: { id: 'user-1', email: 'person@example.com' },
          }),
        }
      }),
    )

    await expect(
      registerUser({
        email: 'person@example.com',
        password: 'a-long-demo-password',
        display_name: 'Person',
      }),
    ).resolves.toMatchObject({ id: 'user-1' })
  })

  it('keeps login failures generic and supports me/logout', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Invalid email or password.' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 'user-1', email: 'person@example.com' }),
      })
      .mockResolvedValueOnce({ ok: true, status: 204, json: async () => null })
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      loginUser({ email: 'person@example.com', password: 'wrong-password' }),
    ).rejects.toMatchObject({
      status: 401,
      message: 'Invalid email or password.',
    })
    await expect(fetchCurrentUser()).resolves.toMatchObject({ id: 'user-1' })
    await expect(logoutUser()).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1][1].credentials).toBe('include')
  })
})
