import { createContext, useCallback, useContext, useEffect, useState } from 'react'

export const ROUTES = {
  home: '/',
  planner: '/planner',
  explore: '/explore',
  docs: '/docs',
  login: '/login',
  signup: '/signup',
}

export function isPlannerPath(pathname) {
  return pathname === ROUTES.planner || pathname === ROUTES.docs
}

export function isExplorePath(pathname) {
  return pathname === ROUTES.explore
}

export function isWorkspacePath(pathname) {
  return isPlannerPath(pathname) || isExplorePath(pathname)
}

export function isAuthPath(pathname) {
  return pathname === ROUTES.login || pathname === ROUTES.signup
}

export function isAppPath(pathname) {
  return pathname === ROUTES.home || isWorkspacePath(pathname) || isAuthPath(pathname)
}

/**
 * Session-aware in-app redirect. Guests may use the planner.
 * Unsigned Explore access goes to login. Signed-in auth pages
 * go to the planner. Never follows query-string URLs.
 */
export function sessionRedirect(pathname, user) {
  if (isExplorePath(pathname) && !user) return ROUTES.login
  if (isAuthPath(pathname) && user) return ROUTES.planner
  return null
}

function readSnapshot() {
  return {
    path: window.location.pathname,
    state: window.history.state,
  }
}

export const RouteContext = createContext(null)

export function RouteProvider({ children }) {
  const [snapshot, setSnapshot] = useState(readSnapshot)

  const navigate = useCallback((to, { replace = false, state = null } = {}) => {
    const path = to.split('?')[0]
    if (replace) window.history.replaceState(state, '', to)
    else window.history.pushState(state, '', to)
    setSnapshot({ path, state })
  }, [])

  useEffect(() => {
    function sync() {
      setSnapshot(readSnapshot())
    }
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])

  useEffect(() => {
    if (snapshot.path === ROUTES.docs) {
      navigate(ROUTES.planner, { replace: true, state: snapshot.state })
    }
  }, [navigate, snapshot.path, snapshot.state])

  return (
    <RouteContext.Provider value={{ path: snapshot.path, state: snapshot.state, navigate }}>
      {children}
    </RouteContext.Provider>
  )
}

export function useRoute() {
  const value = useContext(RouteContext)
  if (!value) {
    throw new Error('useRoute must be used inside RouteProvider')
  }
  return value
}

export function AppLink({ to, className, children, replace = false, 'aria-label': ariaLabel }) {
  const { path, navigate } = useRoute()

  return (
    <a
      href={to}
      className={className}
      aria-label={ariaLabel}
      aria-current={path === to ? 'page' : undefined}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
        event.preventDefault()
        navigate(to, { replace })
      }}
    >
      {children}
    </a>
  )
}
