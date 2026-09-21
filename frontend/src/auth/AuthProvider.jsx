import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { ApiError } from '../services/travelApi'
import {
  fetchCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from '../services/authApi'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refreshUser = useCallback(async () => {
    try {
      const currentUser = await fetchCurrentUser()
      setUser(currentUser)
      setError('')
      return currentUser
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        setUser(null)
        setError('')
        return null
      }
      setUser(null)
      setError(requestError?.message || 'Could not load your account.')
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshUser()
  }, [refreshUser])

  const register = useCallback(async (details) => {
    const currentUser = await registerUser(details)
    setUser(currentUser)
    setError('')
    return currentUser
  }, [])

  const login = useCallback(async (details) => {
    const currentUser = await loginUser(details)
    setUser(currentUser)
    setError('')
    return currentUser
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutUser()
    } finally {
      setUser(null)
      setError('')
    }
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        register,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
