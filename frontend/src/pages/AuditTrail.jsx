import { Fragment, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AuthorityFlow from '../components/AuthorityFlow'
import { Alert, Empty, Loading, Mono, Rule, Section, Status } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { timeOf } from '../lib/format'

/**
 * The record.
 *
 * A structured table rather than a decorated timeline: this is evidence, and
 * evidence should be scannable in columns. Colour appears only on the state
 * column, where it carries meaning.
 *
 * The integrity panel is the point of the page — it lets a reader verify the
 * trail was not rewritten instead of asking them to trust it.
 */

const EVENT_LABEL = {
  REQUEST_RECEIVED: 'PURCHASE_REQUESTED',
  EVALUATION_STARTED: 'EVALUATION_STARTED',
  CHECK_EVALUATED: 'POLICY_CHECK',
  DECISION_MADE: 'DECISION_MADE',
  RECOVERY_OFFERED: 'ALTERNATIVE_OFFERED',
  BUDGET_RESERVED: 'BUDGET_RESERVED',
  BUDGET_RELEASED: 'BUDGET_RELEASED',
  HUMAN_APPROVED: 'USER_APPROVED',
  HUMAN_REJECTED: 'USER_REJECTED',
  APPROVAL_EXPIRED: 'APPROVAL_EXPIRED',
  PAYMENT_CREATED: 'PAYMENT_CREATED',
  PAYMENT_SUCCEEDED: 'PAYMENT_CONFIRMED',
  PAYMENT_FAILED: 'PAYMENT_FAILED',
  PAYMENT_CREATION_FAILED: 'PAYMENT_CREATION_FAILED',
  DUPLICATE_SUPPRESSED: 'DUPLICATE_SUPPRESSED',
  STATE_CHANGED: 'STATE_CHANGED',
}

const STATE_TONE = {
  PASS: 'ok',
  APPROVED: 'ok',
  REVIEW: 'warn',
  PENDING_APPROVAL: 'warn',
  FAIL: 'danger',
  BLOCKED: 'danger',
  REJECTED: 'danger',
}

export default function AuditTrail() {
  const { id } = useParams()
  const [open, setOpen] = useState(null)
  const { data: trail, loading, error } = useLiveResource(() => api.audit(id), [id])
  const { data: txnView } = useLiveResource(() => api.transaction(id), [id])

  if (loading && !trail) return <Loading label="Reconstructing trail" />
  if (error) return <Alert>{error.message}</Alert>

  const integrity = trail?.integrity

  return (
    <div className="v-page space-y-10">
      <header>
        <Link to="/app/transactions"
          className="text-label tracking-normal normal-case text-fg-subtle transition-colors hover:text-fg-muted"
        >
          ← All transactions
        </Link>
        <h1 className="mt-3 text-title font-semibold tracking-tight text-fg">Audit trail</h1>
        <Mono className="mt-1.5 block">{id}</Mono>
      </header>

      <Rule />

      <div className="grid gap-12 lg:grid-cols-[1fr_280px]">
        <div className="min-w-0 space-y-12">
          {txnView && (
            <Section title="Decision">
              <AuthorityFlow txn={txnView.transaction}
                amountDisplay={txnView.amount_display}
              />
            </Section>
          )}

          <Section title="Event record" description={`${trail?.entries?.length ?? 0} events, oldest first`}
          >
            {!trail?.entries?.length ? (
              <Empty title="No events recorded" />
            ) : (
              <div className="-mx-2 overflow-x-auto">
                <table className="w-full min-w-[600px]">
                  <thead>
                    <tr className="border-b border-ink-800">
                      {['Time', 'Event', 'Transition', 'State'].map((h) => (
                        <th key={h} className="eyebrow px-2 pb-2.5 text-left font-medium">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-900">
                    {trail.entries.map((entry) => {
                      const expanded = open === entry.id
                      const moved =
                        entry.previous_state &&
                        entry.new_state &&
                        entry.previous_state !== entry.new_state
                      return (
                        <Fragment key={entry.id}>
                          <tr
                            onClick={() => setOpen(expanded ? null : entry.id)}
                            className="cursor-pointer transition-colors hover:bg-ink-950"
                          >
                            <td className="px-2 py-2.5 align-top">
                              <Mono className="tnum">{timeOf(entry.created_at)}</Mono>
                            </td>
                            <td className="px-2 py-2.5 align-top">
                              <span className="font-mono text-label tracking-normal normal-case text-fg-muted">
                                {EVENT_LABEL[entry.event_type] || entry.event_type}
                              </span>
                            </td>
                            <td className="px-2 py-2.5 align-top">
                              {moved ? (
                                <Mono>
                                  {entry.previous_state} → {entry.new_state}
                                </Mono>
                              ) : (
                                <span className="text-ink-600">—</span>
                              )}
                            </td>
                            <td className="px-2 py-2.5 align-top">
                              {entry.decision ? (
                                <Status state={STATE_TONE[entry.decision] || 'muted'}>
                                  {entry.decision}
                                </Status>
                              ) : (
                                <span className="text-ink-600">—</span>
                              )}
                            </td>
                          </tr>
                          {expanded && (
                            <tr className="bg-ink-950">
                              <td colSpan={4} className="px-2 pt-1 pb-4">
                                <p className="v-enter max-w-2xl text-small leading-relaxed text-fg-muted">
                                  {entry.explanation}
                                </p>
                                <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1">
                                  <Mono>#{entry.seq}</Mono>
                                  <Mono>actor {entry.actor}</Mono>
                                  {entry.reason_code && <Mono>{entry.reason_code}</Mono>}
                                  <Mono>hash {entry.entry_hash.slice(0, 16)}</Mono>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-4 text-label tracking-normal normal-case text-fg-faint">
              Select any row to see its explanation and hash.
            </p>
          </Section>
        </div>

        <aside className="space-y-10">
          <Section title="Integrity">
            {integrity?.valid ? (
              <>
                <Status state="ok">Chain intact</Status>
                <p className="mt-3 text-small leading-relaxed text-fg-subtle">
                  All {integrity.entries} entries hash correctly against their predecessor.
                  Altering any past entry would break every hash after it.
                </p>
              </>
            ) : (
              <>
                <Status state="danger">Chain broken</Status>
                <p className="mt-3 text-small leading-relaxed text-fg-subtle">
                  {integrity?.detail} First mismatch at entry #{integrity?.broken_at_seq}.
                </p>
              </>
            )}
          </Section>

          {txnView?.transaction?.policy_id && (
            <Section title="Judged against">
              <Mono className="block break-all">{txnView.transaction.policy_id}</Mono>
              <p className="mt-3 text-small leading-relaxed text-fg-subtle">
                The policy was snapshotted at evaluation, so this record stays accurate even
                if the authorization is edited later.
              </p>
            </Section>
          )}

          {txnView?.transaction?.payment_order_id && (
            <Section title="Payment">
              <dl className="space-y-3">
                <div>
                  <dt className="eyebrow">Order</dt>
                  <dd className="mt-1 font-mono text-label tracking-normal break-all normal-case text-fg-muted">
                    {txnView.transaction.payment_order_id}
                  </dd>
                </div>
                {txnView.transaction.payment_id && (
                  <div>
                    <dt className="eyebrow">Payment</dt>
                    <dd className="mt-1 font-mono text-label tracking-normal break-all normal-case text-fg-muted">
                      {txnView.transaction.payment_id}
                    </dd>
                  </div>
                )}
                {txnView.transaction.payment_error && (
                  <div>
                    <dt className="eyebrow">Error</dt>
                    <dd className="mt-1 text-small text-[color:var(--color-danger)]">
                      {txnView.transaction.payment_error}
                    </dd>
                  </div>
                )}
              </dl>
            </Section>
          )}
        </aside>
      </div>
    </div>
  )
}
