import React, { createContext, useContext, useEffect, useState } from 'react'
import type { User, LoginRequest, RegisterRequest } from '../types/auth'
import { api } from '../services/api'

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (req: LoginRequest) => Promise<void>
  register: (req: RegisterRequest) => Promise<User>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)

  const refreshUser = async () => {
    try {
      const currentUser = await api.getCurrentUser()
      setUser(currentUser)
    } catch {
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    refreshUser()
  }, [])

  const login = async (req: LoginRequest) => {
    const res = await api.login(req)
    setUser(res.user)
  }

  const register = async (req: RegisterRequest): Promise<User> => {
    const newUser = await api.register(req)
    return newUser
  }

  const logout = async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

const defaultAuthContext: AuthContextType = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  login: async () => {},
  register: async () => ({} as User),
  logout: async () => {},
  refreshUser: async () => {},
}

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext)
  return context || defaultAuthContext
}
