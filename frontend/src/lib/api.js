/**
 * Thin API client.
 *
 * The agent token lives in localStorage and is sent only on agent-facing
 * calls. That mirrors the backend's trust model: the console acts *as* the
 * agent when it asks permission, and as the user when it approves.
 */

import { clearSession, getSession, setProfile, setSession } from './session'

const TOKEN_KEY = 'velora.agentToken'

/**
 * Operator token for the human-facing API, when the backend has one set
 * (OPERATOR_TOKEN). Supplied at build time via VITE_OPERATOR_TOKEN. Empty in
 * a localhost demo, where the backend leaves the operator surface open.
 */
export const OPERATOR_TOKEN = import.meta.env?.VITE_OPERATOR_TOKEN || ''

export function getAgentToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setAgentToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode: the session still works, it just will not be remembered */
  }
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

/**
 * `auth` selects which credential to present:
 *   'user'     the signed-in buyer   (default for the buyer console)
 *   'merchant' the signed-in seller
 *   'agent'    an agent bearer token
 *   'none'     public endpoints
 */
async function request(method, path, { body, auth = 'user' } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (OPERATOR_TOKEN) headers['X-Velora-Token'] = OPERATOR_TOKEN

  if (auth === 'agent') {
    const token = getAgentToken()
    if (!token) throw new ApiError(401, 'No agent token set. Add one in the Agent Console.')
    headers.Authorization = `Bearer ${token}`
  } else if (auth === 'user' || auth === 'merchant') {
    const token = getSession(auth)
    if (token) headers.Authorization = `Bearer ${token}`
  }

  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const text = await res.text()
  const payload = text ? JSON.parse(text) : null

  if (!res.ok) {
    // A dead session should log you out rather than leave the UI retrying
    // against a token the server has already rejected.
    if (res.status === 401 && (auth === 'user' || auth === 'merchant')) {
      clearSession(auth)
      setProfile(auth, null)
    }
    throw new ApiError(res.status, payload?.detail || res.statusText)
  }
  return payload
}

export const api = {
  health: () => request('GET', '/api/health', { auth: 'none' }),
  config: () => request('GET', '/api/config', { auth: 'none' }),
  dashboard: () => request('GET', '/api/dashboard'),

  products: () => request('GET', '/api/products', { auth: 'none' }),
  merchants: () => request('GET', '/api/merchants', { auth: 'none' }),
  agentCatalog: () => request('GET', '/api/merchants/catalog', { auth: 'none' }),

  agents: () => request('GET', '/api/agents'),
  createAgent: (body) => request('POST', '/api/agents', { body }),
  suspendAgent: (id) => request('POST', `/api/agents/${id}/suspend`, { body: {} }),

  policies: () => request('GET', '/api/policies'),
  createPolicy: (body) => request('POST', '/api/policies', { body }),
  revokePolicy: (id) => request('POST', `/api/policies/${id}/revoke`, { body: {} }),

  transactions: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/api/transactions${qs ? `?${qs}` : ''}`)
  },
  transaction: (id) => request('GET', `/api/transactions/${id}`),
  audit: (id) => request('GET', `/api/transactions/${id}/audit`),

  approvals: () => request('GET', '/api/approvals'),
  approve: (id) => request('POST', `/api/transactions/${id}/approve`, { body: {} }),
  reject: (id, note) => request('POST', `/api/transactions/${id}/reject`, { body: { note } }),

  pay: (id, forceFailure = false) =>
    request('POST', `/api/transactions/${id}/payment`, { body: { force_failure: forceFailure } }),
  simulatePayment: (id, succeed) =>
    request('POST', '/api/webhooks/simulate', { body: { transaction_id: id, succeed } }),
  confirmPayment: (id, result) =>
    request('POST', `/api/transactions/${id}/payment/confirm`, {
      body: {
        razorpay_payment_id: result.razorpay_payment_id,
        razorpay_signature: result.razorpay_signature,
      },
    }),

  // Agent-authenticated calls.
  runAgent: (body) => request('POST', '/api/agent/run', { body, auth: 'agent' }),
  requestPurchase: (body) => request('POST', '/api/agent/request', { body, auth: 'agent' }),

  // --- Auth ---
  login: async (email, password) => {
    const out = await request('POST', '/api/auth/login', {
      body: { email, password },
      auth: 'none',
    })
    setSession('user', out.token)
    setProfile('user', out.user)
    return out.user
  },
  merchantLogin: async (email, password) => {
    const out = await request('POST', '/api/auth/merchant/login', {
      body: { email, password },
      auth: 'none',
    })
    setSession('merchant', out.token)
    setProfile('merchant', out.merchant)
    return out.merchant
  },
  me: () => request('GET', '/api/auth/me'),
  merchantMe: () => request('GET', '/api/auth/merchant/me', { auth: 'merchant' }),
  merchantConsole: () => request('GET', '/api/merchants/me', { auth: 'merchant' }),
}
