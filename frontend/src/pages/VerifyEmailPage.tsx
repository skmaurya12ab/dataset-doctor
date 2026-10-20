import React, { useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Activity, AlertCircle, ArrowRight, CheckCircle2, KeyRound } from 'lucide-react'
import { api } from '../services/api'

export const VerifyEmailPage: React.FC = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const initialToken = searchParams.get('token') || ''
  const navigationState = location.state as { email?: unknown } | null
  const initialEmail = typeof navigationState?.email === 'string' ? navigationState.email : ''
  const [token, setToken] = useState(initialToken)
  const [resendEmail, setResendEmail] = useState(initialEmail)
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState<string | null>(null)
  const [resendMessage, setResendMessage] = useState<string | null>(null)
  const [isResending, setIsResending] = useState(false)
  const verificationRequestInFlight = useRef(false)
  const verificationRequestId = useRef(0)
  const resendRequestInFlight = useRef(false)

  const verify = async (tokenToUse: string) => {
    if (!tokenToUse || verificationRequestInFlight.current) return
    verificationRequestInFlight.current = true
    const requestId = ++verificationRequestId.current
    setStatus('loading')
    setMessage(null)
    try {
      const res = await api.verifyEmail({ token: tokenToUse })
      if (requestId !== verificationRequestId.current) return
      setStatus('success')
      setMessage(res.message || 'Your email address has been verified successfully!')

      if (searchParams.has('token')) {
        const remainingParams = new URLSearchParams(searchParams)
        remainingParams.delete('token')
        const query = remainingParams.toString()
        navigate(
          {
            pathname: location.pathname,
            search: query ? `?${query}` : '',
            hash: location.hash,
          },
          { replace: true, state: location.state },
        )
      }
    } catch (err: unknown) {
      if (requestId !== verificationRequestId.current) return
      setStatus('error')
      const errObj = err as { response?: { data?: { detail?: string } }; message?: string }
      setMessage(
        errObj.response?.data?.detail ||
          errObj.message ||
          'Verification token is invalid, expired, or already used.',
      )
    } finally {
      if (requestId === verificationRequestId.current) {
        verificationRequestInFlight.current = false
      }
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    verify(token)
  }

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (resendRequestInFlight.current) return
    resendRequestInFlight.current = true
    setIsResending(true)
    setResendMessage(null)
    try {
      const res = await api.resendVerification(resendEmail)
      setResendMessage(res.message || 'If an account needs verification, the request has been received. Check your inbox later.')
    } catch (err: unknown) {
      const errObj = err as { response?: { data?: { detail?: string } }; message?: string }
      setResendMessage(
        errObj.response?.data?.detail || errObj.message || 'The request could not be processed. Try again later.',
      )
    } finally {
      resendRequestInFlight.current = false
      setIsResending(false)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-950 flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8 text-neutral-100">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-8">
        <div className="inline-flex items-center justify-center p-3 bg-white/5 rounded-2xl border border-white/10 mb-4 shadow-lg shadow-black/20">
          <Activity className="h-10 w-10 text-neutral-300" />
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-neutral-200 to-neutral-400 bg-clip-text text-transparent">
          Dataset Doctor
        </h1>
        <p className="mt-2 text-sm text-neutral-400">Email Address Verification</p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-neutral-900/90 border border-neutral-800 shadow-2xl rounded-2xl p-8 backdrop-blur-xl">
          {status === 'loading' && (
            <div className="text-center py-6 space-y-4">
              <div className="w-10 h-10 border-4 border-neutral-400 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm text-neutral-300">Verifying your token with Dataset Doctor...</p>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center py-4 space-y-4">
              <div className="mx-auto w-12 h-12 bg-green-300/10 text-green-300 rounded-full flex items-center justify-center border border-green-300/20">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h2 className="text-xl font-bold text-white">Email Verified!</h2>
              <p className="text-sm text-neutral-300 leading-relaxed">{message}</p>
              <div className="pt-4">
                <Link
                  to="/login"
                  className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 bg-white hover:bg-neutral-200 text-neutral-950 font-medium rounded-xl transition-all text-sm"
                >
                  <span>Sign In</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          )}

          {status === 'error' && (
            <div className="space-y-4">
              <div
                role="alert"
                className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3 text-red-300 text-sm"
              >
                <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-red-400" />
                <span>{message}</span>
              </div>
              <p className="text-xs text-neutral-400 text-center">
                This link may have expired or already been used. Request a fresh verification email below.
              </p>
            </div>
          )}

          {initialToken && status === 'idle' && (
            <p className="text-sm text-neutral-300 text-center">
              Your verification link is ready. Select <strong>Verify Email</strong> to confirm this address.
            </p>
          )}

          {(status === 'idle' || status === 'error') && (
            <form onSubmit={handleResend} className="mt-5 border-t border-neutral-800 pt-5 space-y-3">
              <h2 className="text-sm font-semibold text-neutral-200">Resend verification email</h2>
              <p className="text-xs text-neutral-400">
                Enter the email address used to register and we’ll send a new link if verification is still needed.
              </p>
              <div>
                <label htmlFor="resend-email" className="block text-sm font-medium text-neutral-300 mb-1.5">
                  Account Email
                </label>
                <input
                  id="resend-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={resendEmail}
                  onChange={(e) => setResendEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full px-4 py-2.5 bg-neutral-950/80 border border-neutral-700/80 rounded-xl text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-neutral-300 transition-all text-sm"
                />
              </div>
              <button
                type="submit"
                disabled={isResending}
                className="w-full py-2.5 px-4 bg-neutral-800 hover:bg-neutral-700 text-neutral-100 font-medium rounded-xl transition-all text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isResending ? 'Requesting…' : 'Resend Verification Email'}
              </button>
              {resendMessage && (
                <p role="status" className="text-xs text-neutral-300 text-center">{resendMessage}</p>
              )}
            </form>
          )}

          {(status === 'idle' || status === 'error') && (
            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              <div>
                <label htmlFor="token" className="block text-sm font-medium text-neutral-300 mb-1.5">
                  Verification Token
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-neutral-500">
                    <KeyRound className="h-4 w-4" />
                  </div>
                  <input
                    id="token"
                    type="text"
                    required
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="Enter verification token from email"
                    className="w-full pl-10 pr-4 py-2.5 bg-neutral-950/80 border border-neutral-700/80 rounded-xl text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-neutral-300 transition-all text-sm"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-3 px-4 bg-white hover:bg-neutral-200 text-neutral-950 font-medium rounded-xl transition-all text-sm flex items-center justify-center gap-2"
              >
                <span>{initialToken ? 'Verify Email' : 'Verify Token'}</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          )}

          <div className="mt-6 pt-6 border-t border-neutral-800 text-center">
            <Link to="/login" className="text-sm font-medium text-neutral-300 hover:text-neutral-200 transition-colors">
              Return to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
