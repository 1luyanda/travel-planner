import BrandMark from './BrandMark'
import AuthPanel from './AuthPanel'
import { useAuth } from '../auth/AuthProvider'
import { getDestinationImage } from '../data/destinationImages'
import { AppLink, ROUTES } from '../utils/routes.jsx'
import styles from '../landing.module.css'

const COLLAGE = [
  { city: 'Rome', className: styles.shotMain },
  { city: 'Lisbon', className: styles.shotMid },
  { city: 'Athens', className: styles.shotRound },
  { city: 'Malta', className: styles.shotSmall },
]

export default function LandingPage() {
  const { user } = useAuth()
  const collagePhotos = COLLAGE.filter((item) => getDestinationImage(item.city))
  const signedIn = Boolean(user)

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <AppLink to={ROUTES.home} className={styles.brand} aria-label="Travel Planner home">
            <BrandMark className={styles.brandMark} />
            Travel <em>Planner</em>
          </AppLink>
          <nav className={styles.nav} aria-label="Landing">
            <a className={styles.navText} href="#how-it-works">
              How it works
            </a>
            <a className={styles.navText} href="#explore-destinations">
              Explore destinations
            </a>
          </nav>
          <div className={styles.headerActions}>
            <AuthPanel />
          </div>
        </div>
      </header>
      
      <section className={styles.hero} aria-labelledby="landing-title">
        <div className={styles.heroInner}>
          <div className={styles.heroCopy}>
            <h1 id="landing-title">
              Your mood. Your budget. <span className={styles.accent}>Your next trip.</span>
            </h1>
            <p className={styles.lede}>
              Tell us your budget, dates and travel preferences. Compare destinations by
              flight price, stops and weather.
            </p>
            <AppLink to={ROUTES.planner} className={styles.startBtnLarge}>
              {signedIn ? 'Open your planner' : 'Start planning'}
            </AppLink>
            <p className={styles.heroHint}>Choose your departure city and dates to get started.</p>
          </div>

          <div className={styles.collage}>
            {collagePhotos.map(({ city, className }) => {
              const image = getDestinationImage(city)
              return (
                <figure key={city} className={className}>
                  <img src={image.src} alt={image.alt} title={image.attribution} />
                  <figcaption className={styles.shotLabel}>{city}</figcaption>
                </figure>
              )
            })}
          </div>
        </div>
      </section>

      <section className={styles.steps} id="how-it-works" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol>
          <li>
            <span>1</span>
            <div>
              <h3>Tell us your plans</h3>
              <p>Choose your departure city, dates and budget.</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <h3>Compare destinations</h3>
              <p>Explore recommendations, flight details and weather.</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <h3>Refine your choices</h3>
              <p>Adjust your preferences and save your favourites.</p>
            </div>
          </li>
        </ol>
      </section>

      <section className={styles.explore} id="explore-destinations" aria-labelledby="explore-title">
        <h2 id="explore-title">Explore destinations</h2>
        <p>
          Search from a departure city to see matching trips. Origin autocomplete is optional.
        </p>
        <AppLink to={ROUTES.planner} className={styles.startBtn}>
          Open the planner
        </AppLink>
      </section>
    </div>
  )
}
