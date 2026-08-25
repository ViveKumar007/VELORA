import { useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Empty, Field, Input, Mono, Spinner } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api, setAgentToken } from '../lib/api'
import { dateTimeOf, inr } from '../lib/format'

const CATEGORIES = ['electronics', 'digital_goods', 'groceries', 'travel']
const MERCHANTS = ['DemoStore', 'AudioHouse']

const STATUS_STYLE = {
  ACTIVE: 'text-emerald-300 bg-emerald-500/10 ring-emerald-500/30',
  EXHAUSTED: 'text-zinc-400 bg-zinc-500/10 ring-zinc-500/30',
  EXPIRED: 'text-zinc-400 bg-zinc-500/10 ring-zinc-500/30',
  REVOKED: 'text-rose-300 bg-rose-500/10 ring-rose-500/30',
}

function Chips({ options, selected, onToggle }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const on = selected.includes(option)
        return (
          <button
            key={option}
            type="button"
            onClick={() => onToggle(option)}
            className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
              on
                ? 'border-brand-500 bg-brand-500/15 text-brand-400'
                : 'border-ink-700 bg-ink-850 text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {option}
          </button>
        )
      })}
    </div>
  )
}

export default function Policies() {
  const { data: policies, loading, reload } = useLiveResource(() => api.policies())
  const { data: agents, reload: reloadAgents } = useLiveResource(() => api.agents())

  const [form, setForm] = useState({
    agent_id: '',
    name: 'Headphones budget',
    max_per_transaction: 2000,
    total_budget: 2000,
    approval_threshold: 1500,
    max_transactions: 1,
    expires_in_minutes: 30,
    one_time_use: true,
  })
  const [categories, setCategories] = useState(['electronics'])
  const [merchants, setMerchants] = useState(['DemoStore'])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [newToken, setNewToken] = useState(null)

  useEffect(() => {
    if (!form.agent_id && agents?.length) {
      setForm((f) => ({ ...f, agent_id: agents[0].id }))
    }
  }, [agents, form.agent_id])

  const set = (key) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [key]: value }))
  }

  const toggle = (list, setList) => (value) =>
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])

  async function createAgent() {
    setError(null)
    try {
      const agent = await api.createAgent({ name: 'Shopping Agent', agent_type: 'shopping' })
      setNewToken(agent.token)
      setAgentToken(agent.token)
      await reloadAgents()
      setForm((f) => ({ ...f, agent_id: agent.id }))
    } catch (err) {
      setError(err.message)
    }
  }

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.createPolicy({
        agent_id: form.agent_id,
        name: form.name,
        max_per_transaction: Number(form.max_per_transaction),
        total_budget: Number(form.total_budget),
        approval_threshold: Number(form.approval_threshold),
        max_transactions: Number(form.max_transactions),
        expires_in_minutes: Number(form.expires_in_minutes),
        one_time_use: form.one_time_use,
        allowed_categories: categories,
        allowed_merchants: merchants,
        currency: 'INR',
      })
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Authorizations</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Draw the boundary. Everything outside it is refused, whatever the agent decides.
        </p>
      </div>

      {newToken && (
        <Alert kind="success">
          <div className="font-medium">Agent created. This token is shown once.</div>
          <code className="mt-1.5 block break-all font-mono text-[11px] text-emerald-300">
            {newToken}
          </code>
          <div className="mt-1.5 text-emerald-200/70">
            Saved to this browser and ready to use in the Agent Console.
          </div>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[400px_1fr]">
        <Card title="New authorization" subtitle="Amounts in rupees">
          <form onSubmit={submit} className="space-y-4">
            {/* An agent's token is shown only at creation, so this button has
                to stay reachable once agents exist -- otherwise the only way
                to obtain a token is to re-run the seed script. */}
            <Field label="Agent" hint="Registering an agent mints its token, shown once.">
              {agents?.length ? (
                <div className="flex gap-2">
                  <select
                    value={form.agent_id}
                    onChange={set('agent_id')}
                    className="min-w-0 flex-1 rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm text-zinc-100 focus:border-brand-500 focus:outline-none"
                  >
                    {agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.status.toLowerCase()})
                      </option>
                    ))}
                  </select>
                  <Button type="button" onClick={createAgent} title="Register another agent">
                    + Agent
                  </Button>
                </div>
              ) : (
                <Button type="button" variant="primary" onClick={createAgent} className="w-full">
                  Register an agent
                </Button>
              )}
            </Field>

            <Field label="Name">
              <Input value={form.name} onChange={set('name')} />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Max per purchase" hint="Ceiling on any one buy">
                <Input
                  type="number"
                  min="1"
                  value={form.max_per_transaction}
                  onChange={set('max_per_transaction')}
                />
              </Field>
              <Field label="Total budget" hint="Ceiling on all buys">
                <Input
                  type="number"
                  min="1"
                  value={form.total_budget}
                  onChange={set('total_budget')}
                />
              </Field>
            </div>

            <Field
              label="Auto-approve at or below"
              hint="Above this, Velora asks you before paying"
            >
              <Input
                type="number"
                min="0"
                value={form.approval_threshold}
                onChange={set('approval_threshold')}
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Max transactions">
                <Input
                  type="number"
                  min="1"
                  value={form.max_transactions}
                  onChange={set('max_transactions')}
                />
              </Field>
              <Field label="Expires in (min)">
                <Input
                  type="number"
                  min="1"
                  value={form.expires_in_minutes}
                  onChange={set('expires_in_minutes')}
                />
              </Field>
            </div>

            <Field label="Allowed categories">
              <Chips
                options={CATEGORIES}
                selected={categories}
                onToggle={toggle(categories, setCategories)}
              />
            </Field>

            <Field label="Allowed merchants">
              <Chips
                options={MERCHANTS}
                selected={merchants}
                onToggle={toggle(merchants, setMerchants)}
              />
            </Field>

            <label className="flex cursor-pointer items-center gap-2.5">
              <input
                type="checkbox"
                checked={form.one_time_use}
                onChange={set('one_time_use')}
                className="h-3.5 w-3.5 rounded border-ink-600 bg-ink-850 accent-brand-500"
              />
              <span className="text-xs text-zinc-400">Single use only</span>
            </label>

            {error && <Alert>{error}</Alert>}

            <Button
              type="submit"
              variant="primary"
              disabled={busy || !form.agent_id}
              className="w-full"
            >
              {busy ? 'Creating…' : 'Create authorization'}
            </Button>
          </form>
        </Card>

        <Card title="Issued authorizations" subtitle="Newest first">
          {loading && !policies ? (
            <Spinner />
          ) : !policies?.length ? (
            <Empty icon="○" title="No authorizations yet" hint="Create one to give an agent bounded authority." />
          ) : (
            <ul className="space-y-3">
              {policies.map((view) => {
                const p = view.policy
                return (
                  <li key={p.id} className="rounded-lg border border-ink-800 bg-ink-850/50 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-zinc-200">{p.name}</span>
                          <Badge className={STATUS_STYLE[p.status]}>{p.status}</Badge>
                        </div>
                        <Mono className="mt-0.5 block">{p.id}</Mono>
                      </div>
                      {p.status === 'ACTIVE' && (
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => api.revokePolicy(p.id).then(reload)}
                        >
                          Revoke
                        </Button>
                      )}
                    </div>

                    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-4">
                      <div>
                        <dt className="text-zinc-600">Per purchase</dt>
                        <dd className="tnum text-zinc-300">{inr(p.max_per_transaction_paise)}</dd>
                      </div>
                      <div>
                        <dt className="text-zinc-600">Budget left</dt>
                        <dd className="tnum text-zinc-300">{view.remaining_budget_display}</dd>
                      </div>
                      <div>
                        <dt className="text-zinc-600">Auto-approve</dt>
                        <dd className="tnum text-zinc-300">≤ {inr(p.approval_threshold_paise)}</dd>
                      </div>
                      <div>
                        <dt className="text-zinc-600">Txns left</dt>
                        <dd className="tnum text-zinc-300">
                          {view.transactions_remaining} / {p.max_transactions}
                        </dd>
                      </div>
                    </dl>

                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      {p.allowed_categories.map((c) => (
                        <span key={c} className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
                          {c}
                        </span>
                      ))}
                      {p.allowed_merchants.map((m) => (
                        <span key={m} className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
                          {m}
                        </span>
                      ))}
                      {p.one_time_use && (
                        <span className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
                          single use
                        </span>
                      )}
                      <span className="ml-auto text-[10px] text-zinc-600">
                        expires {dateTimeOf(p.expires_at)}
                      </span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
