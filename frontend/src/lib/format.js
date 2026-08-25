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
  APPROVED: { label: 'Approved', cls: 'text-emerald-300 bg-emerald-500/10 ring-emerald-500/30' },
  PENDING_APPROVAL: { label: 'Needs approval', cls: 'text-amber-300 bg-amber-500/10 ring-amber-500/30' },
  BLOCKED: { label: 'Blocked', cls: 'text-rose-300 bg-rose-500/10 ring-rose-500/30' },
}

export const STATE_STYLE = {
  CREATED: 'text-zinc-400 bg-zinc-500/10 ring-zinc-500/30',
  EVALUATING: 'text-zinc-300 bg-zinc-500/10 ring-zinc-500/30',
  BLOCKED: 'text-rose-300 bg-rose-500/10 ring-rose-500/30',
  PENDING_APPROVAL: 'text-amber-300 bg-amber-500/10 ring-amber-500/30',
  APPROVED: 'text-emerald-300 bg-emerald-500/10 ring-emerald-500/30',
  REJECTED: 'text-zinc-300 bg-zinc-500/10 ring-zinc-500/30',
  EXPIRED: 'text-zinc-400 bg-zinc-500/10 ring-zinc-500/30',
  PAYMENT_CREATED: 'text-sky-300 bg-sky-500/10 ring-sky-500/30',
  PAYMENT_CREATION_FAILED: 'text-orange-300 bg-orange-500/10 ring-orange-500/30',
  PAYMENT_SUCCESS: 'text-emerald-200 bg-emerald-500/15 ring-emerald-400/40',
  PAYMENT_FAILED: 'text-rose-300 bg-rose-500/10 ring-rose-500/30',
}

export const CHECK_STYLE = {
  PASS: { dot: 'bg-emerald-400', text: 'text-emerald-300', label: 'PASS' },
  FAIL: { dot: 'bg-rose-400', text: 'text-rose-300', label: 'FAIL' },
  REVIEW: { dot: 'bg-amber-400', text: 'text-amber-300', label: 'REVIEW' },
  SKIP: { dot: 'bg-ink-600', text: 'text-zinc-500', label: 'SKIP' },
}
