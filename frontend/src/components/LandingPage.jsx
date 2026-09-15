import BrandMark from './BrandMark'
import DestinationPhoto from './DestinationPhoto'
import { formatPrice } from '../utils/format'
import { getDestinationImage } from '../data/destinationImages'
import { AppLink, ROUTES } from '../utils/routes.jsx'
import styles from '../landing.module.css'

function FloatingCard({ destination, className, onSelect }) {
  const city = destination.destination?.city
  const price = formatPrice(destination.flight)
  if (!city || !price) return null

  return (
    <button type="button" className={className} onClick={() => onSelect(destination)}>
      <strong>{city}</strong>
      <span>{price}</span>
    </button>
  )
}

export default function LandingPage({ destinations, onSelectDestination }) {
  const previews = destinations.slice(0, 4)
  const [rome, malta, lisbon, athens] = ['Rome', 'Malta', 'Lisbon', 'Athens'].map((city) =>
    destinations.find((item) => item.destination?.city === city),
  )
  const collagePhotos = [
    { destination: rome, className: styles.shotMain },
    { destination: lisbon, className: styles.shotMid },
    { destination: athens, className: styles.shotRound },
    { destination: malta, className: styles.shotSmall },
  ].filter((item) => item.destination && getDestinationImage(item.destination.destination?.city))

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <AppLink to={ROUTES.home} className={styles.brand} aria-label="Travel Planner home">
          <BrandMark className={styles.brandMark} />
          Travel <em>Planner</em>
        </AppLink>
        <nav className={styles.nav} aria-label="Landing">
          <a href="#how-it-works">How it works</a>
          <a href="#explore-destinations">Explore destinations</a>
          <AppLink to={ROUTES.planner} className={styles.startBtn}>
            Start planning
          </AppLink>
        </nav>
      </header>

      <section className={styles.hero} aria-labelledby="landing-title">
        <div className={styles.heroCopy}>
          <p className={styles.badge}>Demo · Mock data</p>
          <h1 id="landing-title">
            Your mood. Your budget. <span className={styles.accent}>Your next trip.</span>
          </h1>
          <p className={styles.lede}>
            Explore destinations, compare flight and weather details, and find a getaway that fits.
          </p>
          <AppLink to={ROUTES.planner} className={styles.startBtnLarge}>
            Start planning
          </AppLink>
        </div>

        <div className={styles.collage}>
          {collagePhotos.map(({ destination, className }) => (
            <div key={destination.id} className={className}>
              <DestinationPhoto destination={destination} sizes="280px" />
            </div>
          ))}
          {rome && (
            <FloatingCard
              destination={rome}
              onSelect={onSelectDestination}
              className={`${styles.floatCard} ${styles.floatOne}`}
            />
          )}
          {malta && (
            <FloatingCard
              destination={malta}
              onSelect={onSelectDestination}
              className={`${styles.floatCard} ${styles.floatTwo}`}
            />
          )}
          {lisbon && (
            <FloatingCard
              destination={lisbon}
              onSelect={onSelectDestination}
              className={`${styles.floatCard} ${styles.floatThree}`}
            />
          )}
        </div>
      </section>

      <section className={styles.steps} id="how-it-works" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol>
          <li>
            <span>1</span>
            <div>
              <h3>Describe your getaway</h3>
              <p>Share a mood, budget, and departure airport. This demo reads those fields locally.</p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <h3>Compare your matches</h3>
              <p>Ranked cards show real mock prices, stops, duration, and weather side by side.</p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <h3>Refine your shortlist</h3>
              <p>Weight cheaper, warmer, direct, or shorter trips without leaving the planner.</p>
            </div>
          </li>
        </ol>
      </section>

      <section className={styles.explore} id="explore-destinations" aria-labelledby="explore-title">
        <h2 id="explore-title">Explore destinations</h2>
        <p>From the mock dataset. Selecting a city opens the planner with that trip selected.</p>
        <div className={styles.grid}>
          {previews.map((destination) => {
            const city = destination.destination?.city || 'Destination'
            const country = destination.country?.common_name
            return (
              <button
                key={destination.id}
                type="button"
                className={styles.preview}
                onClick={() => onSelectDestination(destination)}
              >
                <DestinationPhoto destination={destination} sizes="240px" />
                <span>
                  <strong>{city}</strong>
                  {country && <em>{country}</em>}
                  {formatPrice(destination.flight) && <b>{formatPrice(destination.flight)}</b>}
                </span>
              </button>
            )
          })}
        </div>
      </section>
    </div>
  )
}
