import { Compass, Heart, Map, MapPinned, Plus, X } from 'lucide-react'
import BrandMark from './BrandMark'
import { AppLink, ROUTES } from '../utils/routes.jsx'
import styles from '../workspace.module.css'

export default function Sidebar({
  view,
  path,
  history,
  savedCount,
  user,
  onLogout,
  open,
  onClose,
  onNewTrip,
  onPlanTrip,
  onExplore,
  onSaved,
  onHistory,
}) {
  const planActive = (view === 'explore' || view == null) && path !== ROUTES.explore
  const exploreActive = path === ROUTES.explore
  const savedActive = view === 'saved' && path !== ROUTES.explore

  function followClick(event, action) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
    event.preventDefault()
    action()
  }
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
          {user ? (
            <>
              <strong>{user.display_name}</strong>
              <button type="button" className={styles.accountAction} onClick={onLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <strong>Guest</strong>
              <AppLink to={ROUTES.login} className={styles.accountAction}>
                Log in to save trips
              </AppLink>
            </>
          )}
        </div>

        <button type="button" className={styles.newTrip} onClick={onNewTrip} title="New trip">
          <Plus size={16} strokeWidth={2} />
          New trip
        </button>

        <nav className={styles.nav} aria-label="Workspace">
          <a
            href={ROUTES.planner}
            className={planActive ? styles.navBtnActive : styles.navBtn}
            aria-current={planActive ? 'page' : undefined}
            title="Plan a trip"
            onClick={(event) => followClick(event, onPlanTrip)}
          >
            <Map size={18} strokeWidth={1.75} />
            Plan a trip
          </a>
          <a
            href={ROUTES.explore}
            className={exploreActive ? styles.navBtnActive : styles.navBtn}
            aria-current={exploreActive ? 'page' : undefined}
            title="Explore"
            onClick={(event) => followClick(event, onExplore)}
          >
            <MapPinned size={18} strokeWidth={1.75} />
            Explore
          </a>
          {user ? (
            <button
              type="button"
              className={savedActive ? styles.navBtnActive : styles.navBtn}
              aria-current={savedActive ? 'page' : undefined}
              title="Saved"
              onClick={onSaved}
            >
              <Heart size={18} strokeWidth={1.75} />
              Saved{savedCount ? ` (${savedCount})` : ''}
            </button>
          ) : null}
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
