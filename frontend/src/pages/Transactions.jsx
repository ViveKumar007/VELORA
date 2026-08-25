import { useState } from 'react'
import { Link } from 'react-router-dom'
import { DecisionBadge, Empty, Button, Card, Mono, Spinner, StateBadge } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { dateTimeOf } from '../lib/format'

// "Authorized" spans every state that cleared the gate but has not settled.
// Filtering on APPROVED alone emptied the tab as soon as a payment was
// created, which reads as data loss rather than progress.
const FILTERS = [
  { key: 'all', label: 'All', params: {} },
  { key: 'pending', label: 'Needs approval', params: { state: 'PENDING_APPROVAL' } },
  {
    key: 'approved',
    label: 'Authorized',
    params: { state: 'APPROVED,PAYMENT_CREATED,PAYMENT_CREATION_FAILED' },
  },
  { key: 'blocked', label: 'Blocked', params: { state: 'BLOCKED,REJECTED,EXPIRED' } },
  { key: 'paid', label: 'Paid', params: { state: 'PAYMENT_SUCCESS' } },
]

/** Actions available depend on state — the UI mirrors the state machine. */
function RowActions({ txn, reload }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run(fn) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const payable = txn.state === 'APPROVED' || txn.state === 'PAYMENT_CREATION_FAILED'

  return (
    <div className="flex flex-wrap items-center justify-end gap-1.5">
      {error && <span className="text-[10px] text-rose-400">{error}</span>}

      {payable && (
        <>
          <Button size="sm" variant="primary" disabled={busy} onClick={() => run(() => api.pay(txn.id))}>
            Create payment
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            title="Force a provider outage to show the failure path"
            onClick={() => run(() => api.pay(txn.id, true))}
          >
            Fail it
          </Button>
        </>
      )}

      {txn.state === 'PAYMENT_CREATED' && (
        <>
          <Button
            size="sm"
            variant="approve"
            disabled={busy}
            onClick={() => run(() => api.simulatePayment(txn.id, true))}
          >
            Confirm payment
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => run(() => api.simulatePayment(txn.id, false))}
          >
            Decline
          </Button>
        </>
      )}
    </div>
  )
}

export default function Transactions() {
  const [filter, setFilter] = useState(FILTERS[0])
  const { data, loading, reload } = useLiveResource(
    () => api.transactions({ limit: 100, ...filter.params }),
    [filter.key],
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Transactions</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every request an agent made, and what happened to it.
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              filter.key === f.key
                ? 'border-brand-500 bg-brand-500/15 text-brand-400'
                : 'border-ink-700 bg-ink-850 text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <Card>
        {loading && !data ? (
          <Spinner />
        ) : !data?.length ? (
          <Empty icon="○" title="Nothing here" hint="No transactions match this filter." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left">
              <thead>
                <tr className="border-b border-ink-800 text-[11px] text-zinc-600">
                  <th className="pb-2 font-medium">Product</th>
                  <th className="pb-2 font-medium">Amount</th>
                  <th className="pb-2 font-medium">Decision</th>
                  <th className="pb-2 font-medium">State</th>
                  <th className="pb-2 font-medium">Reason</th>
                  <th className="pb-2 font-medium">When</th>
                  <th className="pb-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800/70">
                {data.map(({ transaction: t, amount_display }) => (
                  <tr key={t.id} className="transition hover:bg-ink-850/40">
                    <td className="py-3 pr-3">
                      <Link to={`/audit/${t.id}`} className="block max-w-[220px]">
                        <div className="truncate text-sm font-medium text-zinc-200 hover:text-brand-400">
                          {t.product_name}
                        </div>
                        <Mono>{t.merchant} · {t.category}</Mono>
                      </Link>
                    </td>
                    <td className="tnum py-3 pr-3 text-sm text-zinc-300">{amount_display}</td>
                    <td className="py-3 pr-3">
                      <DecisionBadge decision={t.decision} />
                    </td>
                    <td className="py-3 pr-3">
                      <StateBadge state={t.state} />
                    </td>
                    <td className="py-3 pr-3">
                      <Mono>{t.reason_code}</Mono>
                    </td>
                    <td className="py-3 pr-3">
                      <Mono>{dateTimeOf(t.created_at)}</Mono>
                    </td>
                    <td className="py-3 pl-3">
                      <RowActions txn={t} reload={reload} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
