import React, { StrictMode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
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

const LocationProbe: React.FC = () => {
  const location = useLocation()
  return <output data-testid="current-location">{`${location.pathname}${location.search}`}</output>
}

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

  it('requires confirmation for a URL token and removes it from history after success', async () => {
    vi.mocked(api.verifyEmail).mockResolvedValue({
      message: 'Your email address has been verified successfully!',
      success: true,
    })

    render(
      <MemoryRouter initialEntries={['/verify-email?token=valid-tok-123']}>
        <LocationProbe />
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Your verification link is ready/i)).toBeInTheDocument()
    expect(api.verifyEmail).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Verify Email' }))

    await waitFor(() => {
      expect(api.verifyEmail).toHaveBeenCalledWith({ token: 'valid-tok-123' })
      expect(api.verifyEmail).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Email Verified!')).toBeInTheDocument()
      expect(screen.getByTestId('current-location')).toHaveTextContent('/verify-email')
      expect(screen.getByTestId('current-location')).not.toHaveTextContent('token=')
    })
  })

  it('does not consume a verification token merely by opening its page under StrictMode', async () => {
    vi.mocked(api.verifyEmail).mockResolvedValue({
      message: 'Your email address has been verified successfully!',
      success: true,
    })

    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/verify-email?token=single-use-token']}>
          <LocationProbe />
          <VerifyEmailPage />
        </MemoryRouter>
      </StrictMode>,
    )

    expect(await screen.findByText(/Your verification link is ready/i)).toBeInTheDocument()
    expect(api.verifyEmail).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Verify Email' }))
    expect(await screen.findByText('Email Verified!')).toBeInTheDocument()
    expect(api.verifyEmail).toHaveBeenCalledTimes(1)
  })

  it('keeps manual token entry available when no URL token is provided', async () => {
    vi.mocked(api.verifyEmail).mockResolvedValue({
      message: 'Manual token verified.',
      success: true,
    })

    render(
      <MemoryRouter initialEntries={['/verify-email']}>
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Verify Token' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Verification Token'), {
      target: { value: 'manual-verification-token' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Verify Token' }))

    expect(await screen.findByText('Email Verified!')).toBeInTheDocument()
    expect(api.verifyEmail).toHaveBeenCalledTimes(1)
    expect(api.verifyEmail).toHaveBeenCalledWith({ token: 'manual-verification-token' })
  })

  it('prevents duplicate verification submissions while a request is pending', async () => {
    let resolveVerification: (value: { message: string; success: boolean }) => void = () => {}
    vi.mocked(api.verifyEmail).mockReturnValue(
      new Promise((resolve) => {
        resolveVerification = resolve
      }),
    )

    render(
      <MemoryRouter initialEntries={['/verify-email?token=pending-token']}>
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    const verifyButton = screen.getByRole('button', { name: 'Verify Email' })
    fireEvent.click(verifyButton)
    fireEvent.click(verifyButton)
    expect(api.verifyEmail).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/Verifying your token/i)).toBeInTheDocument()

    resolveVerification({ message: 'Verified.', success: true })
    expect(await screen.findByText('Email Verified!')).toBeInTheDocument()
  })

  it('keeps success visible after a failed verification is retried successfully', async () => {
    vi.mocked(api.verifyEmail)
      .mockRejectedValueOnce({ response: { data: { detail: 'Temporary verification error.' } } })
      .mockResolvedValueOnce({ message: 'Verified on retry.', success: true })

    render(
      <MemoryRouter initialEntries={['/verify-email?token=retry-token']}>
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Verify Email' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporary verification error.')
    fireEvent.click(screen.getByRole('button', { name: 'Verify Email' }))
    expect(await screen.findByText('Email Verified!')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(api.verifyEmail).toHaveBeenCalledTimes(2)
  })

  it('shows resend recovery after an expired link and submits the account email', async () => {
    vi.mocked(api.verifyEmail).mockRejectedValue({
      response: { data: { detail: 'Verification token is invalid or has expired.' } },
    })
    vi.mocked(api.resendVerification).mockResolvedValue({
      message: 'If an account needs verification, the request has been received.',
      success: true,
    })

    render(
      <MemoryRouter initialEntries={['/verify-email?token=expired-token']}>
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    expect(api.verifyEmail).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Verify Email' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/i)
    expect(screen.getByText(/This link may have expired or already been used/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Resend verification email/i })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Account Email'), {
      target: { value: 'recover@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Resend Verification Email/i }))

    await waitFor(() => {
      expect(api.resendVerification).toHaveBeenCalledWith('recover@example.com')
      expect(screen.getByRole('status')).toHaveTextContent(/request has been received/i)
    })
  })

  it('prevents duplicate resend requests while the first request is pending', async () => {
    let resolveResend: (value: { message: string; success: boolean }) => void = () => {}
    vi.mocked(api.resendVerification).mockReturnValue(
      new Promise((resolve) => {
        resolveResend = resolve
      }),
    )

    render(
      <MemoryRouter initialEntries={['/verify-email']}>
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Account Email'), {
      target: { value: 'recover@example.com' },
    })
    const resendButton = screen.getByRole('button', { name: /Resend Verification Email/i })
    fireEvent.click(resendButton)
    fireEvent.click(resendButton)

    expect(api.resendVerification).toHaveBeenCalledTimes(1)
    expect(resendButton).toBeDisabled()

    resolveResend({ message: 'Request received.', success: true })
    expect(await screen.findByRole('status')).toHaveTextContent('Request received.')
  })

  it('prefills the account email and requests a verification resend', async () => {
    vi.mocked(api.resendVerification).mockResolvedValue({
      message: 'If an account needs verification, the request has been received. Check your inbox later.',
      success: true,
    })

    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/verify-email', state: { email: 'resend@example.com' } }]}
      >
        <VerifyEmailPage />
      </MemoryRouter>,
    )

    expect(screen.getByLabelText('Account Email')).toHaveValue('resend@example.com')
    fireEvent.click(screen.getByRole('button', { name: /Resend Verification Email/i }))

    await waitFor(() => {
      expect(api.resendVerification).toHaveBeenCalledWith('resend@example.com')
      expect(screen.getByRole('status')).toHaveTextContent(/request has been received/i)
    })
  })

  it('submits email on ForgotPasswordPage and displays confirmation', async () => {
    vi.mocked(api.forgotPassword).mockResolvedValue({
      message: 'If an account exists with this email address, the request has been received. Check your inbox later; if no message arrives, try again later.',
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
      expect(screen.getByText('Request Received')).toBeInTheDocument()
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
