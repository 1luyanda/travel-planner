import { workspaceImages } from '../data/destinationImages'
import styles from '../workspace.module.css'

export default function InspirationPanel({ onPlan, onExplore }) {
  return (
    <aside className={styles.inspiration} aria-label="Get started">
      <h2>Get started</h2>
      <div className={styles.tiles}>
        <button type="button" className={styles.tile} onClick={onPlan}>
          <img src={workspaceImages.tileGetaway.src} alt="" />
          <span>Plan a getaway</span>
        </button>
        <button type="button" className={styles.tile} onClick={onExplore}>
          <img src={workspaceImages.tileExplore.src} alt="" />
          <span>Explore activities</span>
        </button>
      </div>
    </aside>
  )
}
