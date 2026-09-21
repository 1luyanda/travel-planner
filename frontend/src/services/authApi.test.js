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

  it('surfaces FastAPI validation details instead of a generic failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [{ msg: 'String should have at least 12 characters' }],
        }),
      })),
    )

    await expect(
      loginUser({ email: 'person@example.com', password: 'short' }),
    ).rejects.toMatchObject({
      status: 422,
      message: 'String should have at least 12 characters',
    })
  })

  it('explains when the authentication service cannot be reached', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )

    await expect(
      loginUser({ email: 'person@example.com', password: 'a-long-demo-password' }),
    ).rejects.toMatchObject({
      status: 0,
      message: 'Could not reach the authentication service. Check that the API is running.',
    })
  })
})
