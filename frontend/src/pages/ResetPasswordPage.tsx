import React, { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Activity, AlertCircle, ArrowRight, CheckCircle2, KeyRound, Lock, ShieldCheck } from 'lucide-react'
import { api } from '../services/api'

export const ResetPasswordPage: React.FC = () => {
  const [searchParams] = useSearchParams()
  const initialToken = searchParams.get('token') || ''
  const [token, setToken] = useState(initialToken)
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSuccess, setIsSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!token) {
      setError('Password reset token is required.')
      return
    }

    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters long.')
      return
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match. Please re-enter.')
      return
    }

    setIsLoading(true)

    try {
      await api.resetPassword({
        token,
        new_password: newPassword,
      })
      setIsSuccess(true)
    } catch (err: unknown) {
      const errObj = err as { response?: { data?: { detail?: string } }; message?: string }
      setError(
        errObj.response?.data?.detail ||
          errObj.message ||
          'Failed to reset password. The token may be expired or already used.',
      )
    } finally {
      setIsLoading(false)
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
        <p className="mt-2 text-sm text-neutral-400">Set New Account Password</p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-neutral-900/90 border border-neutral-800 shadow-2xl rounded-2xl p-8 backdrop-blur-xl">
          {isSuccess ? (
            <div className="text-center py-4 space-y-4">
              <div className="mx-auto w-12 h-12 bg-green-300/10 text-green-300 rounded-full flex items-center justify-center border border-green-300/20">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h2 className="text-xl font-bold text-white">Password Reset Successful</h2>
              <p className="text-sm text-neutral-300 leading-relaxed">
                Your password has been securely updated and all previous sessions have been revoked.
                You can now log in with your new password.
              </p>
              <div className="pt-4">
                <Link
                  to="/login"
                  className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 bg-white hover:bg-neutral-200 text-neutral-950 font-medium rounded-xl transition-all text-sm"
                >
                  <span>Log In With New Password</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          ) : (
            <>
              {error && (
                <div
                  role="alert"
                  className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3 text-red-300 text-sm"
                >
                  <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-red-400" />
                  <span>{error}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label htmlFor="reset-token" className="block text-sm font-medium text-neutral-300 mb-1.5">
                    Reset Token
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-neutral-500">
                      <KeyRound className="h-4 w-4" />
                    </div>
                    <input
                      id="reset-token"
                      type="text"
                      required
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      placeholder="Paste token from email"
                      className="w-full pl-10 pr-4 py-2.5 bg-neutral-950/80 border border-neutral-700/80 rounded-xl text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-neutral-300 transition-all text-sm"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="new-pw" className="block text-sm font-medium text-neutral-300 mb-1.5">
                    New Password (min 8 characters)
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-neutral-500">
                      <Lock className="h-4 w-4" />
                    </div>
                    <input
                      id="new-pw"
                      type="password"
                      required
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-10 pr-4 py-2.5 bg-neutral-950/80 border border-neutral-700/80 rounded-xl text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-neutral-300 transition-all text-sm"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="confirm-new-pw" className="block text-sm font-medium text-neutral-300 mb-1.5">
                    Confirm New Password
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-neutral-500">
                      <ShieldCheck className="h-4 w-4" />
                    </div>
                    <input
                      id="confirm-new-pw"
                      type="password"
                      required
                      autoComplete="new-password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-10 pr-4 py-2.5 bg-neutral-950/80 border border-neutral-700/80 rounded-xl text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-neutral-300 transition-all text-sm"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full mt-2 py-3 px-4 bg-white hover:bg-neutral-200 text-neutral-950 font-medium rounded-xl shadow-lg shadow-black/20 focus:outline-none focus:ring-2 focus:ring-white/70 focus:ring-offset-2 focus:ring-offset-neutral-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-sm"
                >
                  {isLoading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Updating Password...</span>
                    </>
                  ) : (
                    <>
                      <span>Reset Password</span>
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </form>

              <div className="mt-6 pt-6 border-t border-neutral-800 text-center">
                <Link to="/login" className="text-sm font-medium text-neutral-300 hover:text-neutral-200 transition-colors">
                  Return to Login
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
