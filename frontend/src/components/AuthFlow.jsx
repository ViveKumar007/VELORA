import { useEffect, useState } from 'react'

/**
 * The hero visualisation: one purchase moving through the gate.
 *
 * It loops through the real decision sequence — request, the checks, a
 * verdict — because the sequence *is* the product. Every third pass ends in
 * a refusal rather than an approval, since a gate that only ever says yes
 * demonstrates nothing.
 *
 * Timing is slow on purpose. This is meant to be readable over someone's
 * shoulder at a demo table, not to look busy.
 */

const CHECKS = [
  'Agent identity',
  'Merchant allowed',
  'Category allowed',
  'Amount within limit',
  'Budget available',
]

const SCENARIOS = [
  {
    product: 'SoundBeat Pro',
    merchant: 'DemoStore',
    amount: '₹1,799',
    failAt: null,
    verdict: 'APPROVED',
    reason: 'Within your authorized scope.',
  },
  {
    product: 'Premium Audio Max',
    merchant: 'DemoStore',
    amount: '₹2,499',
    failAt: 3,
    verdict: 'BLOCKED',
    reason: '₹2,499 exceeds your ₹2,000 limit.',
  },
]

export default function AuthFlow() {
  const [scenario, setScenario] = useState(0)
  const [step, setStep] = useState(0)

  useEffect(() => {
    const total = CHECKS.length + 3
    const id = setTimeout(
      () => {
        if (step >= total) {
          setStep(0)
          setScenario((s) => (s + 1) % SCENARIOS.length)
        } else {
          setStep((s) => s + 1)
        }
      },
      step === 0 ? 900 : step > CHECKS.length ? 2200 : 520,
    )
    return () => clearTimeout(id)
  }, [step])

  const active = SCENARIOS[scenario]
  const visibleChecks = Math.max(0, Math.min(step - 1, CHECKS.length))
  const decided = step > CHECKS.length
  const approved = active.verdict === 'APPROVED'

  return (
    <div className="relative mx-auto w-full max-w-md">
      <div className="aura pointer-events-none absolute -inset-16 -z-10" />

      <div className="rounded-2xl border border-ink-800 bg-ink-900/70 p-5 backdrop-blur-xl">
        {/* Request */}
        <div
          className={`rounded-xl border border-ink-800 bg-ink-850/60 p-4 transition-opacity duration-500 ${
            step >= 1 ? 'opacity-100' : 'opacity-40'
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-400 v-live" />
            <span className="text-label tracking-normal normal-case font-semibold tracking-widest text-brand-300 uppercase">
              Agent request
            </span>
          </div>
          <div className="mt-2.5 flex items-baseline justify-between gap-3">
            <span className="truncate text-small font-medium text-fg">
              {active.product}
            </span>
            <span className="tnum shrink-0 text-heading font-semibold text-fg">
              {active.amount}
            </span>
          </div>
          <div className="mt-0.5 text-label tracking-normal normal-case text-fg-subtle">{active.merchant}</div>
        </div>

        <Connector active={step >= 1} />

        {/* Gate */}
        <div className="rounded-xl border border-brand-500/25 bg-brand-500/[0.05] p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-label tracking-normal normal-case font-semibold tracking-widest text-fg-muted uppercase">
              Authorization engine
            </span>
            {!decided && step >= 1 && (
              <span className="text-label tracking-normal normal-case text-brand-300">evaluating…</span>
            )}
          </div>

          <ul className="space-y-1.5">
            {CHECKS.map((label, i) => {
              const shown = i < visibleChecks
              const failed = active.failAt === i
              return (
                <li key={label}
                  className={`flex items-center gap-2.5 text-small ${
                    shown ? 'v-resolve' : 'opacity-0'
                  }`} style={{ animationDelay: `${i * 40}ms` }}
                >
                  <span
                    className={`grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] font-bold ${
                      !shown
                        ? 'bg-ink-800 text-transparent'
                        : failed
                          ? 'bg-[color:var(--color-danger)]/20 text-[color:var(--color-danger)] ring-1 ring-[color:var(--color-danger)]/40'
                          : 'bg-[color:var(--color-ok)]/15 text-[color:var(--color-ok)] ring-1 ring-[color:var(--color-ok)]/30'
                    }`}
                  >
                    {failed ? '✕' : '✓'}
                  </span>
                  <span className={failed ? 'text-[color:var(--color-danger)]' : 'text-fg-muted'}>
                    {label}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>

        <Connector active={decided} tone={approved ? 'emerald' : 'rose'} />

        {/* Verdict */}
        <div
          className={`rounded-xl border p-4 transition-all duration-500 ${
            !decided
              ? 'border-ink-800 bg-ink-850/40 opacity-40'
              : approved
                ? 'border-[color:var(--color-ok)]/30 bg-[color:var(--color-ok)]/[0.07]'
                : 'border-[color:var(--color-danger)]/30 bg-[color:var(--color-danger)]/[0.07]'
          }`}
        >
          {decided ? (
            <div className="v-enter">
              <div
                className={`text-body font-semibold tracking-tight ${
                  approved ? 'text-[color:var(--color-ok)]' : 'text-[color:var(--color-danger)]'
                }`}
              >
                {active.verdict}
              </div>
              <p className="mt-1 text-small leading-relaxed text-fg-muted">{active.reason}</p>
            </div>
          ) : (
            <div className="text-small text-fg-faint">Awaiting decision…</div>
          )}
        </div>
      </div>
    </div>
  )
}

function Connector({ active, tone = 'brand' }) {
  const stroke =
    tone === 'emerald' ? '#34d399' : tone === 'rose' ? '#fb7185' : '#6d5ef0'
  return (
    <div className="flex h-7 justify-center">
      <svg width="2" height="28" viewBox="0 0 2 28" aria-hidden="true">
        <line
          x1="1"
          y1="0"
          x2="1"
          y2="28" stroke={active ? stroke : '#212533'}
          strokeWidth="2"
          className={active ? 'v-flow' : ''} opacity={active ? 0.9 : 1}
        />
      </svg>
    </div>
  )
}
