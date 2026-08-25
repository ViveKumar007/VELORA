import { DECISION_STYLE, STATE_STYLE } from '../lib/format'

export function Card({ title, subtitle, right, children, className = '' }) {
  return (
    <section
      className={`rounded-xl border border-ink-800 bg-ink-900/60 backdrop-blur ${className}`}
    >
      {(title || right) && (
        <header className="flex items-start justify-between gap-4 border-b border-ink-800 px-5 py-3.5">
          <div>
            {title && <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-zinc-500">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function Badge({ children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${className}`}
    >
      {children}
    </span>
  )
}

export function StateBadge({ state }) {
  return <Badge className={STATE_STYLE[state] || STATE_STYLE.CREATED}>{state?.replace(/_/g, ' ')}</Badge>
}

export function DecisionBadge({ decision }) {
  const style = DECISION_STYLE[decision]
  if (!style) return null
  return <Badge className={style.cls}>{style.label}</Badge>
}

export function Button({
  children,
  variant = 'default',
  size = 'md',
  className = '',
  ...props
}) {
  const variants = {
    default: 'bg-ink-800 hover:bg-ink-700 text-zinc-100 border-ink-700',
    primary: 'bg-brand-600 hover:bg-brand-500 text-white border-brand-500',
    approve: 'bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500',
    danger: 'bg-rose-600/90 hover:bg-rose-500 text-white border-rose-500',
    ghost: 'bg-transparent hover:bg-ink-800 text-zinc-300 border-transparent',
  }
  const sizes = { sm: 'px-2.5 py-1 text-xs', md: 'px-3.5 py-1.5 text-sm' }
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition
        disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-zinc-400">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-zinc-600">{hint}</span>}
    </label>
  )
}

export function Input({ className = '', ...props }) {
  return (
    <input
      className={`w-full rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm text-zinc-100
        placeholder:text-zinc-600 focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none ${className}`}
      {...props}
    />
  )
}

export function Stat({ label, value, sub, accent = 'text-zinc-100' }) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/60 px-5 py-4">
      <div className="text-xs font-medium text-zinc-500">{label}</div>
      <div className={`tnum mt-1.5 text-2xl font-semibold ${accent}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-zinc-600">{sub}</div>}
    </div>
  )
}

export function Empty({ icon = '—', title, hint }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-3 text-2xl text-ink-600">{icon}</div>
      <p className="text-sm font-medium text-zinc-400">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-xs text-zinc-600">{hint}</p>}
    </div>
  )
}

export function Mono({ children, className = '' }) {
  return <span className={`font-mono text-[11px] text-zinc-500 ${className}`}>{children}</span>
}

export function Alert({ kind = 'error', children }) {
  const kinds = {
    error: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
    warn: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    info: 'border-brand-500/30 bg-brand-500/10 text-brand-400',
    success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  }
  return (
    <div className={`rounded-lg border px-3.5 py-2.5 text-xs ${kinds[kind]}`}>{children}</div>
  )
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-10">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-ink-700 border-t-brand-500" />
    </div>
  )
}
