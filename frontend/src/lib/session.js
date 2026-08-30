/**
 * Session storage for the two human audiences.
 *
 * Buyer and merchant sessions are kept under separate keys so signing in as
 * one never disturbs the other — you can have both consoles open in the same
 * browser, which is exactly what a demo needs.
 *
 * The tokens are signed server-side and carry the audience they were minted
 * for, so a merchant token pasted into the buyer console is refused by the
 * API regardless of what this module does.
 */

const KEYS = {
  user: 'velora.session.user',
  merchant: 'velora.session.merchant',
}

function read(key) {
  try {
    return localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}

function write(key, value) {
  try {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  } catch {
    /* private mode: the session works, it just is not remembered */
  }
}

export const getSession = (kind) => read(KEYS[kind])
export const setSession = (kind, token) => write(KEYS[kind], token)
export const clearSession = (kind) => write(KEYS[kind], '')

/** Cached profile, so a reload does not flash an empty header. */
export function getProfile(kind) {
  try {
    const raw = localStorage.getItem(`${KEYS[kind]}.profile`)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setProfile(kind, profile) {
  try {
    if (profile) localStorage.setItem(`${KEYS[kind]}.profile`, JSON.stringify(profile))
    else localStorage.removeItem(`${KEYS[kind]}.profile`)
  } catch {
    /* ignore */
  }
}
