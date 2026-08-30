import { Link } from 'react-router-dom'
import { Button, Empty, Loading, Mono, Rule, Section, Status } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { inr } from '../lib/format'

/**
 * Agents as entities, not a grid of cards.
 *
 * A structured list reads down a column, so status, name, authority and
 * today's activity all line up and can be compared across agents. Boxing each
 * one would make five agents look like five unrelated dashboards.
 */

const CAPABILITIES = {
  shopping: ['Search', 'Compare', 'Select', 'Request payment'],
}

export default function Agents() {
  const { data: agents, loading, reload } = useLiveResource(() => api.agents())
  const { data: policies } = useLiveResource(() => api.policies())
  const { data: txns } = useLiveResource(() => api.transactions({ limit: 100 }))

  if (loading && !agents) return <Loading label="Reading agents" />

  const policyFor = (agentId) =>
    (policies || []).find(
      (p) => p.policy.agent_id === agentId && ['ACTIVE', 'EXHAUSTED'].includes(p.policy.status),
    )

  const activityFor = (agentId) =>
    (txns || []).filter((t) => t.transaction.agent_id === agentId)

  return (
    <div className="v-page space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-title font-semibold tracking-tight text-fg">Agents</h1>
          <p className="mt-2 max-w-lg text-small text-fg-muted">
            Autonomous actors you have registered. An agent holds no authority until you grant
            it a boundary.
          </p>
        </div>
        <Link to="/app/policies">
          <Button variant="primary">Grant authority</Button>
        </Link>
      </header>

      <Rule />

      {!agents?.length ? (
        <Empty title="No agents registered" hint="Register one on the Authority page to mint its credentials."
        />
      ) : (
        <ul className="divide-y divide-ink-900">
          {agents.map((agent) => {
            const view = policyFor(agent.id)
            const activity = activityFor(agent.id)
            const paid = activity.filter(
              (t) => t.transaction.state === 'PAYMENT_SUCCESS',
            ).length
            const blocked = activity.filter((t) => t.transaction.state === 'BLOCKED').length
            const active = agent.status === 'ACTIVE'

            return (
              <li key={agent.id} className="py-7 first:pt-0">
                <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr_auto] lg:items-start">
                  {/* Identity */}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <span
                        className={`h-[7px] w-[7px] rounded-full ${
                          active ? 'v-live bg-[color:var(--color-ok)]' : 'bg-ink-600'
                        }`}
                      />
                      <h2 className="text-heading font-medium text-fg">{agent.name}</h2>
                      {!active && <Status state="muted">{agent.status.toLowerCase()}</Status>}
                    </div>

                    <p className="mt-2 text-small text-fg-subtle">
                      {(CAPABILITIES[agent.agent_type] || ['Request payment']).join(' · ')}
                    </p>
                    <Mono className="mt-2 block">{agent.id}</Mono>
                  </div>

                  {/* Authority */}
                  <div>
                    {view ? (
                      <dl className="space-y-2">
                        <Row label="Per purchase" value={inr(view.policy.max_per_transaction_paise)}
                        />
                        <Row label="Budget remaining" value={view.remaining_budget_display}
                        />
                        <Row label="Auto-approve up to" value={inr(view.policy.approval_threshold_paise)}
                        />
                        <Row label="Scope" value={`${view.policy.allowed_categories.join(', ')} · ${view.policy.allowed_merchants.join(', ')}`}
                        />
                      </dl>
                    ) : (
                      <p className="text-small text-fg-faint">
                        No authority granted. Every request will be refused.
                      </p>
                    )}
                  </div>

                  {/* Activity */}
                  <div className="flex items-center gap-6 lg:flex-col lg:items-end lg:gap-2">
                    <div className="text-right">
                      <div className="tnum text-heading font-medium text-fg">
                        {activity.length}
                      </div>
                      <div className="text-label tracking-normal normal-case text-fg-faint">
                        requests
                      </div>
                    </div>
                    <div className="flex gap-4 lg:mt-1">
                      {paid > 0 && <Status state="ok">{paid} paid</Status>}
                      {blocked > 0 && <Status state="danger">{blocked} blocked</Status>}
                    </div>
                    {active && (
                      <button
                        onClick={() => api.suspendAgent(agent.id).then(reload)}
                        className="mt-1 text-label tracking-normal normal-case text-fg-faint transition-colors hover:text-[color:var(--color-danger)]"
                      >
                        Suspend agent
                      </button>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <Section title="How authority is proven">
        <p className="max-w-2xl text-small leading-relaxed text-fg-muted">
          Each agent holds a bearer token whose SHA-256 hash is all Velora stores. The token
          decides which agent is acting — an <span className="font-mono">agent_id</span> in a
          request body is only a claim, and a mismatch is blocked and recorded.
        </p>
      </Section>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="eyebrow">{label}</dt>
      <dd className="tnum truncate text-small text-fg-muted">{value}</dd>
    </div>
  )
}
