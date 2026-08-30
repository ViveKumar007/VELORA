import { Mono } from './ui'
import { timeOf } from '../lib/format'

/**
 * A system event stream, not a chat log.
 *
 * Four aligned columns — time, event, context, state — so the eye can scan
 * down any one of them. The newest entry carries full contrast and everything
 * older recedes, which is what makes "what is happening right now" legible at
 * a glance without any element having to shout.
 */

const STATE_TONE = {
  PASS: 'text-[color:var(--color-ok)]',
  APPROVED: 'text-[color:var(--color-ok)]',
  SUCCESS: 'text-[color:var(--color-ok)]',
  REVIEW: 'text-[color:var(--color-warn)]',
  PENDING_APPROVAL: 'text-[color:var(--color-warn)]',
  FAIL: 'text-[color:var(--color-danger)]',
  BLOCKED: 'text-[color:var(--color-danger)]',
}

/** Audit event types read better as sentences than as SCREAMING_SNAKE. */
const EVENT_LABEL = {
  REQUEST_RECEIVED: 'Purchase requested',
  EVALUATION_STARTED: 'Evaluation started',
  CHECK_EVALUATED: 'Policy check',
  DECISION_MADE: 'Decision made',
  RECOVERY_OFFERED: 'Alternative offered',
  BUDGET_RESERVED: 'Budget reserved',
  BUDGET_RELEASED: 'Budget released',
  HUMAN_APPROVED: 'Approved by you',
  HUMAN_REJECTED: 'Rejected by you',
  APPROVAL_EXPIRED: 'Approval expired',
  PAYMENT_CREATED: 'Payment order created',
  PAYMENT_SUCCEEDED: 'Payment confirmed',
  PAYMENT_FAILED: 'Payment failed',
  PAYMENT_CREATION_FAILED: 'Payment could not be created',
  DUPLICATE_SUPPRESSED: 'Duplicate suppressed',
  STATE_CHANGED: 'State changed',
}

export default function ActivityStream({ entries = [], limit = 12, dim = true }) {
  const shown = entries.slice(0, limit)
  if (!shown.length) return null

  return (
    <ol className="divide-y divide-ink-900">
      {shown.map((entry, i) => {
        // Freshness as opacity: the top item is the present, the rest is
        // context. Capped so nothing becomes unreadable.
        const fade = dim ? Math.max(0.4, 1 - i * 0.085) : 1
        const tone = STATE_TONE[entry.decision] || 'text-fg-faint'

        return (
          <li key={entry.id || i}
            className="v-enter grid grid-cols-[auto_1fr] items-baseline gap-x-4 gap-y-1 py-2.5 sm:grid-cols-[auto_1fr_auto]" style={{ opacity: fade, animationDelay: `${Math.min(i, 6) * 30}ms` }}
          >
            <Mono className="tnum">{timeOf(entry.created_at)}</Mono>

            <div className="min-w-0">
              <div className={`text-small ${i === 0 ? 'text-fg' : 'text-fg-muted'}`}>
                {EVENT_LABEL[entry.event_type] || entry.event_type}
              </div>
              {entry.explanation && (
                <div className="mt-0.5 truncate text-label text-fg-faint normal-case tracking-normal">
                  {entry.explanation}
                </div>
              )}
            </div>

            <span className={`text-label tracking-normal normal-case ${tone} sm:text-right`}>
              {entry.decision || ''}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
