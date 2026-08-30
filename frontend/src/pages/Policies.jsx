import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Empty,
  Field,
  Input,
  Loading,
  Mono,
  Rule,
  Section,
  Status,
} from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api, setAgentToken } from '../lib/api'
import { dateTimeOf, inr } from '../lib/format'

const CATEGORIES = ['electronics', 'groceries', 'digital_goods', 'food', 'travel']
const MERCHANTS = ['DemoStore', 'Blinkit', 'Zepto', 'Amazon', 'Swiggy']

/**
 * Authority, not a form.
 *
 * Sections separated by rules and labels rather than boxed panels, with the
 * amount inputs sized to the thing they represent — a spending ceiling is the
 * most consequential number on the page and should look it.
 */
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
    if (!form.agent_id && agents?.length) setForm((f) => ({ ...f, agent_id: agents[0].id }))
  }, [agents, form.agent_id])

  const set = (key) => (e) =>
    setForm((f) => ({
      ...f,
      [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
    }))

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

  if (loading && !policies) return <Loading label="Reading authority" />

  return (
    <div className="v-page space-y-12">
      <header>
        <h1 className="text-title font-semibold tracking-tight text-fg">Authority</h1>
        <p className="mt-2 max-w-lg text-small text-fg-muted">
          Define exactly what an agent may do. Everything outside the boundary is refused,
          explained and recorded.
        </p>
      </header>

      {newToken && (
        <Alert kind="success">
          <div className="font-medium">Agent registered. This token is shown once.</div>
          <code className="mt-2 block break-all font-mono text-label tracking-normal normal-case">
            {newToken}
          </code>
        </Alert>
      )}

      <div className="grid gap-14 lg:grid-cols-[minmax(0,380px)_1fr]">
        {/* Composer */}
        <form onSubmit={submit} className="space-y-10">
          <Section title="Agent">
            {agents?.length ? (
              <div className="flex gap-2">
                <select value={form.agent_id}
                  onChange={set('agent_id')}
                  className="min-w-0 flex-1 rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 text-body text-fg transition-colors focus:border-brand-500 focus:outline-none"
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
            <p className="mt-2 text-label tracking-normal normal-case text-fg-faint">
              Registering mints a bearer token, shown once.
            </p>
          </Section>

          <Rule />

          <Section title="Spending">
            <div className="space-y-6">
              <Amount label="Per purchase" value={form.max_per_transaction}
                onChange={set('max_per_transaction')} hint="Ceiling on any single buy."
              />
              <Amount label="Total budget" value={form.total_budget}
                onChange={set('total_budget')} hint="Ceiling on everything combined."
              />
            </div>
          </Section>

          <Rule />

          <Section title="Auto-approval">
            <Amount label="Approve automatically up to" value={form.approval_threshold}
              onChange={set('approval_threshold')} hint="Above this, Velora holds the purchase and asks you."
            />
          </Section>

          <Rule />

          <Section title="Scope">
            <div className="space-y-6">
              <Field label="Categories">
                <Chips options={CATEGORIES} selected={categories}
                  onToggle={toggle(categories, setCategories)}
                />
              </Field>
              <Field label="Merchants">
                <Chips options={MERCHANTS} selected={merchants}
                  onToggle={toggle(merchants, setMerchants)}
                />
              </Field>
            </div>
          </Section>

          <Rule />

          <Section title="Duration">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Max transactions">
                <Input type="number" min="1" value={form.max_transactions}
                  onChange={set('max_transactions')}
                />
              </Field>
              <Field label="Expires in (min)">
                <Input type="number" min="1" value={form.expires_in_minutes}
                  onChange={set('expires_in_minutes')}
                />
              </Field>
            </div>
            <label className="mt-4 flex cursor-pointer items-center gap-2.5">
              <input type="checkbox" checked={form.one_time_use}
                onChange={set('one_time_use')}
                className="h-3.5 w-3.5 rounded border-ink-600 bg-ink-900 accent-[color:var(--color-brand-500)]"
              />
              <span className="text-small text-fg-muted">Single use only</span>
            </label>
          </Section>

          <Field label="Name">
            <Input value={form.name} onChange={set('name')} />
          </Field>

          {error && <Alert>{error}</Alert>}

          <Button type="submit" variant="primary" disabled={busy || !form.agent_id}
            className="w-full"
          >
            {busy ? 'Granting…' : 'Grant authority'}
          </Button>
        </form>

        {/* Issued */}
        <Section title="Issued authority" description="Newest first">
          {!policies?.length ? (
            <Empty title="Nothing granted yet" hint="Agents hold nothing until you decide." />
          ) : (
            <ul className="divide-y divide-ink-900">
              {policies.map((view) => {
                const p = view.policy
                const live = p.status === 'ACTIVE'
                return (
                  <li key={p.id} className="py-6 first:pt-0">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-3">
                          <h3 className="text-heading font-medium text-fg">{p.name}</h3>
                          <Status state={
                              live
                                ? 'ok'
                                : p.status === 'REVOKED'
                                  ? 'danger'
                                  : 'muted'
                            }
                          >
                            {p.status.toLowerCase()}
                          </Status>
                        </div>
                        <Mono className="mt-1.5 block">{p.id}</Mono>
                      </div>
                      {live && (
                        <button
                          onClick={() => api.revokePolicy(p.id).then(reload)}
                          className="text-label tracking-normal normal-case text-fg-faint transition-colors hover:text-[color:var(--color-danger)]"
                        >
                          Revoke
                        </button>
                      )}
                    </div>

                    <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-2.5 sm:grid-cols-4">
                      <Spec label="Per purchase" value={inr(p.max_per_transaction_paise)} />
                      <Spec label="Remaining" value={view.remaining_budget_display} />
                      <Spec label="Auto-approve" value={`≤ ${inr(p.approval_threshold_paise)}`} />
                      <Spec label="Transactions" value={`${view.transactions_remaining} / ${p.max_transactions}`}
                      />
                    </dl>

                    <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                      {[...p.allowed_categories, ...p.allowed_merchants].map((tag) => (
                        <Mono key={tag}>{tag}</Mono>
                      ))}
                      {p.one_time_use && <Mono>single use</Mono>}
                      <span className="ml-auto text-label tracking-normal normal-case text-fg-faint">
                        expires {dateTimeOf(p.expires_at)}
                      </span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </Section>
      </div>
    </div>
  )
}

/** Amount inputs are large: they are the most consequential values here. */
function Amount({ label, value, onChange, hint }) {
  return (
    <div>
      <span className="eyebrow mb-2 block">{label}</span>
      <div className="flex items-baseline gap-2 border-b border-ink-700 pb-2 transition-colors focus-within:border-brand-500">
        <span className="text-title font-medium text-fg-subtle">₹</span>
        <input type="number" min="0" value={value}
          onChange={onChange}
          className="tnum w-full bg-transparent text-title font-semibold text-fg focus:outline-none"
        />
      </div>
      {hint && <p className="mt-2 text-label tracking-normal normal-case text-fg-faint">{hint}</p>}
    </div>
  )
}

function Chips({ options, selected, onToggle }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const on = selected.includes(option)
        return (
          <button key={option} type="button"
            onClick={() => onToggle(option)}
            className={`rounded-lg border px-2.5 py-1 text-small transition-all duration-[var(--dur-fast)] ${
              on
                ? 'border-brand-500/50 bg-brand-500/12 text-brand-300'
                : 'border-ink-700 bg-ink-900 text-fg-subtle hover:border-ink-600 hover:text-fg-muted'
            }`}
          >
            {option}
          </button>
        )
      })}
    </div>
  )
}

function Spec({ label, value }) {
  return (
    <div>
      <dt className="eyebrow">{label}</dt>
      <dd className="tnum mt-1 text-small text-fg-muted">{value}</dd>
    </div>
  )
}
