export const NAME_MAX = 100
export const PASSWORD_MIN = 12
export const PASSWORD_MAX = 128

export const VERIFY_EMAIL_MESSAGE =
  'Your account was created. Verify your email, then log in to continue.'

export function validateSignupForm({ display_name, password, confirm_password }) {
  const name = (display_name || '').trim()
  if (!name) return 'Enter your name.'
  if (name.length > NAME_MAX) return `Name must be ${NAME_MAX} characters or fewer.`
  if ((password || '').length < PASSWORD_MIN) {
    return `Password must be at least ${PASSWORD_MIN} characters.`
  }
  if ((password || '').length > PASSWORD_MAX) {
    return `Password must be ${PASSWORD_MAX} characters or fewer.`
  }
  if (password !== confirm_password) return 'Passwords do not match.'
  return ''
}

export function registerRequestBody({ email, password, display_name }) {
  return {
    email,
    password,
    display_name: (display_name || '').trim(),
  }
}

export async function submitLogin({ login, email, password }) {
  const user = await login({ email, password })
  if (!user) {
    throw new Error('Authentication failed. Please try again.')
  }
  return user
}

export async function submitRegister({ register, form }) {
  const error = validateSignupForm(form)
  if (error) return { status: 'invalid', error }
  const user = await register(registerRequestBody(form))
  if (!user) return { status: 'pending', message: VERIFY_EMAIL_MESSAGE }
  return { status: 'signed_in', user }
}
