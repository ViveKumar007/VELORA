import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FlowStep } from '../components/AuthorityFlow'
import { Alert, Button, Empty, Loading, Mono, Rule, Status } from '../components/ui'
import { useLiveResource, useTick } from '../hooks/useLive'
import { api } from '../lib/api'
import { countdown, inr } from '../lib/format'

/**
 * The decision.
 *
 * One purchase at a time, with everything else stripped away. The amount and
 * the threshold it crossed are the two facts that matter, so they are the two
 * largest things on screen; the checks that passed sit underneath as evidence
 * rather than as competing content.
 *
 * No modal. A decision about money should be a place you are, not a thing
 * that interrupts you.
 */
export default function Approvals() {
  const { data, loading, reload } = useLiveResource(() => api.approvals())
  useTick(1000)

  if (loading && !data) return <Loading label="Checking for decisions" />

  const total = (data || []).reduce(
    (sum, item) => sum + item.transaction.requested_amount_paise,
    0,
  )

  return (
    <div className="v-page space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="text-title font-semibold tracking-tight text-fg">Approvals</h1>
          <p className="mt-2 max-w-lg text-small text-fg-muted">
            Purchases inside your limits but above the threshold you set for automatic
            approval.
          </p>
        </div>
        {data?.length > 0 && (
          <div className="text-right">
            <div className="tnum text-title font-semibold text-[color:var(--color-warn)]">
              {inr(total)}
            </div>
            <div className="text-label tracking-normal normal-case text-fg-faint">
              held pending your decision
            </div>
          </div>
        )}
      </header>

      <Rule />

      {!data?.length ? (
        <Empty title="Nothing needs your approval" hint="Purchases at or below your threshold clear on their own. Anything above it waits here."
        />
      ) : (
        <div className="space-y-16">
          {data.map((item) => (
            <Decision key={item.id} item={item} onDone={reload} />
          ))}
        </div>
      )}
    </div>
  )
}

function Decision({ item, onDone }) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [showChecks, setShowChecks] = useState(false)
  const t = item.transaction
  const remaining = countdown(item.expires_at)
  const urgent = remaining && !remaining.includes('m')
  const expired = remaining === 'expired'

  const threshold = t.policy_snapshot?.approval_threshold_paise
  const limit = t.policy_snapshot?.max_per_transaction_paise

  async function act(kind) {
    setBusy(kind)
    setError(null)
    try {
      if (kind === 'approve') await api.approve(t.id)
      else await api.reject(t.id, 'Rejected from the approval centre.')
      await onDone()
    } catch (err) {
      setError(err.message)
      await onDone()
    } finally {
      setBusy(null)
    }
  }

  const checks = (t.checks || []).filter((c) => c.status !== 'SKIP')

  return (
    <article className="v-enter">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <span className="eyebrow">Authority limit reached</span>
        <Status state={urgent || expired ? 'danger' : 'muted'}>
          {expired ? 'expired' : `expires in ${remaining}`}
        </Status>
      </div>

      {/* The two numbers that matter */}
      <div className="flex flex-wrap items-end gap-x-12 gap-y-6">
        <div>
          <div className="tnum text-display font-semibold tracking-tight text-fg">
            {item.amount_display}
          </div>
          <div className="mt-1.5 text-small text-fg-muted">
            {t.product_name} · {t.merchant}
          </div>
        </div>
        {threshold != null && (
          <div className="pb-2">
            <div className="tnum text-title font-medium text-fg-subtle">{inr(threshold)}</div>
            <div className="mt-1 text-label tracking-normal normal-case text-fg-faint">
              your auto-approval threshold
            </div>
          </div>
        )}
      </div>

      <p className="mt-6 max-w-xl text-body leading-relaxed text-fg-muted">
        This purchase is <span className="text-fg">within</span> your permitted scope
        {limit != null && <> of {inr(limit)} per purchase</>}, but exceeds the amount you
        allow Velora to approve on its own.
      </p>

      {t.agent_rationale && (
        <p className="mt-4 max-w-xl border-l border-ink-700 pl-4 text-small leading-relaxed text-fg-subtle italic">
          {t.agent_rationale}
        </p>
      )}

      {/* Evidence */}
      <div className="mt-8">
        <button
          onClick={() => setShowChecks((v) => !v)}
          className="eyebrow transition-colors hover:text-fg-muted"
        >
          {showChecks ? '− Hide' : '+ Show'} the {checks.length} checks that passed
        </button>
        {showChecks && (
          <ol className="mt-5 max-w-md">
            {checks.map((c, i) => (
              <FlowStep key={c.name} index={i} label={c.name} value={c.status} status={c.status} last={i === checks.length - 1}
              />
            ))}
          </ol>
        )}
      </div>

      {error && (
        <div className="mt-6 max-w-md">
          <Alert>{error}</Alert>
        </div>
      )}

      <div className="mt-9 flex flex-wrap items-center gap-3">
        <Button variant="approve"
          onClick={() => act('approve')} disabled={busy !== null || expired}
          className="px-6"
        >
          {busy === 'approve' ? 'Approving…' : `Approve ${item.amount_display}`}
        </Button>
        <Button variant="danger" onClick={() => act('reject')} disabled={busy !== null}>
          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
        </Button>
        <Link to={`/app/audit/${t.id}`}
          className="ml-auto text-label tracking-normal normal-case text-brand-400 transition-colors hover:text-brand-300"
        >
          Audit trail →
        </Link>
      </div>

      <Mono className="mt-5 block">{t.id}</Mono>
    </article>
  )
}
