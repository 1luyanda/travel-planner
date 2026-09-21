import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthProvider'
import { submitLogin } from '../utils/authForms'
import { AppLink, ROUTES, useRoute } from '../utils/routes.jsx'
import AuthScreen from './AuthScreen'
import PasswordField from './PasswordField'
import styles from '../landing.module.css'

export default function LoginPage() {
  const { user, loading, error: bootstrapError, login } = useAuth()
  const { navigate } = useRoute()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  useEffect(() => {
    if (!loading && user) navigate(ROUTES.planner, { replace: true })
  }, [loading, navigate, user])

  if (loading) {
    return (
      <AuthScreen title="Log in">
        <p className={styles.authStatus}>Checking account…</p>
      </AuthScreen>
    )
  }

  if (user) {
    return (
      <AuthScreen title="Log in">
        <p className={styles.authStatus}>Redirecting to the planner…</p>
      </AuthScreen>
    )
  }

  async function submit(event) {
    event.preventDefault()
    if (submittingRef.current) return
    submittingRef.current = true
    setError('')
    setSubmitting(true)
    try {
      await submitLogin({ login, email: form.email, password: form.password })
      navigate(ROUTES.planner)
    } catch (requestError) {
      setError(requestError?.message || 'Authentication failed. Please try again.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const visibleError = error || bootstrapError
  const errorId = visibleError ? 'login-error' : undefined

  return (
    <AuthScreen title="Log in">
      <form onSubmit={submit} className={styles.authPageForm}>
        <div className={styles.authField}>
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            required
            type="email"
            value={form.email}
            autoComplete="email"
            aria-invalid={Boolean(visibleError)}
            aria-describedby={errorId}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
        </div>
        <PasswordField
          id="login-password"
          label="Password"
          value={form.password}
          autoComplete="current-password"
          maxLength={128}
          describedBy={errorId}
          onChange={(event) => setForm({ ...form, password: event.target.value })}
        />
        <button type="submit" className={styles.authPageSubmit} disabled={submitting}>
          {submitting ? 'Working…' : 'Log in'}
        </button>
      </form>
      {visibleError ? (
        <p id="login-error" className={styles.authError} role="alert">
          {visibleError}
        </p>
      ) : null}
      <p className={styles.authSwitch}>
        New here? <AppLink to={ROUTES.signup}>Sign up</AppLink>
      </p>
      <p className={styles.authSwitch}>
        <AppLink to={ROUTES.home}>Back to homepage</AppLink>
      </p>
    </AuthScreen>
  )
}
