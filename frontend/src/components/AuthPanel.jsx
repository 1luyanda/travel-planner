import { useState } from 'react'
import { useAuth } from '../auth/AuthProvider'
import { AppLink, ROUTES } from '../utils/routes.jsx'
import styles from '../landing.module.css'

export default function AuthPanel() {
  const { user, loading, error: bootstrapError, login, register, logout } = useAuth()
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ email: '', password: '', display_name: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (loading) return <span className={styles.authStatus}>Checking account…</span>

  if (user) {
    return (
      <div className={styles.authSignedIn}>
        <span>Hi, {user.display_name}</span>
        <AppLink to={ROUTES.planner} className={styles.authLink}>
          Open planner
        </AppLink>
        <button type="button" className={styles.authTextButton} onClick={logout}>
          Log out
        </button>
      </div>
    )
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (mode === 'register' && form.password.length < 12) {
      setError('Password must be at least 12 characters.')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'register') {
        await register(form)
      } else {
        await login({ email: form.email, password: form.password })
      }
      setForm({ email: '', password: '', display_name: '' })
    } catch (requestError) {
      setError(requestError?.message || 'Authentication failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.authPanel}>
      <div className={styles.authTabs} role="tablist" aria-label="Account">
        <button
          type="button"
          className={mode === 'login' ? styles.authTabActive : styles.authTab}
          onClick={() => {
            setMode('login')
            setError('')
          }}
        >
          Sign in
        </button>
        <button
          type="button"
          className={mode === 'register' ? styles.authTabActive : styles.authTab}
          onClick={() => {
            setMode('register')
            setError('')
          }}
        >
          Register
        </button>
      </div>
      <form onSubmit={submit} className={styles.authForm}>
        {mode === 'register' && (
          <input
            required
            maxLength={100}
            value={form.display_name}
            placeholder="Name"
            autoComplete="name"
            onChange={(event) => setForm({ ...form, display_name: event.target.value })}
          />
        )}
        <input
          required
          type="email"
          value={form.email}
          placeholder="Email"
          autoComplete="email"
          onChange={(event) => setForm({ ...form, email: event.target.value })}
        />
        <input
          required
          minLength={mode === 'register' ? 12 : 1}
          maxLength={128}
          type="password"
          value={form.password}
          placeholder={mode === 'register' ? 'Password (12+ characters)' : 'Password'}
          autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
          onChange={(event) => setForm({ ...form, password: event.target.value })}
        />
        <button type="submit" className={styles.authSubmit} disabled={submitting}>
          {submitting ? 'Working…' : mode === 'register' ? 'Create account' : 'Sign in'}
        </button>
      </form>
      {(error || bootstrapError) && (
        <p className={styles.authError} role="alert">
          {error || bootstrapError}
        </p>
      )}
    </div>
  )
}
