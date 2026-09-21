import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthProvider'
import { NAME_MAX, PASSWORD_MAX, PASSWORD_MIN, submitRegister } from '../utils/authForms'
import { AppLink, ROUTES, useRoute } from '../utils/routes.jsx'
import AuthScreen from './AuthScreen'
import PasswordField from './PasswordField'
import styles from '../landing.module.css'

export default function SignupPage() {
  const { user, loading, error: bootstrapError, register } = useAuth()
  const { navigate } = useRoute()
  const [form, setForm] = useState({
    display_name: '',
    email: '',
    password: '',
    confirm_password: '',
  })
  const [error, setError] = useState('')
  const [pendingMessage, setPendingMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  useEffect(() => {
    if (!loading && user) navigate(ROUTES.planner, { replace: true })
  }, [loading, navigate, user])

  if (loading) {
    return (
      <AuthScreen title="Sign up">
        <p className={styles.authStatus}>Checking account…</p>
      </AuthScreen>
    )
  }

  if (user) {
    return (
      <AuthScreen title="Sign up">
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
      const result = await submitRegister({ register, form })
      if (result.status === 'invalid') {
        setError(result.error)
        return
      }
      if (result.status === 'pending') {
        setPendingMessage(result.message)
        return
      }
      navigate(ROUTES.planner)
    } catch (requestError) {
      setError(requestError?.message || 'Authentication failed. Please try again.')
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  if (pendingMessage) {
    return (
      <AuthScreen title="Sign up">
        <p className={styles.authPending} role="status">
          {pendingMessage}
        </p>
        <p className={styles.authSwitch}>
          Already have an account? <AppLink to={ROUTES.login}>Log in</AppLink>
        </p>
        <p className={styles.authSwitch}>
          <AppLink to={ROUTES.home}>Back to homepage</AppLink>
        </p>
      </AuthScreen>
    )
  }

  const visibleError = error || bootstrapError
  const errorId = visibleError ? 'signup-error' : undefined

  return (
    <AuthScreen title="Sign up">
      <form onSubmit={submit} className={styles.authPageForm}>
        <div className={styles.authField}>
          <label htmlFor="signup-name">Name</label>
          <input
            id="signup-name"
            required
            maxLength={NAME_MAX}
            value={form.display_name}
            autoComplete="name"
            aria-invalid={Boolean(visibleError)}
            aria-describedby={errorId}
            onChange={(event) => setForm({ ...form, display_name: event.target.value })}
          />
        </div>
        <div className={styles.authField}>
          <label htmlFor="signup-email">Email</label>
          <input
            id="signup-email"
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
          id="signup-password"
          label="Password"
          value={form.password}
          autoComplete="new-password"
          minLength={PASSWORD_MIN}
          maxLength={PASSWORD_MAX}
          describedBy={errorId}
          onChange={(event) => setForm({ ...form, password: event.target.value })}
        />
        <PasswordField
          id="signup-confirm-password"
          label="Confirm password"
          value={form.confirm_password}
          autoComplete="new-password"
          minLength={PASSWORD_MIN}
          maxLength={PASSWORD_MAX}
          describedBy={errorId}
          toggleLabel="confirm password"
          onChange={(event) => setForm({ ...form, confirm_password: event.target.value })}
        />
        <button type="submit" className={styles.authPageSubmit} disabled={submitting}>
          {submitting ? 'Working…' : 'Create account'}
        </button>
      </form>
      {visibleError ? (
        <p id="signup-error" className={styles.authError} role="alert">
          {visibleError}
        </p>
      ) : null}
      <p className={styles.authSwitch}>
        Already have an account? <AppLink to={ROUTES.login}>Log in</AppLink>
      </p>
      <p className={styles.authSwitch}>
        <AppLink to={ROUTES.home}>Back to homepage</AppLink>
      </p>
    </AuthScreen>
  )
}
