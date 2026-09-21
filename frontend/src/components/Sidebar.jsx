import { Compass, Heart, Map, Plus, X } from 'lucide-react'
import BrandMark from './BrandMark'
import { AppLink, ROUTES } from '../utils/routes.jsx'
import styles from '../workspace.module.css'

export default function Sidebar({
  view,
  history,
  savedCount,
  user,
  onLogout,
  open,
  onClose,
  onNewTrip,
  onExplore,
  onSaved,
  onHistory,
}) {
  return (
    <>
      {open && (
        <button type="button" className={styles.sidebarScrim} aria-label="Close navigation" onClick={onClose} />
      )}
      <aside className={`${styles.sidebar} ${open ? styles.sidebarOpen : ''}`} aria-label="Travel Planner">
        <div className={styles.sidebarTop}>
          <AppLink to={ROUTES.home} className={styles.brand} aria-label="Travel Planner home">
            <BrandMark className={styles.brandMark} />
            <span>
              Travel <em>Planner</em>
            </span>
          </AppLink>
          <button type="button" className={`${styles.iconBtn} ${styles.sidebarClose}`} onClick={onClose} aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <div className={styles.accountBox}>
          <strong>{user.display_name}</strong>
          <button type="button" className={styles.accountAction} onClick={onLogout}>
            Log out
          </button>
        </div>

        <button type="button" className={styles.newTrip} onClick={onNewTrip} title="New trip">
          <Plus size={16} strokeWidth={2} />
          New trip
        </button>

        <nav className={styles.nav} aria-label="Workspace">
          <button
            type="button"
            className={view === 'explore' ? styles.navBtnActive : styles.navBtn}
            aria-current={view === 'explore' ? 'page' : undefined}
            title="Explore"
            onClick={onExplore}
          >
            <Map size={18} strokeWidth={1.75} />
            Explore
          </button>
          <button
            type="button"
            className={view === 'saved' ? styles.navBtnActive : styles.navBtn}
            aria-current={view === 'saved' ? 'page' : undefined}
            title="Saved"
            onClick={onSaved}
          >
            <Heart size={18} strokeWidth={1.75} />
            Saved{savedCount ? ` (${savedCount})` : ''}
          </button>
        </nav>

        {history.length > 0 && (
          <div className={styles.history}>
            <h2>Recent</h2>
            <ul>
              {history.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => onHistory(item)}>
                    <Compass size={14} strokeWidth={1.75} />
                    {item.title}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </>
  )
}
