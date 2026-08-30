import { Link } from 'react-router-dom'
import ActivityStream from '../components/ActivityStream'
import AuthorityFlow from '../components/AuthorityFlow'
import { Empty, Figure, Loading, Mono, Rule, Section, Status } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { inr, paise } from '../lib/format'

/**
 * The control room.
 *
 * The question this page answers first is "what are my agents doing right
 * now", so the most recent evaluated purchase occupies the centre at full
 * size. Counts are secondary and live as bare figures, not as a row of
 * coloured widgets — a statistic is not an object and does not need a box.
 */
export default function Dashboard() {
  const { data: stats, loading } = useLiveResource(() => api.dashboard())
  const { data: policies } = useLiveResource(() => api.policies())
  const { data: txns } = useLiveResource(() => api.transactions({ limit: 10 }))

  const latest = txns?.[0]
  const { data: trail } = useLiveResource(
    () => (latest ? api.audit(latest.transaction.id) : Promise.resolve(null)),
    [latest?.transaction?.id],
  )

  if (loading && !stats) return <Loading label="Reading authority" />

  const inForce = (policies || []).filter((p) =>
    ['ACTIVE', 'EXHAUSTED'].includes(p.policy.status),
  )

  return (
    <div className="v-page space-y-14">
      {/* Secondary figures, deliberately quiet and above the fold's focus. */}
      <div className="grid grid-cols-2 gap-x-8 gap-y-7 sm:grid-cols-4">
        <Figure value={paise(stats?.total_spent_paise)} label="Settled today" note={`${stats?.paid ?? 0} payments`}
        />
        <Figure value={stats?.active_authorizations ?? 0} label="Authorizations in force" />
        <Figure value={stats?.pending_approvals ?? 0} label="Awaiting you" tone={stats?.pending_approvals ? 'warn' : 'default'}
        />
        <Figure value={stats?.blocked ?? 0} label="Blocked" tone={stats?.blocked ? 'danger' : 'default'} note={`${stats?.total_blocked_display ?? '₹0'} prevented`}
        />
      </div>

      <Rule />

      <div className="grid gap-14 lg:grid-cols-[1.15fr_1fr]">
        {/* Centrepiece */}
        <Section title="Live authority" description="The most recent purchase your agents put through the gate."
        >
          {!latest ? (
            <Empty title="No agent activity yet" hint="Give an agent a goal from the console and its decision will appear here."
            />
          ) : (
            <AuthorityFlow txn={latest.transaction}
              amountDisplay={latest.amount_display}
            />
          )}
        </Section>

        {/* Authority + stream */}
        <div className="space-y-14">
          <Section title="Standing authority" action={
              <Link to="/app/policies"
                className="text-label tracking-normal normal-case text-brand-400 transition-colors hover:text-brand-300"
              >
                Manage →
              </Link>
            }
          >
            {!inForce.length ? (
              <Empty title="No authority granted" hint="Agents hold nothing until you define a boundary."
              />
            ) : (
              <ul className="space-y-6">
                {inForce.map((view) => (
                  <AuthorityMeter key={view.policy.id} view={view} />
                ))}
              </ul>
            )}
          </Section>

          <Section title="System events" description={latest ? 'Newest first' : undefined} action={
              latest && (
                <Link to={`/app/audit/${latest.transaction.id}`}
                  className="text-label tracking-normal normal-case text-brand-400 transition-colors hover:text-brand-300"
                >
                  Full trail →
                </Link>
              )
            }
          >
            {!trail?.entries?.length ? (
              <Empty title="Nothing recorded yet" />
            ) : (
              <ActivityStream entries={[...trail.entries].reverse()} limit={9} />
            )}
          </Section>
        </div>
      </div>
    </div>
  )
}

/**
 * Spending authority as a track with a marker, not a filled bar.
 *
 * A filled bar reads as progress toward a goal. This is a limit, so the
 * marker shows position against a ceiling — and the held portion is drawn
 * separately because reserved money is committed but not yet spent.
 */
function AuthorityMeter({ view }) {
  const p = view.policy
  const total = p.total_budget_paise || 1
  const settled = Math.min(100, (p.amount_settled_paise / total) * 100)
  const held = Math.min(100 - settled, (p.amount_reserved_paise / total) * 100)
  const marker = Math.min(100, settled + held)

  return (
    <li>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-small font-medium text-fg">{p.name}</span>
        <span className="tnum text-small text-fg-muted">
          {view.remaining_budget_display} left
        </span>
      </div>

      <div className="relative mt-3 h-px w-full bg-ink-800">
        <div
          className="absolute inset-y-0 left-0 bg-[color:var(--color-ok)]/60" style={{ width: `${settled}%` }}
        />
        <div
          className="absolute inset-y-0 bg-[color:var(--color-warn)]/50" style={{ left: `${settled}%`, width: `${held}%` }}
        />
        <span
          className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand-400 transition-[left] duration-[var(--dur-slow)] ease-[var(--ease-out-soft)]" style={{ left: `${marker}%` }}
        />
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        <Mono>₹0</Mono>
        <span className="flex-1" />
        <Mono>{inr(p.total_budget_paise)}</Mono>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {p.amount_settled_paise > 0 && (
          <Status state="ok">{inr(p.amount_settled_paise)} spent</Status>
        )}
        {p.amount_reserved_paise > 0 && (
          <Status state="warn">{inr(p.amount_reserved_paise)} held</Status>
        )}
        <span className="ml-auto text-label tracking-normal normal-case text-fg-faint">
          max {inr(p.max_per_transaction_paise)} · auto ≤ {inr(p.approval_threshold_paise)}
        </span>
      </div>
    </li>
  )
}
