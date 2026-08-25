import { Link } from 'react-router-dom'
import { Badge, DecisionBadge, Empty, Card, Mono, Spinner, Stat, StateBadge } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { dateTimeOf, inr } from '../lib/format'

function BudgetBar({ policy }) {
  const total = policy.total_budget_paise || 1
  const settled = (policy.amount_settled_paise / total) * 100
  const reserved = (policy.amount_reserved_paise / total) * 100

  return (
    <div>
      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-ink-800">
        <div className="bg-emerald-500" style={{ width: `${Math.min(settled, 100)}%` }} />
        <div className="bg-amber-500/70" style={{ width: `${Math.min(reserved, 100 - settled)}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-zinc-600">
        <span className="text-emerald-400/80">{inr(policy.amount_settled_paise)} spent</span>
        {policy.amount_reserved_paise > 0 && (
          <span className="text-amber-400/80">{inr(policy.amount_reserved_paise)} held</span>
        )}
        <span className="ml-auto text-zinc-500">of {inr(policy.total_budget_paise)}</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { data: stats, loading } = useLiveResource(() => api.dashboard())
  const { data: policies } = useLiveResource(() => api.policies())
  const { data: txns } = useLiveResource(() => api.transactions({ limit: 8 }))

  if (loading && !stats) return <Spinner />

  // ACTIVE and EXHAUSTED both count as in force: a single-use policy reads
  // EXHAUSTED while it holds a reservation for a pending approval, and
  // returns to ACTIVE if that purchase is rejected.
  const active = (policies || []).filter((p) =>
    ['ACTIVE', 'EXHAUSTED'].includes(p.policy.status),
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every purchase your agents attempted, and what Velora decided.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat
          label="Active authorizations"
          value={stats?.active_authorizations ?? 0}
          sub={active.length ? `${inr(stats?.total_authorized_paise)} authorized` : 'None active'}
        />
        <Stat
          label="Approved"
          value={stats?.approved ?? 0}
          accent="text-emerald-300"
          sub="Cleared the gate"
        />
        <Stat
          label="Awaiting you"
          value={stats?.pending_approvals ?? 0}
          accent={stats?.pending_approvals ? 'text-amber-300' : 'text-zinc-100'}
          sub={stats?.pending_approvals ? 'Needs a decision' : 'Nothing pending'}
        />
        <Stat
          label="Blocked"
          value={stats?.blocked ?? 0}
          accent="text-rose-300"
          sub={`${stats?.total_blocked_display ?? '₹0'} prevented`}
        />
        <Stat
          label="Paid"
          value={stats?.paid ?? 0}
          sub={`${stats?.total_spent_display ?? '₹0'} settled`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
        <Card
          title="Active authorizations"
          subtitle="What your agents are currently allowed to do"
          right={
            <Link to="/policies" className="text-[11px] font-medium text-brand-400 hover:text-brand-500">
              Manage →
            </Link>
          }
        >
          {active.length === 0 ? (
            <Empty
              icon="○"
              title="No active authorizations"
              hint="Agents hold no spending authority until you grant it."
            />
          ) : (
            <ul className="space-y-4">
              {active.map(({ policy, remaining_budget_display, transactions_remaining }) => (
                <li key={policy.id} className="rounded-lg border border-ink-800 bg-ink-850/50 p-4">
                  <div className="mb-2.5 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-zinc-200">
                          {policy.name}
                        </span>
                        {policy.status === 'EXHAUSTED' && (
                          <Badge className="bg-zinc-500/10 text-zinc-400 ring-zinc-500/30">
                            no headroom
                          </Badge>
                        )}
                      </div>
                      <Mono>{policy.agent_id}</Mono>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="tnum text-sm font-medium text-zinc-200">
                        {remaining_budget_display}
                      </div>
                      <div className="text-[11px] text-zinc-600">left</div>
                    </div>
                  </div>
                  <BudgetBar policy={policy} />
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-zinc-600">
                    <span>Max {inr(policy.max_per_transaction_paise)}/purchase</span>
                    <span>Auto-approve ≤ {inr(policy.approval_threshold_paise)}</span>
                    <span>{transactions_remaining} txn left</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {policy.allowed_categories.map((c) => (
                      <span
                        key={c}
                        className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] text-zinc-500"
                      >
                        {c}
                      </span>
                    ))}
                    {policy.allowed_merchants.map((m) => (
                      <span
                        key={m}
                        className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] text-zinc-500"
                      >
                        {m}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Recent agent activity"
          subtitle="Newest first"
          right={
            <Link
              to="/transactions"
              className="text-[11px] font-medium text-brand-400 hover:text-brand-500"
            >
              All transactions →
            </Link>
          }
        >
          {!txns?.length ? (
            <Empty
              icon="○"
              title="No agent activity yet"
              hint="Send your agent a goal from the Agent Console."
            />
          ) : (
            <ul className="divide-y divide-ink-800">
              {txns.map(({ transaction: t, amount_display }) => (
                <li key={t.id}>
                  <Link
                    to={`/audit/${t.id}`}
                    className="-mx-2 flex items-start gap-3 rounded-lg px-2 py-3 transition hover:bg-ink-850/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2">
                        <span className="truncate text-sm font-medium text-zinc-200">
                          {t.product_name}
                        </span>
                        <span className="tnum shrink-0 text-sm text-zinc-400">{amount_display}</span>
                      </div>
                      <p className="mt-0.5 line-clamp-1 text-xs text-zinc-600">{t.explanation}</p>
                      <div className="mt-1.5 flex items-center gap-2">
                        <Mono>{dateTimeOf(t.created_at)}</Mono>
                        <Mono>·</Mono>
                        <Mono>{t.reason_code}</Mono>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1.5">
                      <DecisionBadge decision={t.decision} />
                      <StateBadge state={t.state} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
