import BrandMark from './BrandMark'
import { AppLink, ROUTES } from '../utils/routes.jsx'
import styles from '../landing.module.css'

export default function AuthScreen({ title, children }) {
  return (
    <div className={styles.authPage}>
      <header className={styles.authPageHeader}>
        <AppLink to={ROUTES.home} className={styles.brand} aria-label="Travel Planner home">
          <BrandMark className={styles.brandMark} />
          Travel <em>Planner</em>
        </AppLink>
      </header>
      <main className={styles.authMain}>
        <section className={styles.authCard} aria-labelledby="auth-heading">
          <h1 id="auth-heading">{title}</h1>
          {children}
        </section>
      </main>
    </div>
  )
}
