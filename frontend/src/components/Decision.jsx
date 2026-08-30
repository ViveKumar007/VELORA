import { Link } from 'react-router-dom'
import { CHECK_STYLE, humanCode, inr } from '../lib/format'
import { Badge, DecisionBadge, Mono, StateBadge } from './ui'

/**
 * The explainable decision object, rendered.
 *
 * Every check is shown, including the ones that passed. Seeing eleven green
 * rows and one red one is what makes a refusal feel like a rule rather than
 * a rejection.
 */
export function ChecksList({ checks = [], dense = false }) {
  const shown = checks.filter((c) => c.status !== 'SKIP')
  const skipped = checks.length - shown.length

  return (
    <div>
      <ul className="space-y-0.5">
        {shown.map((check, i) => {
          const style = CHECK_STYLE[check.status] || CHECK_STYLE.SKIP
          return (
            <li key={`${check.name}-${i}`}
              className={`flex items-start gap-3 rounded-lg px-2.5 ${
                dense ? 'py-1.5' : 'py-2'
              } ${check.status !== 'PASS' ? 'bg-ink-850/70' : ''}`}
            >
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-small font-medium text-fg">{check.name}</span>
                  <span className={`text-label tracking-normal normal-case font-semibold tracking-wide ${style.text}`}>
                    {style.label}
                  </span>
                </div>
                <p className="mt-0.5 text-small leading-relaxed text-fg-subtle">{check.detail}</p>
              </div>
            </li>
          )
        })}
      </ul>
      {skipped > 0 && (
        <p className="mt-2 px-2.5 text-label tracking-normal normal-case text-fg-faint">
          {skipped} check{skipped === 1 ? '' : 's'} skipped — no authorization to evaluate against.
        </p>
      )}
    </div>
  )
}

export function DecisionPanel({ txn, amountDisplay, showChecks = true, footer }) {
  if (!txn) return null

  const tone =
    txn.decision === 'BLOCKED'
      ? 'border-rose-500/25 bg-rose-500/[0.04]'
      : txn.decision === 'PENDING_APPROVAL'
        ? 'border-amber-500/25 bg-amber-500/[0.04]'
        : 'border-[color:var(--color-ok)]/25 bg-emerald-500/[0.04]'

  return (
    <div className={`v-enter rounded-xl border ${tone}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-800/80 px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-small font-semibold text-fg">{txn.product_name}</span>
            <span className="tnum text-small text-fg-muted">
              {amountDisplay || inr(txn.requested_amount_paise)}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Mono>{txn.merchant}</Mono>
            <Mono>·</Mono>
            <Mono>{txn.category}</Mono>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DecisionBadge decision={txn.decision} />
          <StateBadge state={txn.state} />
        </div>
      </div>

      <div className="px-4 py-3">
        <div className="mb-2 flex items-center gap-2">
          <Badge className="bg-ink-800 font-mono text-fg-muted ring-ink-700">
            {txn.reason_code}
          </Badge>
          <span className="text-label tracking-normal normal-case text-fg-faint">{humanCode(txn.reason_code)}</span>
        </div>
        <p className="text-small leading-relaxed text-fg-muted">{txn.explanation}</p>

        {txn.agent_rationale && (
          <p className="mt-3 border-l-2 border-ink-700 pl-3 text-small italic leading-relaxed text-fg-subtle">
            Agent reasoning: {txn.agent_rationale}
          </p>
        )}

        {/* A refusal that keeps the sale. The alternative has already been run
            through the same policy, so it is an offer the buyer can act on
            rather than another thing to be told no about. */}
        {txn.recovery && (
          <div className="mt-3 rounded-lg border border-[color:var(--color-ok)]/30 bg-[color:var(--color-ok)]/[0.06] p-3">
            <div className="mb-1.5 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--color-ok)]" />
              <span className="text-label tracking-normal normal-case font-semibold tracking-wide text-[color:var(--color-ok)] uppercase">
                In-policy alternative
              </span>
            </div>
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-small font-medium text-fg">{txn.recovery.name}</span>
              <span className="tnum text-small text-[color:var(--color-ok)]">
                {txn.recovery.price_display}
              </span>
              <Badge
                className={
                  txn.recovery.would_be === 'APPROVED'
                    ? 'bg-emerald-500/10 text-[color:var(--color-ok)] ring-[color:var(--color-ok)]/30'
                    : 'bg-amber-500/10 text-[color:var(--color-warn)] ring-amber-500/30'
                }
              >
                would be {txn.recovery.would_be === 'APPROVED' ? 'approved' : 'held for approval'}
              </Badge>
            </div>
            <p className="mt-1.5 text-small leading-relaxed text-fg-muted">
              {txn.recovery.explanation}
            </p>
            <p className="mt-1.5 text-label tracking-normal normal-case text-fg-faint">
              Checked against this same authorization before being offered.
            </p>
          </div>
        )}
      </div>

      {showChecks && txn.checks?.length > 0 && (
        <div className="border-t border-ink-800/80 px-2 py-2">
          <p className="px-2.5 pb-1 pt-1 text-label tracking-normal normal-case font-medium tracking-wide text-fg-faint uppercase">
            Policy checks
          </p>
          <ChecksList checks={txn.checks} dense />
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-800/80 px-4 py-2.5">
        <Link to={`/app/audit/${txn.id}`}
          className="text-label tracking-normal normal-case font-medium text-brand-400 hover:text-brand-500"
        >
          View audit trail →
        </Link>
        {footer}
      </div>
    </div>
  )
}
