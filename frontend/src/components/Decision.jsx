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
            <li
              key={`${check.name}-${i}`}
              className={`flex items-start gap-3 rounded-lg px-2.5 ${
                dense ? 'py-1.5' : 'py-2'
              } ${check.status !== 'PASS' ? 'bg-ink-850/70' : ''}`}
            >
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-xs font-medium text-zinc-200">{check.name}</span>
                  <span className={`text-[10px] font-semibold tracking-wide ${style.text}`}>
                    {style.label}
                  </span>
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-zinc-500">{check.detail}</p>
              </div>
            </li>
          )
        })}
      </ul>
      {skipped > 0 && (
        <p className="mt-2 px-2.5 text-[11px] text-zinc-600">
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
        : 'border-emerald-500/25 bg-emerald-500/[0.04]'

  return (
    <div className={`animate-in rounded-xl border ${tone}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-800/80 px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-zinc-100">{txn.product_name}</span>
            <span className="tnum text-sm text-zinc-400">
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
          <Badge className="bg-ink-800 font-mono text-zinc-400 ring-ink-700">
            {txn.reason_code}
          </Badge>
          <span className="text-[11px] text-zinc-600">{humanCode(txn.reason_code)}</span>
        </div>
        <p className="text-sm leading-relaxed text-zinc-300">{txn.explanation}</p>

        {txn.agent_rationale && (
          <p className="mt-3 border-l-2 border-ink-700 pl-3 text-xs italic leading-relaxed text-zinc-500">
            Agent reasoning: {txn.agent_rationale}
          </p>
        )}
      </div>

      {showChecks && txn.checks?.length > 0 && (
        <div className="border-t border-ink-800/80 px-2 py-2">
          <p className="px-2.5 pb-1 pt-1 text-[11px] font-medium tracking-wide text-zinc-600 uppercase">
            Policy checks
          </p>
          <ChecksList checks={txn.checks} dense />
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-800/80 px-4 py-2.5">
        <Link
          to={`/audit/${txn.id}`}
          className="text-[11px] font-medium text-brand-400 hover:text-brand-500"
        >
          View audit trail →
        </Link>
        {footer}
      </div>
    </div>
  )
}
