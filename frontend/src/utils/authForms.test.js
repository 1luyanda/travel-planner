import { describe, expect, it, vi } from 'vitest'
import {
  NAME_MAX,
  PASSWORD_MAX,
  PASSWORD_MIN,
  VERIFY_EMAIL_MESSAGE,
  registerRequestBody,
  submitLogin,
  submitRegister,
  validateSignupForm,
} from './authForms'

const validForm = {
  display_name: 'Ada Lovelace',
  email: 'ada@example.com',
  password: 'a-long-demo-password',
  confirm_password: 'a-long-demo-password',
}

describe('signup validation', () => {
  it('rejects mismatched passwords before the API is called', async () => {
    const register = vi.fn()
    const result = await submitRegister({
      register,
      form: { ...validForm, confirm_password: 'a-different-password' },
    })

    expect(result).toEqual({ status: 'invalid', error: 'Passwords do not match.' })
    expect(register).not.toHaveBeenCalled()
    expect(validateSignupForm({ ...validForm, confirm_password: 'nope' })).toBe(
      'Passwords do not match.',
    )
  })

  it('keeps name and password length limits', () => {
    expect(validateSignupForm({ ...validForm, display_name: 'A'.repeat(NAME_MAX + 1) })).toBe(
      `Name must be ${NAME_MAX} characters or fewer.`,
    )
    expect(validateSignupForm({ ...validForm, password: 'short', confirm_password: 'short' })).toBe(
      `Password must be at least ${PASSWORD_MIN} characters.`,
    )
    expect(
      validateSignupForm({
        ...validForm,
        password: 'x'.repeat(PASSWORD_MAX + 1),
        confirm_password: 'x'.repeat(PASSWORD_MAX + 1),
      }),
    ).toBe(`Password must be ${PASSWORD_MAX} characters or fewer.`)
  })

  it('does not send the confirm-password field to register', async () => {
    const register = vi.fn(async () => ({ id: 'user-1', display_name: 'Ada Lovelace' }))
    const result = await submitRegister({ register, form: validForm })

    expect(register).toHaveBeenCalledWith({
      email: 'ada@example.com',
      password: 'a-long-demo-password',
      display_name: 'Ada Lovelace',
    })
    expect(register.mock.calls[0][0]).not.toHaveProperty('confirm_password')
    expect(registerRequestBody(validForm)).not.toHaveProperty('confirm_password')
    expect(result).toMatchObject({ status: 'signed_in', user: { id: 'user-1' } })
  })

  it('asks the user to verify email when register does not return a session user', async () => {
    const register = vi.fn(async () => null)
    await expect(submitRegister({ register, form: validForm })).resolves.toEqual({
      status: 'pending',
      message: VERIFY_EMAIL_MESSAGE,
    })
  })

  it('surfaces failed registration requests', async () => {
    const register = vi.fn(async () => {
      throw new Error('An account with that email already exists.')
    })
    await expect(submitRegister({ register, form: validForm })).rejects.toThrow(
      'An account with that email already exists.',
    )
  })
})

describe('login submission', () => {
  it('calls login with email and password and returns the user', async () => {
    const login = vi.fn(async () => ({ id: 'user-1', display_name: 'Ada' }))
    await expect(
      submitLogin({ login, email: 'ada@example.com', password: 'a-long-demo-password' }),
    ).resolves.toMatchObject({ id: 'user-1' })
    expect(login).toHaveBeenCalledWith({
      email: 'ada@example.com',
      password: 'a-long-demo-password',
    })
  })

  it('keeps failed login errors visible', async () => {
    const login = vi.fn(async () => {
      throw new Error('Invalid email or password.')
    })
    await expect(
      submitLogin({ login, email: 'ada@example.com', password: 'wrong-password' }),
    ).rejects.toThrow('Invalid email or password.')
  })
})
