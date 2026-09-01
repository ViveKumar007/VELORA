import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Button,
  DecisionBadge,
  Empty,
  Loading,
  Mono,
  Rule,
  StateBadge,
} from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { openCheckout } from '../lib/razorpay'
import { dateTimeOf } from '../lib/format'

/**
 * The ledger.
 *
 * A table, because this is a list of comparable records and a table is the
 * right shape for that. Filters are text with an underline indicator rather
 * than pills — they are navigation, not objects.
 *
 * "Authorized" spans every state that cleared the gate but has not settled;
 * filtering on APPROVED alone emptied the tab the moment a payment was
 * created, which reads as data loss rather than progress.
 */
const FILTERS = [
  { key: 'all', label: 'All', params: {} },
  { key: 'pending', label: 'Needs approval', params: { state: 'PENDING_APPROVAL' } },
  {
    key: 'approved',
    label: 'Authorized',
    params: { state: 'APPROVED,PAYMENT_CREATED,PAYMENT_CREATION_FAILED' },
  },
  { key: 'blocked', label: 'Refused', params: { state: 'BLOCKED,REJECTED,EXPIRED' } },
  { key: 'paid', label: 'Paid', params: { state: 'PAYMENT_SUCCESS' } },
]

export default function Transactions() {
  const [filter, setFilter] = useState(FILTERS[0])
  const { data: config } = useLiveResource(() => api.config(), [], { poll: 0 })
  const { data, loading, reload } = useLiveResource(
    () => api.transactions({ limit: 100, ...filter.params }),
    [filter.key],
  )

  return (
    <div className="v-page space-y-8">
      <header>
        <h1 className="text-title font-semibold tracking-tight text-fg">Transactions</h1>
        <p className="mt-2 max-w-lg text-small text-fg-muted">
          Every request an agent made, and what Velora decided.
        </p>
      </header>

      <nav className="flex flex-wrap gap-6 border-b border-ink-800">
        {FILTERS.map((f) => {
          const active = filter.key === f.key
          return (
            <button key={f.key}
              onClick={() => setFilter(f)}
              className={`relative -mb-px pb-2.5 text-small transition-colors duration-[var(--dur-fast)] ${
                active ? 'text-fg' : 'text-fg-subtle hover:text-fg-muted'
              }`}
            >
              {f.label}
              <span
                className={`absolute inset-x-0 -bottom-px h-px transition-all duration-[var(--dur-base)] ${
                  active ? 'bg-brand-500' : 'bg-transparent'
                }`}
              />
            </button>
          )
        })}
      </nav>

      {loading && !data ? (
        <Loading label="Reading ledger" />
      ) : !data?.length ? (
        <Empty title="Nothing here" hint="No transactions match this filter." />
      ) : (
        <div className="edge-fade -mx-2 overflow-x-auto">
          <table className="w-full min-w-[780px]">
            <thead>
              <tr className="border-b border-ink-800">
                {['Product', 'Amount', 'Decision', 'State', 'Reason', 'When', ''].map((h, i) => (
                  <th key={h || i}
                    className={`eyebrow px-2 pb-2.5 font-medium ${
                      i === 6 ? 'text-right' : 'text-left'
                    }`}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            {/* Rows are generous and reveal on hover: at a glance the ledger
                reads as a block of aligned figures, and the row under the
                cursor lifts out of it without any colour being added. */}
            <tbody className="divide-y divide-ink-900">
              {data.map(({ transaction: t, amount_display }) => (
                <tr key={t.id} className="group transition-colors duration-[var(--dur-fast)] hover:bg-ink-950">
                  <td className="relative px-2 py-3.5">
                    <span
                      aria-hidden
                      className="absolute inset-y-0 left-0 w-px origin-center scale-y-0 bg-brand-500 transition-transform duration-[var(--dur-base)] ease-[var(--ease-out-soft)] group-hover:scale-y-100"
                    />
                    <Link to={`/app/audit/${t.id}`} className="block max-w-[220px]">
                      <div className="truncate text-small text-fg transition-colors duration-[var(--dur-fast)] group-hover:text-brand-300">
                        {t.product_name}
                      </div>
                      <Mono className="mt-0.5 block truncate">
                        {t.merchant} · {t.category}
                      </Mono>
                    </Link>
                  </td>
                  <td className="tnum px-2 py-3.5 text-small font-medium text-fg">{amount_display}</td>
                  <td className="px-2 py-3.5">
                    <DecisionBadge decision={t.decision} />
                  </td>
                  <td className="px-2 py-3.5">
                    <StateBadge state={t.state} />
                  </td>
                  <td className="px-2 py-3.5">
                    <Mono>{t.reason_code}</Mono>
                  </td>
                  <td className="px-2 py-3.5">
                    <Mono className="tnum">{dateTimeOf(t.created_at)}</Mono>
                  </td>
                  <td className="px-2 py-3.5">
                    <RowActions txn={t} reload={reload} config={config} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Rule />
      <p className="max-w-2xl text-label tracking-normal normal-case text-fg-faint">
        A refused transaction has no route to a payment. Blocked, rejected and expired states
        have no outgoing transitions at all.
      </p>
    </div>
  )
}

/** Actions mirror the state machine: you can only do what the lifecycle allows. */
function RowActions({ txn, reload, config }) {
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

  /**
   * Dismissing checkout deliberately does nothing: the transaction stays
   * PAYMENT_CREATED and can be retried or settled by the webhook. Guessing an
   * outcome here would be the one place a browser could talk the backend into
   * a state it did not earn.
   */
  async function payWithRazorpay() {
    setBusy(true)
    setError(null)
    try {
      const result = await openCheckout({
        keyId: config.razorpay_key_id,
        orderId: txn.payment_order_id,
        amountPaise: txn.requested_amount_paise,
        description: txn.product_name,
        methods: config.payment_methods,
      })
      await api.confirmPayment(txn.id, result)
      await reload()
    } catch (err) {
      setError(err.message)
      await reload()
    } finally {
      setBusy(false)
    }
  }

  const live = config?.payment_provider === 'razorpay'
  const payable = txn.state === 'APPROVED' || txn.state === 'PAYMENT_CREATION_FAILED'

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {error && (
        <span className="max-w-[220px] truncate text-label tracking-normal normal-case text-[color:var(--color-danger)]">
          {error}
        </span>
      )}

      {payable && (
        <>
          <Button size="sm" variant="primary" disabled={busy} onClick={() => run(() => api.pay(txn.id))}>
            Create payment
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} title="Force a provider outage to show the failure path"
            onClick={() => run(() => api.pay(txn.id, true))}
          >
            Fail it
          </Button>
        </>
      )}

      {txn.state === 'PAYMENT_CREATED' &&
        (live ? (
          <Button size="sm" variant="approve" disabled={busy} onClick={payWithRazorpay}>
            {busy ? 'Opening…' : 'Pay with Razorpay'}
          </Button>
        ) : (
          <>
            <Button size="sm" variant="approve" disabled={busy}
              onClick={() => run(() => api.simulatePayment(txn.id, true))}
            >
              Confirm
            </Button>
            <Button size="sm" variant="ghost" disabled={busy}
              onClick={() => run(() => api.simulatePayment(txn.id, false))}
            >
              Decline
            </Button>
          </>
        ))}
    </div>
  )
}
