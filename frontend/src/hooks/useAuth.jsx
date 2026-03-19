import { useState, useEffect, createContext, useContext } from 'react'
import { authApi } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(() => {
    try { return JSON.parse(localStorage.getItem('user')) } catch { return null }
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) { setLoading(false); return }
    authApi.me()
      .then(r => { setUser(r.data); localStorage.setItem('user', JSON.stringify(r.data)) })
      .catch(() => { localStorage.clear() })
      .finally(() => setLoading(false))
  }, [])

  const login = async (email, password) => {
    const r = await authApi.login({ email, password })
    localStorage.setItem('access_token',  r.data.access_token)
    localStorage.setItem('refresh_token', r.data.refresh_token)
    const me = await authApi.me()
    setUser(me.data)
    localStorage.setItem('user', JSON.stringify(me.data))
    return me.data
  }

  const register = async (email, password, full_name) => {
    await authApi.register({ email, password, full_name })
    return login(email, password)
  }

  const logout = () => {
    localStorage.clear()
    setUser(null)
    window.location.href = '/login'
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)