import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, AlertCircle, ArrowRight, CheckCircle2, Mail } from 'lucide-react'
import { api } from '../services/api'

export const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError(null)
    setMessage(null)

    try {
      const res = await api.forgotPassword({ email })
      setMessage(
        res.message ||
          'If an account exists with this email address, the request has been received. Check your inbox later; if no message arrives, try again later.',
      )
    } catch (err: unknown) {
      const errObj = err as { response?: { data?: { detail?: string } }; message?: string }
      setError(
        errObj.response?.data?.detail ||
          errObj.message ||
          'Failed to submit password reset request.',
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
        <p className="mt-2 text-sm text-neutral-400">Password Recovery</p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-neutral-900/90 border border-neutral-800 shadow-2xl rounded-2xl p-8 backdrop-blur-xl">
          {message ? (
            <div className="text-center py-4 space-y-4">
              <div className="mx-auto w-12 h-12 bg-green-300/10 text-green-300 rounded-full flex items-center justify-center border border-green-300/20">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h2 className="text-xl font-bold text-white">Request Received</h2>
              <p className="text-sm text-neutral-300 leading-relaxed">{message}</p>
              <div className="pt-4 flex flex-col gap-2">
                <Link
                  to="/reset-password"
                  className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 bg-white hover:bg-neutral-200 text-neutral-950 font-medium rounded-xl transition-all text-sm"
                >
                  <span>Enter Reset Token</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  to="/login"
                  className="w-full text-center py-2 text-sm text-neutral-400 hover:text-neutral-300"
                >
                  Return to Login
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

              <p className="text-sm text-neutral-300 mb-6 leading-relaxed">
                Enter your account email address. If an account exists, we'll try to send a single-use password reset link.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label htmlFor="reset-email" className="block text-sm font-medium text-neutral-300 mb-1.5">
                    Account Email
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-neutral-500">
                      <Mail className="h-4 w-4" />
                    </div>
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@company.com"
                      className="w-full pl-10 pr-4 py-2.5 bg-neutral-950/80 border border-neutral-700/80 rounded-xl text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-neutral-300 transition-all text-sm"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-3 px-4 bg-white hover:bg-neutral-200 text-neutral-950 font-medium rounded-xl shadow-lg shadow-black/20 focus:outline-none focus:ring-2 focus:ring-white/70 focus:ring-offset-2 focus:ring-offset-neutral-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-sm"
                >
                  {isLoading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Sending Instructions...</span>
                    </>
                  ) : (
                    <>
                      <span>Send Reset Instructions</span>
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </form>

              <div className="mt-6 pt-6 border-t border-neutral-800 text-center">
                <Link to="/login" className="text-sm font-medium text-neutral-300 hover:text-neutral-200 transition-colors">
                  Remember password? Sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
