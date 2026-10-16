import { describe, it, expect } from 'vitest'
import { apiClient } from '../services/api'

describe('Production API Client Routing & Security Configuration', () => {
  it('defaults to relative same-origin /api/v1 baseURL', () => {
    // Relative baseURL allows Vercel external rewrite to proxy same-origin without CORS complications
    expect(apiClient.defaults.baseURL).toBe('/api/v1')
  })

  it('enforces credentials transmission for HttpOnly cookie authentication', () => {
    // withCredentials ensures dd_session and dd_csrf cookies are transmitted by the browser
    expect(apiClient.defaults.withCredentials).toBe(true)
  })

  it('configures Double-Submit CSRF cookie and header parameters', () => {
    // Axios automatically extracts dd_csrf cookie and sends X-CSRF-Token header on state-changing requests
    expect(apiClient.defaults.xsrfCookieName).toBe('dd_csrf')
    expect(apiClient.defaults.xsrfHeaderName).toBe('X-CSRF-Token')
  })

  it('sets application/json as default Content-Type header', () => {
    expect(apiClient.defaults.headers['Content-Type']).toBe('application/json')
  })
})
