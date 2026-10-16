import React, { useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { Activity, AlertCircle, ArrowRight, CheckCircle2, KeyRound } from 'lucide-react'
import { api } from '../services/api'

export const VerifyEmailPage: React.FC = () => {
  const location = useLocation()
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

  const verify = async (tokenToUse: string) => {
    if (!tokenToUse) return
    setStatus('loading')
    setMessage(null)
    try {
      const res = await api.verifyEmail({ token: tokenToUse })
      setStatus('success')
      setMessage(res.message || 'Your email address has been verified successfully!')
    } catch (err: unknown) {
      setStatus('error')
      const errObj = err as { response?: { data?: { detail?: string } }; message?: string }
      setMessage(
        errObj.response?.data?.detail ||
          errObj.message ||
          'Verification token is invalid, expired, or already used.',
      )
    }
  }

  useEffect(() => {
    if (initialToken) {
      verify(initialToken)
    }
  }, [initialToken])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    verify(token)
  }

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault()
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
      setIsResending(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8 text-slate-100">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-8">
        <div className="inline-flex items-center justify-center p-3 bg-indigo-500/10 rounded-2xl border border-indigo-500/20 mb-4 shadow-lg shadow-indigo-500/5">
          <Activity className="h-10 w-10 text-indigo-400" />
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">
          Dataset Doctor
        </h1>
        <p className="mt-2 text-sm text-slate-400">Email Address Verification</p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-slate-900/90 border border-slate-800 shadow-2xl rounded-2xl p-8 backdrop-blur-xl">
          {status === 'loading' && (
            <div className="text-center py-6 space-y-4">
              <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm text-slate-300">Verifying your token with Dataset Doctor...</p>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center py-4 space-y-4">
              <div className="mx-auto w-12 h-12 bg-emerald-500/10 text-emerald-400 rounded-full flex items-center justify-center border border-emerald-500/20">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h2 className="text-xl font-bold text-white">Email Verified!</h2>
              <p className="text-sm text-slate-300 leading-relaxed">{message}</p>
              <div className="pt-4">
                <Link
                  to="/login"
                  className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-xl transition-all text-sm"
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
                className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start gap-3 text-rose-300 text-sm"
              >
                <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-rose-400" />
                <span>{message}</span>
              </div>
              <p className="text-xs text-slate-400 text-center">
                Enter a token manually below or request a new verification email.
              </p>
            </div>
          )}

          {(status === 'idle' || status === 'error') && (
            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              <div>
                <label htmlFor="token" className="block text-sm font-medium text-slate-300 mb-1.5">
                  Verification Token
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                    <KeyRound className="h-4 w-4" />
                  </div>
                  <input
                    id="token"
                    type="text"
                    required
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="Enter verification token from email"
                    className="w-full pl-10 pr-4 py-2.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all text-sm"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-xl transition-all text-sm flex items-center justify-center gap-2"
              >
                <span>Verify Token</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          )}

          {status !== 'success' && (
            <form onSubmit={handleResend} className="mt-6 border-t border-slate-800 pt-5 space-y-3">
              <h2 className="text-sm font-semibold text-slate-200">Need a new verification email?</h2>
              <div>
                <label htmlFor="resend-email" className="block text-sm font-medium text-slate-300 mb-1.5">
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
                  className="w-full px-4 py-2.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all text-sm"
                />
              </div>
              <button
                type="submit"
                disabled={isResending}
                className="w-full py-2.5 px-4 bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium rounded-xl transition-all text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isResending ? 'Requesting…' : 'Resend Verification Email'}
              </button>
              {resendMessage && (
                <p role="status" className="text-xs text-slate-300 text-center">{resendMessage}</p>
              )}
            </form>
          )}

          <div className="mt-6 pt-6 border-t border-slate-800 text-center">
            <Link to="/login" className="text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors">
              Return to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
