import BrandMark from './BrandMark'
import AuthPanel from './AuthPanel'
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
  const collagePhotos = COLLAGE.filter((item) => getDestinationImage(item.city))

  return (
    <div className={styles.page}>
      <header className={styles.header}>
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
          <AppLink to={ROUTES.planner} className={styles.startBtn}>
            Start planning
          </AppLink>
          <AuthPanel />
        </nav>
      </header>

      <section className={styles.hero} aria-labelledby="landing-title">
        <div className={styles.heroCopy}>
          <h1 id="landing-title">
            Your mood. Your budget. <span className={styles.accent}>Your next trip.</span>
          </h1>
          <p className={styles.lede}>
            Compare flights and weather for a departure city you choose.
          </p>
          <AppLink to={ROUTES.planner} className={styles.startBtnLarge}>
            Start planning
          </AppLink>
        </div>

        <div className={styles.collage}>
          {collagePhotos.map(({ city, className }) => {
            const image = getDestinationImage(city)
            return (
              <div key={city} className={className}>
                <img src={image.src} alt={image.alt} title={image.attribution} />
              </div>
            )
          })}
        </div>
      </section>

      <section className={styles.steps} id="how-it-works" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol>
          <li>
            <span>1</span>
            <div>
              <h3>Choose where you fly from</h3>
              <p>Search origin cities or include an IATA code in your request. Dates, budget, and origin can also be clarified in chat.</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <h3>Compare matches</h3>
              <p>Cards show prices, stops, duration, and weather. Missing fields stay blank.</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <h3>Refine your shortlist</h3>
              <p>Ask for cheaper, warmer, direct, or shorter trips. The planner service updates the shortlist.</p>
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
