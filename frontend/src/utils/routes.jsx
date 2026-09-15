import { createContext, useCallback, useContext, useEffect, useState } from 'react'

export const ROUTES = {
  home: '/',
  planner: '/planner',
  docs: '/docs',
}

export function isPlannerPath(pathname) {
  return pathname === ROUTES.planner || pathname === ROUTES.docs
}

function readSnapshot() {
  return {
    path: window.location.pathname,
    state: window.history.state,
  }
}

const RouteContext = createContext(null)

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
