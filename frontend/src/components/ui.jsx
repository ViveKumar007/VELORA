import { useEffect, useRef, useState } from 'react'
import { LogoMark } from './Logo'

/* ==========================================================================
   Primitives

   The rule that shapes this file: a surface has to earn itself. Sections are
   organised with type, space and a single hairline rule — a box is drawn only
   around things that are genuinely objects (a transaction, an agent, a
   decision), never around a statistic or a heading.
   ========================================================================== */

/** A named region. No border, no background — the label and spacing do the work. */
export function Section({ title, description, action, children, className = '' }) {
  return (
    <section className={className}>
      {(title || action) && (
        <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            {title && <h2 className="eyebrow">{title}</h2>}
            {description && (
              <p className="mt-1.5 text-small text-fg-subtle">{description}</p>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

/** For genuine objects only. Use sparingly. */
export function Surface({ children, className = '', interactive = false, tone }) {
  const tones = {
    ok: 'border-[color:var(--color-ok)]/25 bg-[color:var(--color-ok)]/[0.04]',
    warn: 'border-[color:var(--color-warn)]/25 bg-[color:var(--color-warn)]/[0.04]',
    danger: 'border-[color:var(--color-danger)]/25 bg-[color:var(--color-danger)]/[0.04]',
    brand: 'border-brand-500/25 bg-brand-500/[0.05]',
  }
  return (
    <div
      className={`rounded-[var(--radius-md)] border shadow-[var(--shadow-raise)] ${
        tone ? tones[tone] : 'border-ink-800 bg-ink-950'
      } ${
        interactive
          ? 'transition-all duration-[var(--dur-base)] ease-[var(--ease-out-soft)] hover:border-ink-700 hover:bg-ink-900 hover:shadow-[var(--shadow-float)]'
          : ''
      } ${className}`}
    >
      {children}
    </div>
  )
}

/** A number that matters. No box — size and colour carry it. */
export function Figure({ value, label, note, tone = 'default', animate = true }) {
  const tones = {
    default: 'text-fg',
    ok: 'text-[color:var(--color-ok)]',
    warn: 'text-[color:var(--color-warn)]',
    danger: 'text-[color:var(--color-danger)]',
    brand: 'text-brand-300',
  }
  return (
    <div>
      <div className={`tnum text-title font-semibold ${tones[tone]}`}>
        {animate && typeof value === 'number' ? <CountUp value={value} /> : value}
      </div>
      <div className="mt-1 text-small text-fg-muted">{label}</div>
      {note && <div className="mt-0.5 text-label text-fg-faint normal-case">{note}</div>}
    </div>
  )
}

/**
 * Financial values should move, not jump. Seeing 2,480 climb to 3,900 tells
 * you money was spent; a swap tells you the page re-rendered.
 */
export function CountUp({ value, duration = 520 }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  const raf = useRef(null)

  useEffect(() => {
    const start = performance.now()
    const origin = from.current
    const delta = value - origin
    if (delta === 0) return

    // A requestAnimationFrame count cannot be stopped by a CSS media query,
    // so reduced motion has to be honoured here in JS or not at all.
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      from.current = value
      setShown(value)
      return
    }

    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setShown(Math.round(origin + delta * eased))
      if (t < 1) raf.current = requestAnimationFrame(tick)
      else from.current = value
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [value, duration])

  return <>{shown.toLocaleString('en-IN')}</>
}

export function Button({
  children,
  variant = 'default',
  size = 'md',
  className = '',
  ...props
}) {
  const variants = {
    default:
      'border-ink-700 bg-ink-850 text-fg hover:border-ink-600 hover:bg-ink-800',
    primary:
      'border-brand-500 bg-brand-500 text-white hover:bg-brand-400 hover:border-brand-400',
    approve:
      'border-[color:var(--color-ok-dim)] bg-[color:var(--color-ok-dim)] text-[#04140a] hover:brightness-110',
    danger:
      'border-[color:var(--color-danger)]/40 bg-[color:var(--color-danger)]/10 text-[color:var(--color-danger)] hover:bg-[color:var(--color-danger)]/20',
    ghost: 'border-transparent bg-transparent text-fg-muted hover:bg-ink-850 hover:text-fg',
  }
  const sizes = {
    sm: 'px-2.5 py-1 text-label normal-case tracking-normal',
    md: 'px-4 py-2 text-small',
  }
  // `children` is destructured out of props above, so it has to be rendered
  // explicitly. The element was previously self-closing, which meant every
  // button in the product drew as an empty coloured bar with its label
  // silently dropped.
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border
        font-medium transition-all duration-[var(--dur-fast)] ease-[var(--ease-out-soft)]
        active:translate-y-px active:brightness-95
        disabled:cursor-not-allowed disabled:opacity-40 disabled:active:translate-y-0
        ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="eyebrow mb-2 block">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-label text-fg-faint normal-case">{hint}</span>}
    </label>
  )
}

/**
 * The focus ring is deliberately not suppressed. An earlier version set
 * `focus:outline-none` and recoloured the border instead, which made keyboard
 * focus *weaker* than mouse hover — on a screen where you approve payments,
 * not knowing which field you are in is a real failure.
 */
export function Input({ className = '', ...props }) {
  return (
    <input
      className={`w-full rounded-[var(--radius-sm)] border border-[color:var(--color-border-control)]
        bg-ink-900 px-3 py-2 text-body text-fg transition-colors duration-[var(--dur-fast)]
        placeholder:text-fg-faint hover:border-ink-500 focus:border-brand-500 ${className}`}
      {...props}
    />
  )
}

/** State only. Never decoration. */
export function Status({ state, children, className = '' }) {
  const map = {
    ok: 'text-[color:var(--color-ok)]',
    warn: 'text-[color:var(--color-warn)]',
    danger: 'text-[color:var(--color-danger)]',
    brand: 'text-brand-300',
    muted: 'text-fg-subtle',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 text-label ${map[state]} ${className}`}>
      {/* 6px, matching every other node in the interface. At 4px it read as
          dirt on the screen rather than as an indicator. */}
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
      {children}
    </span>
  )
}

export function Badge({ children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-label font-medium
        tracking-normal normal-case ring-1 ring-inset ${className}`}
    >
      {children}
    </span>
  )
}

export function Mono({ children, className = '' }) {
  return (
    <span className={`font-mono text-label tracking-normal normal-case text-fg-faint ${className}`}>
      {children}
    </span>
  )
}

export function Rule({ className = '' }) {
  return <div className={`h-px bg-ink-800 ${className}`} />
}

export function Alert({ kind = 'error', children }) {
  const kinds = {
    error:
      'border-[color:var(--color-danger)]/30 bg-[color:var(--color-danger)]/[0.07] text-[color:var(--color-danger)]',
    warn: 'border-[color:var(--color-warn)]/30 bg-[color:var(--color-warn)]/[0.07] text-[color:var(--color-warn)]',
    info: 'border-brand-500/30 bg-brand-500/[0.07] text-brand-300',
    success:
      'border-[color:var(--color-ok)]/30 bg-[color:var(--color-ok)]/[0.07] text-[color:var(--color-ok)]',
  }
  return <div className={`rounded-lg border px-3.5 py-2.5 text-small ${kinds[kind]}`}>{children}</div>
}

/**
 * Loading, in the language of the mark: the two loops hold still and the
 * decision node pulses. A generic spinner says "wait"; this says "the system
 * is deciding", which is the only thing this product ever makes you wait for.
 */
export function Loading({ label = 'Loading', className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 py-14 ${className}`}>
      <LogoMark size={44} live className="text-brand-500 v-orbit" />
      <span className="eyebrow">{label}</span>
    </div>
  )
}

export function Skeleton({ className = '' }) {
  return <div className={`v-skeleton ${className}`} />
}

/** Empty states use the same node language rather than an icon font. */
export function Empty({ title, hint, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <svg width="52" height="32" viewBox="0 0 100 62" fill="none" className="mb-5 text-ink-700">
        <ellipse cx="26" cy="31" rx="24" ry="20" stroke="currentColor" strokeWidth="2.5" />
        <ellipse cx="62" cy="31" rx="35" ry="29" stroke="currentColor" strokeWidth="2.5" />
        <circle cx="43" cy="31" r="5" fill="currentColor" />
      </svg>
      <p className="text-heading font-medium text-fg-muted">{title}</p>
      {hint && <p className="mt-2 max-w-xs text-small text-fg-faint">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/** Scroll-triggered reveal. Fires once, then stops observing. */
export function Reveal({ children, delay = 0, className = '' }) {
  const ref = useRef(null)
  const [shown, setShown] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true)
          observer.disconnect()
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -60px 0px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} data-shown={shown} style={{ transitionDelay: `${delay}ms` }}
      className={`v-reveal ${className}`}
    >
      {children}
    </div>
  )
}

/* Kept for compatibility with pages not yet migrated off the old card API. */
export function Card({ title, subtitle, right, children, className = '' }) {
  return (
    <Surface className={className}>
      {(title || right) && (
        <header className="flex items-start justify-between gap-4 border-b border-ink-800 px-5 py-3.5">
          <div>
            {title && <h2 className="eyebrow">{title}</h2>}
            {subtitle && <p className="mt-1 text-label text-fg-faint normal-case">{subtitle}</p>}
          </div>
          {right}
        </header>
      )}
      <div className="p-5">{children}</div>
    </Surface>
  )
}

export const Spinner = Loading

export function StateBadge({ state }) {
  const map = {
    BLOCKED: 'danger',
    REJECTED: 'muted',
    EXPIRED: 'muted',
    PENDING_APPROVAL: 'warn',
    APPROVED: 'ok',
    PAYMENT_CREATED: 'brand',
    PAYMENT_CREATION_FAILED: 'warn',
    PAYMENT_SUCCESS: 'ok',
    PAYMENT_FAILED: 'danger',
  }
  return <Status state={map[state] || 'muted'}>{state?.replace(/_/g, ' ').toLowerCase()}</Status>
}

export function DecisionBadge({ decision }) {
  const map = {
    APPROVED: ['ok', 'approved'],
    PENDING_APPROVAL: ['warn', 'needs approval'],
    BLOCKED: ['danger', 'blocked'],
  }
  const entry = map[decision]
  if (!entry) return null
  return <Status state={entry[0]}>{entry[1]}</Status>
}
