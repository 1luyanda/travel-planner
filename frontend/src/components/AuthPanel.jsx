import { useAuth } from '../auth/AuthProvider'
import { AppLink, ROUTES } from '../utils/routes.jsx'
import styles from '../landing.module.css'

export default function AuthPanel() {
  const { user, loading, error: bootstrapError, logout } = useAuth()

  if (loading) return <span className={styles.authStatus}>Checking account…</span>

  if (user) {
    return (
      <div className={styles.authSignedIn}>
        <span>Hi, {user.display_name}</span>
        <AppLink to={ROUTES.planner} className={styles.startBtn}>
          Open planner
        </AppLink>
        <button type="button" className={styles.authTextButton} onClick={logout}>
          Log out
        </button>
      </div>
    )
  }

  return (
    <div className={styles.authActions}>
      {bootstrapError ? (
        <p className={styles.authError} role="alert">
          {bootstrapError}
        </p>
      ) : null}
      <AppLink to={ROUTES.login} className={styles.authLoginLink}>
        Log in
      </AppLink>
      <AppLink to={ROUTES.signup} className={styles.authGetStarted}>
        Sign up
      </AppLink>
    </div>
  )
}
