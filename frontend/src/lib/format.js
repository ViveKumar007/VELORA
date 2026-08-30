/** Display helpers. Paise in, human-readable strings out. */

export function inr(paise) {
  if (paise == null) return '—'
  const rupees = paise / 100
  const formatted = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: rupees % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(rupees)
  return formatted
}

export function timeOf(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function dateTimeOf(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function countdown(iso) {
  if (!iso) return null
  const ms = new Date(iso).getTime() - Date.now()
  if (ms <= 0) return 'expired'
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
}

/** Turn MAX_AMOUNT_EXCEEDED into "Max amount exceeded". */
export function humanCode(code) {
  if (!code) return '—'
  const s = code.replace(/_/g, ' ').toLowerCase()
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export const DECISION_STYLE = {
  APPROVED: { label: 'Approved', tone: 'ok' },
  PENDING_APPROVAL: { label: 'Needs approval', tone: 'warn' },
  BLOCKED: { label: 'Blocked', tone: 'danger' },
}

export const STATE_STYLE = {
  CREATED: 'muted',
  EVALUATING: 'muted',
  BLOCKED: 'danger',
  PENDING_APPROVAL: 'warn',
  APPROVED: 'ok',
  REJECTED: 'muted',
  EXPIRED: 'muted',
  PAYMENT_CREATED: 'brand',
  PAYMENT_CREATION_FAILED: 'warn',
  PAYMENT_SUCCESS: 'ok',
  PAYMENT_FAILED: 'danger',
}

export const CHECK_STYLE = {
  PASS: { dot: 'bg-[color:var(--color-ok)]', text: 'text-[color:var(--color-ok)]', label: 'PASS' },
  FAIL: { dot: 'bg-[color:var(--color-danger)]', text: 'text-[color:var(--color-danger)]', label: 'FAIL' },
  REVIEW: { dot: 'bg-[color:var(--color-warn)]', text: 'text-[color:var(--color-warn)]', label: 'REVIEW' },
  SKIP: { dot: 'bg-ink-600', text: 'text-fg-faint', label: 'SKIP' },
}

/** Numeric rupee value for animated figures (CountUp needs a number). */
export function paise(value) {
  return Math.round((value || 0) / 100)
}
