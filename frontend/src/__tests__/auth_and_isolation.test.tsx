import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { LoginPage } from '../pages/LoginPage'
import { RegisterPage } from '../pages/RegisterPage'
import { VerifyEmailPage } from '../pages/VerifyEmailPage'
import { ForgotPasswordPage } from '../pages/ForgotPasswordPage'
import { ResetPasswordPage } from '../pages/ResetPasswordPage'
import { ProtectedRoute } from '../components/ProtectedRoute'
import { Header } from '../components/Header'
import { AuthProvider } from '../context/AuthContext'
import { api } from '../services/api'

vi.mock('../services/api')

describe('Frontend Authentication - Pages & Route Guards', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders LoginPage and handles successful login', async () => {
    vi.mocked(api.login).mockResolvedValue({
      user: {
        id: 'user-1',
        email: 'tester@example.com',
        is_active: true,
        is_verified: true,
        role: 'user',
        created_at: new Date().toISOString(),
      },
      message: 'Authentication successful',
      csrf_token: 'csrf123',
    })

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Email Address/i), {
      target: { value: 'tester@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'Password123!' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }))

    await waitFor(() => {
      expect(api.login).toHaveBeenCalledWith({
        email: 'tester@example.com',
        password: 'Password123!',
      })
    })
  })

  it('displays error message on LoginPage when authentication fails', async () => {
    vi.mocked(api.login).mockRejectedValue({
      response: { data: { detail: 'Invalid email address or password.' } },
    })

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText(/Email Address/i), {
      target: { value: 'wrong@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'WrongPassword' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Invalid email address or password/i)
    })
  })

  it('validates password matching on RegisterPage before submitting', async () => {
    render(
      <MemoryRouter initialEntries={['/register']}>
        <AuthProvider>
          <RegisterPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText(/Email Address/i), {
      target: { value: 'newuser@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/^Password/i), {
      target: { value: 'Secret123!' },
    })
    fireEvent.change(screen.getByLabelText(/Confirm Password/i), {
      target: { value: 'Mismatch123!' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Create Account/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Passwords do not match/i)
      expect(api.register).not.toHaveBeenCalled()
    })
  })

  it('submits valid registration on RegisterPage and displays success state', async () => {
    vi.mocked(api.register).mockResolvedValue({
      id: 'new-user-id',
      email: 'success@example.com',
      is_active: true,
      is_verified: false,
      role: 'user',
      created_at: new Date().toISOString(),
    })

    render(
      <MemoryRouter initialEntries={['/register']}>
        <AuthProvider>
          <RegisterPage />
        </AuthProvider>
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText(/Email Address/i), {
      target: { value: 'success@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/^Password/i), {
      target: { value: 'StrongPass123!' },
    })
    fireEvent.change(screen.getByLabelText(/Confirm Password/i), {
      target: { value: 'StrongPass123!' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Create Account/i }))

    await waitFor(() => {
      expect(api.register).toHaveBeenCalledWith({
        email: 'success@example.com',
        password: 'StrongPass123!',
      })
      expect(screen.getByText('Account Created!')).toBeInTheDocument()
    })
  })

  it('verifies token on VerifyEmailPage from URL search params', async () => {
    vi.mocked(api.verifyEmail).mockResolvedValue({
      message: 'Your email address has been verified successfully!',
      success: true,
    })

    render(
      <MemoryRouter initialEntries={['/verify-email?token=valid-tok-123']}>
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(api.verifyEmail).toHaveBeenCalledWith({ token: 'valid-tok-123' })
      expect(screen.getByText('Email Verified!')).toBeInTheDocument()
    })
  })

  it('submits email on ForgotPasswordPage and displays confirmation', async () => {
    vi.mocked(api.forgotPassword).mockResolvedValue({
      message: 'If an account exists with this email address, password reset instructions have been sent.',
      success: true,
    })

    render(
      <MemoryRouter initialEntries={['/forgot-password']}>
        <ForgotPasswordPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText(/Account Email/i), {
      target: { value: 'forgot@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Send Reset Instructions/i }))

    await waitFor(() => {
      expect(api.forgotPassword).toHaveBeenCalledWith({ email: 'forgot@example.com' })
      expect(screen.getByText('Instructions Sent')).toBeInTheDocument()
    })
  })

  it('resets password on ResetPasswordPage', async () => {
    vi.mocked(api.resetPassword).mockResolvedValue({
      message: 'Password reset successfully.',
      success: true,
    })

    render(
      <MemoryRouter initialEntries={['/reset-password?token=reset-tok-456']}>
        <ResetPasswordPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText(/^New Password/i), {
      target: { value: 'NewSuperPass123!' },
    })
    fireEvent.change(screen.getByLabelText(/Confirm New Password/i), {
      target: { value: 'NewSuperPass123!' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Reset Password/i }))

    await waitFor(() => {
      expect(api.resetPassword).toHaveBeenCalledWith({
        token: 'reset-tok-456',
        new_password: 'NewSuperPass123!',
      })
      expect(screen.getByText('Password Reset Successful')).toBeInTheDocument()
    })
  })

  it('ProtectedRoute redirects anonymous user to /login', async () => {
    vi.mocked(api.getCurrentUser).mockRejectedValue(new Error('Unauthorized'))

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login Screen</div>} />
            <Route
              path="/protected"
              element={
                <ProtectedRoute>
                  <div>Secret Dashboard</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Login Screen')).toBeInTheDocument()
      expect(screen.queryByText('Secret Dashboard')).not.toBeInTheDocument()
    })
  })

  it('renders user email and logout in Header when user is logged in', async () => {
    vi.mocked(api.getCurrentUser).mockResolvedValue({
      id: 'logged-in-user',
      email: 'doctor@hospital.org',
      is_active: true,
      is_verified: true,
      role: 'user',
      created_at: new Date().toISOString(),
    })

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <Header />
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('doctor@hospital.org')).toBeInTheDocument()
      expect(screen.getByTitle('Sign Out')).toBeInTheDocument()
    })
  })
})
