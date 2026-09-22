import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import AuthPanel from '../components/AuthPanel'
import LandingPage from '../components/LandingPage'
import LoginPage from '../components/LoginPage'
import Sidebar from '../components/Sidebar'
import SignupPage from '../components/SignupPage'

const auth = {
  user: null,
  loading: false,
  error: '',
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}

vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => auth,
}))

vi.mock('../utils/routes.jsx', async () => {
  const actual = await vi.importActual('../utils/routes.jsx')
  return {
    ...actual,
    useRoute: () => ({ path: '/', navigate: vi.fn() }),
    AppLink: ({ to, className, children, 'aria-label': ariaLabel }) => (
      <a href={to} className={className} aria-label={ariaLabel}>
        {children}
      </a>
    ),
  }
})

describe('auth navigation', () => {
  beforeEach(() => {
    auth.user = null
    auth.loading = false
    auth.error = ''
  })

  it('replaces the landing header form with login and signup links', () => {
    const html = renderToStaticMarkup(<LandingPage />)
    expect(html).toContain('href="/login"')
    expect(html).toContain('Log in')
    expect(html).toContain('href="/signup"')
    expect(html).toContain('Sign up')
    expect(html).not.toContain('Get started')
    expect(html).toContain('Start planning')
    expect((html.match(/Start planning/g) || []).length).toBe(1)
    expect(html).not.toContain('Get app')
    expect(html).not.toContain('placeholder="Email"')
    expect(html).not.toContain('role="tablist"')
    expect(html).toContain('href="/planner"')
    expect(html).toContain('Continue as guest')
    expect(html).toContain('Your mood. Your budget.')
    expect(html).toContain('Tell us your budget, dates and travel preferences.')
    expect(html).toContain('Choose your departure city and dates to get started.')
    expect(html).toContain('Tell us your plans')
    expect(html).toContain('Compare destinations')
    expect(html).toContain('Refine your choices')
    expect(html).toContain('href="#how-it-works"')
    expect(html).toContain('href="#explore-destinations"')
  })

  it('shows one Open planner action and the user name when signed in', () => {
    auth.user = { id: 'user-1', display_name: 'Ada' }
    const html = renderToStaticMarkup(<LandingPage />)
    expect(html).toContain('Hi, Ada')
    expect(html).toContain('Open planner')
    expect(html).toContain('Open your planner')
    expect(html).toContain('Log out')
    expect(html).toContain('href="/planner"')
    expect(html).not.toContain('Start planning')
    expect(html).not.toContain('href="/login"')
    expect((html.match(/Open planner/g) || []).length).toBe(1)
  })

  it('preserves signed-in greeting, planner link, and logout in the header', () => {
    auth.user = { id: 'user-1', display_name: 'Ada' }
    const html = renderToStaticMarkup(<AuthPanel />)
    expect(html).toContain('Hi, Ada')
    expect(html).toContain('href="/planner"')
    expect(html).toContain('Open planner')
    expect(html).toContain('Log out')
    expect(html).not.toContain('href="/login"')
  })

  it('keeps the compact checking-account header state', () => {
    auth.loading = true
    expect(renderToStaticMarkup(<AuthPanel />)).toContain('Checking account…')
  })

  it('links the login page to signup and home', () => {
    const html = renderToStaticMarkup(<LoginPage />)
    expect(html).toContain('for="login-email">Email')
    expect(html).toContain('for="login-password">Password')
    expect(html).toContain('Show password')
    expect(html).toContain('href="/signup"')
    expect(html).toContain('Sign up')
    expect(html).toContain('href="/"')
    expect(html).toContain('Back to homepage')
    expect(html).toContain('href="/planner"')
    expect(html).toContain('Continue as guest')
    expect(html).toContain('autoComplete="current-password"')
  })

  it('links the signup page to login and home with matching labels', () => {
    const html = renderToStaticMarkup(<SignupPage />)
    expect(html).toContain('for="signup-name">Name')
    expect(html).toContain('for="signup-email">Email')
    expect(html).toContain('for="signup-password">Password')
    expect(html).toContain('for="signup-confirm-password">Confirm password')
    expect(html).toContain('maxLength="100"')
    expect(html).toContain('minLength="12"')
    expect(html).toContain('maxLength="128"')
    expect(html).toContain('href="/login"')
    expect(html).toContain('Log in')
    expect(html).toContain('Back to homepage')
    expect(html).toContain('href="/planner"')
    expect(html).toContain('Continue as guest')
    expect(html).toContain('autoComplete="name"')
    expect(html).toContain('autoComplete="new-password"')
  })

  it('lets guests open the planner without a Saved tab', () => {
    const html = renderToStaticMarkup(
      <Sidebar view="explore" history={[]} savedCount={0} user={null} />,
    )
    expect(html).toContain('Guest')
    expect(html).toContain('Log in to save trips')
    expect(html).toContain('href="/login"')
    expect(html).not.toContain('Saved')
  })

  it('keeps Saved available for signed-in users', () => {
    const html = renderToStaticMarkup(
      <Sidebar
        view="explore"
        history={[]}
        savedCount={2}
        user={{ display_name: 'Ada' }}
      />,
    )
    expect(html).toContain('Ada')
    expect(html).toContain('Saved (2)')
    expect(html).toContain('Log out')
  })
})
