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
      <div className="aura pointer-events-none absolute -inset-20 -z-10" />

      {/* One surface, three regions.
          The previous version nested four boxes inside each other, which made
          a single continuous process look like a stack of separate widgets.
          Now only the gate carries a fill — it is the one thing this product
          actually is, and it is where the boldness is spent. */}
      <div className="rounded-[var(--radius-lg)] border border-ink-800 bg-ink-950/80 p-6 shadow-[var(--shadow-float)] backdrop-blur-xl">
        {/* Request */}
        <div className={`transition-opacity duration-500 ${step >= 1 ? 'opacity-100' : 'opacity-35'}`}>
          <div className="flex items-center gap-2">
            <span className="v-live h-1.5 w-1.5 rounded-full bg-brand-400" />
            <span className="eyebrow text-brand-300">Agent request</span>
          </div>
          <div className="mt-3 flex items-baseline justify-between gap-4">
            <span className="min-w-0 truncate text-heading font-medium text-fg">
              {active.product}
            </span>
            <span className="tnum shrink-0 text-title font-semibold tracking-tight text-fg">
              {active.amount}
            </span>
          </div>
          <div className="mt-1 font-mono text-label tracking-normal normal-case text-fg-faint">
            {active.merchant}
          </div>
        </div>

        <Connector active={step >= 1} />

        {/* Gate — a lit band spanning the full card rather than a box nested
            inside it. Nesting put the gate's text on a different left edge
            from the request above it, so the three stages did not line up as
            one column; full bleed puts every stage on the same axis. */}
        <div className="-mx-6 border-y border-brand-500/20 bg-brand-500/[0.055] px-6 py-4">
          <div className="mb-3.5 flex items-center justify-between gap-3">
            <span className="eyebrow text-fg-muted">Authorization engine</span>
            {!decided && step >= 1 && (
              <span className="flex items-center gap-1.5 text-label tracking-normal normal-case text-brand-300">
                <span className="v-live h-1 w-1 rounded-full bg-brand-400" />
                evaluating
              </span>
            )}
          </div>

          {/* Dots and a right-aligned verdict, matching how every other check
              list in the product is set. */}
          <ul className="space-y-2">
            {CHECKS.map((label, i) => {
              const shown = i < visibleChecks
              const failed = active.failAt === i
              return (
                <li key={label}
                  className={`flex items-center gap-2.5 text-small transition-opacity duration-300 ${
                    shown ? 'opacity-100' : 'opacity-25'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${shown ? 'v-seat' : ''} ${
                      !shown
                        ? 'bg-ink-700'
                        : failed
                          ? 'bg-[color:var(--color-danger)]'
                          : 'bg-[color:var(--color-ok)]'
                    }`} style={{ animationDelay: `${i * 40}ms` }}
                  />
                  <span className={failed ? 'text-[color:var(--color-danger)]' : 'text-fg-muted'}>
                    {label}
                  </span>
                  <span
                    className={`ml-auto font-mono text-label ${
                      !shown
                        ? 'text-transparent'
                        : failed
                          ? 'text-[color:var(--color-danger)]'
                          : 'text-[color:var(--color-ok)]/75'
                    }`}
                  >
                    {failed ? 'FAIL' : 'PASS'}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>

        <Connector active={decided} tone={approved ? 'ok' : 'danger'} />

        {/* Verdict — type, not a box. The colour of the word is the state. */}
        <div className={`transition-opacity duration-500 ${decided ? 'opacity-100' : 'opacity-35'}`}>
          {decided ? (
            <div className="v-enter">
              <div className="flex items-baseline justify-between gap-3">
                <span
                  className={`text-title font-semibold tracking-tight ${
                    approved ? 'text-[color:var(--color-ok)]' : 'text-[color:var(--color-danger)]'
                  }`}
                >
                  {active.verdict}
                </span>
              </div>
              <p className="mt-2 text-small leading-relaxed text-fg-muted">{active.reason}</p>
            </div>
          ) : (
            <div className="text-small text-fg-faint">Awaiting decision…</div>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * The connection between two nodes. It draws itself downward when the stage
 * it leads to becomes live, then carries a travelling signal — the mark's own
 * idea, used as the transition between every stage of a decision.
 */
function Connector({ active, tone = 'brand' }) {
  const stroke =
    tone === 'ok'
      ? 'var(--color-ok)'
      : tone === 'danger'
        ? 'var(--color-danger)'
        : 'var(--color-brand-500)'
  // Two things make this read as a connection rather than as a stray tick.
  // It spans the full gap with no padding, so it touches the stage above and
  // the stage below; and it sits on the node axis — the same 3px offset as
  // every status dot in the card — rather than centred in the card, where it
  // ran down the middle of empty space and joined nothing to nothing.
  return (
    <div className="flex h-9" aria-hidden="true">
      <div className="relative ml-[2.5px] w-px">
        <span className="absolute inset-0 bg-ink-800" />
        {active && (
          <span
            className="v-draw absolute inset-0" style={{ background: stroke, opacity: 0.55 }}
          />
        )}
        {/* The travelling signal rides on top of the drawn line. */}
        {active && (
          <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 1 36">
            <line x1="0.5" y1="0" x2="0.5" y2="36"
              stroke={stroke} strokeWidth="1" className="v-flow"
            />
          </svg>
        )}
      </div>
    </div>
  )
}
