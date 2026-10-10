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
          'If an account exists with this email address, password reset instructions have been sent.',
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
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8 text-slate-100">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-8">
        <div className="inline-flex items-center justify-center p-3 bg-indigo-500/10 rounded-2xl border border-indigo-500/20 mb-4 shadow-lg shadow-indigo-500/5">
          <Activity className="h-10 w-10 text-indigo-400" />
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">
          Dataset Doctor
        </h1>
        <p className="mt-2 text-sm text-slate-400">Password Recovery</p>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-slate-900/90 border border-slate-800 shadow-2xl rounded-2xl p-8 backdrop-blur-xl">
          {message ? (
            <div className="text-center py-4 space-y-4">
              <div className="mx-auto w-12 h-12 bg-emerald-500/10 text-emerald-400 rounded-full flex items-center justify-center border border-emerald-500/20">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h2 className="text-xl font-bold text-white">Instructions Sent</h2>
              <p className="text-sm text-slate-300 leading-relaxed">{message}</p>
              <div className="pt-4 flex flex-col gap-2">
                <Link
                  to="/reset-password"
                  className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-xl transition-all text-sm"
                >
                  <span>Enter Reset Token</span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  to="/login"
                  className="w-full text-center py-2 text-sm text-slate-400 hover:text-slate-300"
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
                  className="mb-6 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start gap-3 text-rose-300 text-sm"
                >
                  <AlertCircle className="h-5 w-5 shrink-0 mt-0.5 text-rose-400" />
                  <span>{error}</span>
                </div>
              )}

              <p className="text-sm text-slate-300 mb-6 leading-relaxed">
                Enter your account email address. If an account is associated with this email, we'll dispatch a single-use secure reset token.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label htmlFor="reset-email" className="block text-sm font-medium text-slate-300 mb-1.5">
                    Account Email
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                      <Mail className="h-4 w-4" />
                    </div>
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@company.com"
                      className="w-full pl-10 pr-4 py-2.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all text-sm"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-xl shadow-lg shadow-indigo-600/20 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-sm"
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

              <div className="mt-6 pt-6 border-t border-slate-800 text-center">
                <Link to="/login" className="text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors">
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
