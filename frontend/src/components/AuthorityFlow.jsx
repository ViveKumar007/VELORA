import { Mono } from './ui'

/**
 * The authorization flow, read top to bottom.
 *
 * Built from type, alignment and a single connecting line rather than a stack
 * of cards — a decision is one continuous thing, and boxing each step would
 * break it into five unrelated facts.
 *
 * Every value shown here comes from a real evaluated transaction. Nothing is
 * illustrative.
 */

const TONE = {
  pass: {
    dot: 'bg-[color:var(--color-ok)]',
    line: 'bg-[color:var(--color-ok)]/30',
    value: 'text-fg',
  },
  review: {
    dot: 'bg-[color:var(--color-warn)]',
    line: 'bg-[color:var(--color-warn)]/30',
    value: 'text-[color:var(--color-warn)]',
  },
  fail: {
    dot: 'bg-[color:var(--color-danger)]',
    line: 'bg-ink-700',
    value: 'text-[color:var(--color-danger)]',
  },
  idle: { dot: 'bg-ink-600', line: 'bg-ink-800', value: 'text-fg-faint' },
}

function toneFor(status) {
  if (status === 'PASS') return 'pass'
  if (status === 'REVIEW') return 'review'
  if (status === 'FAIL') return 'fail'
  return 'idle'
}

/**
 * One resolved check.
 *
 * The connector to the next step draws downward as this one settles, so the
 * eye is pulled through the evaluation in the order it actually happened
 * rather than being handed a finished list. The node seats itself at the same
 * moment — that pairing is what makes the sequence read as a mechanism
 * working rather than as content appearing.
 */
export function FlowStep({ label, value, status = 'PASS', last = false, index = 0 }) {
  const tone = TONE[toneFor(status)]
  const delay = `${index * 60}ms`
  return (
    <li
      className="v-resolve group relative flex gap-4 pb-5 last:pb-0" style={{ animationDelay: delay }}
    >
      {!last && (
        <span
          aria-hidden
          className={`v-draw absolute top-3 bottom-0 left-[3px] w-px ${tone.line}`} style={{ animationDelay: delay }}
        />
      )}
      <span
        aria-hidden
        className={`v-seat relative mt-1.5 h-[7px] w-[7px] shrink-0 rounded-full ${tone.dot}`} style={{ animationDelay: delay }}
      />
      {/* The check's name is set in its own sentence case and the verdict in
          mono caps. Setting both in caps put two shouting columns next to
          each other and made a thirteen-row checklist markedly harder to
          scan than it needed to be. */}
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
        <span className="text-small text-fg-muted transition-colors duration-[var(--dur-fast)] group-hover:text-fg">
          {label}
        </span>
        <span className={`tnum font-mono text-label ${tone.value}`}>{value}</span>
      </div>
    </li>
  )
}

/**
 * The centrepiece: one transaction's full evaluation.
 * `checks` is the decision object the gate returned.
 */
export default function AuthorityFlow({ txn, amountDisplay }) {
  if (!txn) return null

  const checks = (txn.checks || []).filter((c) => c.status !== 'SKIP')
  const decided = Boolean(txn.decision)
  const blocked = txn.decision === 'BLOCKED'
  const pending = txn.decision === 'PENDING_APPROVAL'

  const verdictTone = blocked
    ? 'text-[color:var(--color-danger)]'
    : pending
      ? 'text-[color:var(--color-warn)]'
      : 'text-[color:var(--color-ok)]'

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-heading font-medium text-fg">{txn.product_name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <Mono>{txn.merchant}</Mono>
            <span className="text-ink-600">·</span>
            <Mono>{txn.category}</Mono>
          </div>
        </div>
        <div className="tnum text-title font-semibold text-fg">
          {amountDisplay}
        </div>
      </div>

      <ol className="mb-6">
        {checks.map((check, i) => (
          <FlowStep key={check.name} index={i} label={check.name} value={check.status} status={check.status} last={i === checks.length - 1}
          />
        ))}
      </ol>

      {decided && (
        <div className="v-resolve border-t border-ink-800 pt-5" style={{ animationDelay: '340ms' }}>
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <span className="eyebrow">Decision</span>
            <Mono>{txn.reason_code}</Mono>
          </div>
          <div className={`mt-2 text-title font-semibold tracking-tight ${verdictTone}`}>
            {blocked ? 'Blocked' : pending ? 'Approval required' : 'Authorized'}
          </div>
          <p className="mt-2 max-w-lg text-small leading-relaxed text-fg-muted">
            {txn.explanation}
          </p>
        </div>
      )}
    </div>
  )
}
