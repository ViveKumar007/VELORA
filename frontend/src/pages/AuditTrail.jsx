import { Link, useParams } from 'react-router-dom'
import { DecisionPanel } from '../components/Decision'
import { Alert, Badge, Card, Mono, Spinner } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { timeOf } from '../lib/format'

/** Each event type gets a colour so the shape of a trail reads at a glance. */
const EVENT_TONE = {
  REQUEST_RECEIVED: 'bg-brand-500',
  EVALUATION_STARTED: 'bg-brand-500',
  CHECK_EVALUATED: 'bg-ink-600',
  DECISION_MADE: 'bg-brand-400',
  BUDGET_RESERVED: 'bg-amber-500',
  BUDGET_RELEASED: 'bg-amber-500',
  HUMAN_APPROVED: 'bg-emerald-500',
  HUMAN_REJECTED: 'bg-rose-500',
  APPROVAL_EXPIRED: 'bg-zinc-500',
  PAYMENT_CREATED: 'bg-sky-500',
  PAYMENT_CREATION_FAILED: 'bg-orange-500',
  PAYMENT_SUCCEEDED: 'bg-emerald-400',
  PAYMENT_FAILED: 'bg-rose-500',
  DUPLICATE_SUPPRESSED: 'bg-zinc-600',
  STATE_CHANGED: 'bg-ink-600',
}

const CHECK_TONE = {
  PASS: 'bg-emerald-500/70',
  FAIL: 'bg-rose-500',
  REVIEW: 'bg-amber-500',
}

function Entry({ entry, last }) {
  const isCheck = entry.event_type === 'CHECK_EVALUATED'
  const tone = isCheck
    ? CHECK_TONE[entry.decision] || 'bg-ink-600'
    : EVENT_TONE[entry.event_type] || 'bg-ink-600'

  return (
    <li className="relative flex gap-4 pb-4">
      {!last && <span className="absolute left-[5px] top-4 h-full w-px bg-ink-800" />}
      <span className={`relative mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${tone}`} />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <span
            className={`font-mono text-[11px] font-medium ${
              isCheck ? 'text-zinc-500' : 'text-zinc-300'
            }`}
          >
            {entry.event_type}
          </span>
          <Mono>{timeOf(entry.created_at)}</Mono>
          {entry.previous_state && entry.new_state && entry.previous_state !== entry.new_state && (
            <Badge className="bg-ink-800 font-mono text-zinc-500 ring-ink-700">
              {entry.previous_state} → {entry.new_state}
            </Badge>
          )}
          {entry.actor !== 'system' && (
            <Badge className="bg-ink-800 text-zinc-500 ring-ink-700">by {entry.actor}</Badge>
          )}
        </div>

        <p
          className={`mt-1 text-xs leading-relaxed ${
            isCheck ? 'text-zinc-500' : 'text-zinc-300'
          }`}
        >
          {entry.explanation}
        </p>

        <div className="mt-1 flex items-center gap-2">
          <Mono className="text-[10px] text-zinc-700">
            #{entry.seq} · {entry.entry_hash.slice(0, 12)}
          </Mono>
        </div>
      </div>
    </li>
  )
}

export default function AuditTrail() {
  const { id } = useParams()
  const { data: trail, loading, error } = useLiveResource(() => api.audit(id), [id])
  const { data: txnView } = useLiveResource(() => api.transaction(id), [id])

  if (loading && !trail) return <Spinner />
  if (error) return <Alert>{error.message}</Alert>

  const integrity = trail?.integrity

  return (
    <div className="space-y-6">
      <div>
        <Link to="/transactions" className="text-[11px] font-medium text-brand-400 hover:text-brand-500">
          ← All transactions
        </Link>
        <h1 className="mt-2 text-xl font-semibold tracking-tight text-zinc-100">Audit Trail</h1>
        <Mono className="mt-0.5 block">{id}</Mono>
      </div>

      {txnView && (
        <DecisionPanel
          txn={txnView.transaction}
          amountDisplay={txnView.amount_display}
          showChecks={false}
        />
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_270px]">
        <Card title="Event timeline" subtitle={`${trail?.entries?.length ?? 0} events, oldest first`}>
          <ol className="mt-1">
            {trail?.entries?.map((entry, i) => (
              <Entry
                key={entry.id}
                entry={entry}
                last={i === trail.entries.length - 1}
              />
            ))}
          </ol>
        </Card>

        <div className="space-y-4">
          <Card title="Integrity">
            {integrity?.valid ? (
              <div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  <span className="text-sm font-medium text-emerald-300">Chain intact</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-zinc-500">
                  All {integrity.entries} entries hash correctly against their predecessor. Any
                  edit to a past entry would break every hash after it.
                </p>
              </div>
            ) : (
              <div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-rose-400" />
                  <span className="text-sm font-medium text-rose-300">Chain broken</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-zinc-500">
                  {integrity?.detail} First mismatch at entry #{integrity?.broken_at_seq}.
                </p>
              </div>
            )}
          </Card>

          {txnView?.transaction?.policy_id && (
            <Card title="Judged against">
              <Mono className="block break-all">{txnView.transaction.policy_id}</Mono>
              <p className="mt-2 text-xs leading-relaxed text-zinc-500">
                The policy was snapshotted at evaluation time, so this record stays accurate even
                if the authorization is edited later.
              </p>
            </Card>
          )}

          {txnView?.transaction?.payment_order_id && (
            <Card title="Payment">
              <dl className="space-y-2 text-xs">
                <div>
                  <dt className="text-zinc-600">Order</dt>
                  <dd className="font-mono break-all text-zinc-300">
                    {txnView.transaction.payment_order_id}
                  </dd>
                </div>
                {txnView.transaction.payment_id && (
                  <div>
                    <dt className="text-zinc-600">Payment</dt>
                    <dd className="font-mono break-all text-zinc-300">
                      {txnView.transaction.payment_id}
                    </dd>
                  </div>
                )}
                {txnView.transaction.payment_error && (
                  <div>
                    <dt className="text-zinc-600">Error</dt>
                    <dd className="text-rose-300">{txnView.transaction.payment_error}</dd>
                  </div>
                )}
              </dl>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
