import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChecksList } from '../components/Decision'
import { Alert, Badge, Button, Card, Empty, Mono, Spinner } from '../components/ui'
import { useLiveResource, useTick } from '../hooks/useLive'
import { api } from '../lib/api'
import { countdown, inr } from '../lib/format'

function ApprovalCard({ item, onDone }) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(false)
  const t = item.transaction
  const remaining = countdown(item.expires_at)
  const urgent = remaining && !remaining.includes('m')

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

  return (
    <div className="animate-in rounded-xl border border-amber-500/25 bg-amber-500/[0.035]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-800/70 px-5 py-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-2.5">
            <h3 className="text-base font-semibold text-zinc-100">{t.product_name}</h3>
            <span className="tnum text-base font-medium text-amber-200">
              {item.amount_display}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Mono>{t.merchant}</Mono>
            <Mono>·</Mono>
            <Mono>{t.category}</Mono>
            <Mono>·</Mono>
            <Mono>{t.id}</Mono>
          </div>
        </div>
        <Badge
          className={
            urgent
              ? 'bg-rose-500/10 text-rose-300 ring-rose-500/30'
              : 'bg-ink-800 text-zinc-400 ring-ink-700'
          }
        >
          {remaining === 'expired' ? 'expired' : `expires in ${remaining}`}
        </Badge>
      </div>

      <div className="px-5 py-4">
        <p className="text-sm leading-relaxed text-zinc-300">{item.prompt}</p>

        {t.agent_rationale && (
          <p className="mt-3 border-l-2 border-ink-700 pl-3 text-xs italic leading-relaxed text-zinc-500">
            Agent reasoning: {t.agent_rationale}
          </p>
        )}

        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 text-[11px] font-medium text-brand-400 hover:text-brand-500"
        >
          {expanded ? 'Hide' : 'Show'} the {t.checks?.length ?? 0} policy checks
        </button>

        {expanded && (
          <div className="mt-2 rounded-lg border border-ink-800 bg-ink-900/60 py-2">
            <ChecksList checks={t.checks} dense />
          </div>
        )}

        {error && (
          <div className="mt-3">
            <Alert>{error}</Alert>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-ink-800/70 px-5 py-3">
        <Button
          variant="approve"
          onClick={() => act('approve')}
          disabled={busy !== null || remaining === 'expired'}
        >
          {busy === 'approve' ? 'Approving…' : `Approve ${item.amount_display}`}
        </Button>
        <Button variant="danger" onClick={() => act('reject')} disabled={busy !== null}>
          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
        </Button>
        <Link
          to={`/audit/${t.id}`}
          className="ml-auto text-[11px] font-medium text-brand-400 hover:text-brand-500"
        >
          Audit trail →
        </Link>
      </div>
    </div>
  )
}

export default function Approvals() {
  const { data, loading, reload } = useLiveResource(() => api.approvals())
  useTick(1000)

  const total = (data || []).reduce(
    (sum, item) => sum + item.transaction.requested_amount_paise,
    0,
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Approval Centre</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Purchases inside the limit but above your auto-approval threshold.
          </p>
        </div>
        {data?.length > 0 && (
          <div className="text-right">
            <div className="tnum text-lg font-semibold text-amber-200">{inr(total)}</div>
            <div className="text-[11px] text-zinc-600">held pending your decision</div>
          </div>
        )}
      </div>

      {loading && !data ? (
        <Spinner />
      ) : !data?.length ? (
        <Card>
          <Empty
            icon="✓"
            title="Nothing needs your approval"
            hint="Purchases at or below your auto-approval threshold clear without asking. Anything above it will appear here."
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {data.map((item) => (
            <ApprovalCard key={item.id} item={item} onDone={reload} />
          ))}
        </div>
      )}
    </div>
  )
}
