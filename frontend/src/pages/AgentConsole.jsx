import { useState } from 'react'
import { DecisionPanel } from '../components/Decision'
import { Alert, Badge, Button, Card, Field, Input, Mono, Empty } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api, getAgentToken, setAgentToken } from '../lib/api'
import { inr } from '../lib/format'

const PRESETS = [
  'Buy me wireless headphones under 2000 with good battery life',
  'Find the cheapest headphones under 2000',
  'Buy me the best headphones you can find',
  'Get me a gaming subscription',
]

function ScoreBar({ value }) {
  return (
    <div className="h-1 w-16 overflow-hidden rounded-full bg-ink-800">
      <div className="h-full bg-brand-500/70" style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  )
}

function Candidate({ item, chosen }) {
  return (
    <div
      className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${
        chosen ? 'border-brand-500/40 bg-brand-500/[0.07]' : 'border-ink-800 bg-ink-850/40'
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-xs font-medium text-zinc-200">{item.name}</span>
          {chosen && (
            <Badge className="bg-brand-500/15 text-brand-400 ring-brand-500/30">chosen</Badge>
          )}
          {!item.within_budget && (
            <Badge className="bg-zinc-500/10 text-zinc-400 ring-zinc-500/30">over budget</Badge>
          )}
        </div>
        {item.notes?.length > 0 && (
          <p className="mt-0.5 truncate text-[11px] text-zinc-600">{item.notes.join(' · ')}</p>
        )}
      </div>
      <span className="tnum shrink-0 text-xs text-zinc-400">{item.price_display}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <ScoreBar value={item.score} />
        <span className="tnum w-8 text-right text-[10px] text-zinc-600">
          {item.score.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

export default function AgentConsole() {
  const [goal, setGoal] = useState(PRESETS[0])
  const [token, setToken] = useState(getAgentToken())
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState(null)

  const { data: products } = useLiveResource(() => api.products(), [], { poll: 0 })

  function saveToken(value) {
    setToken(value)
    setAgentToken(value)
  }

  async function run(autoSubmit) {
    setError(null)
    setResult(null)
    setBusy(true)
    setStage('Reading the goal and searching the catalog…')
    try {
      if (autoSubmit) {
        setTimeout(() => setStage('Asking Velora for permission…'), 450)
      }
      const out = await api.runAgent({ goal, auto_submit: autoSubmit })
      setResult(out)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
      setStage(null)
    }
  }

  const rec = result?.recommendation
  const txnView = result?.transaction

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Agent Console</h1>
        <p className="mt-1 text-sm text-zinc-500">
          The agent chooses what to buy. It cannot see your policy, and it cannot pay.
        </p>
      </div>

      {!token && (
        <Alert kind="warn">
          <div className="font-medium">No agent token set.</div>
          <div className="mt-0.5">
            Paste the token printed by <code className="font-mono">python -m app.seed</code>, or
            register an agent on the Authorizations page.
          </div>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.15fr]">
        <div className="space-y-6">
          <Card title="Shopping Agent" subtitle="Give it a goal in plain language">
            <div className="space-y-4">
              <Field label="Goal">
                <textarea
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  rows={2}
                  className="w-full resize-none rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
                />
              </Field>

              <div className="flex flex-wrap gap-1.5">
                {PRESETS.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setGoal(preset)}
                    className="rounded-lg border border-ink-700 bg-ink-850 px-2 py-1 text-[11px] text-zinc-500 transition hover:text-zinc-300"
                  >
                    {preset.length > 34 ? `${preset.slice(0, 34)}…` : preset}
                  </button>
                ))}
              </div>

              <div className="flex gap-2">
                <Button
                  variant="primary"
                  onClick={() => run(true)}
                  disabled={busy || !token}
                  className="flex-1"
                >
                  {busy ? 'Working…' : 'Run agent'}
                </Button>
                <Button onClick={() => run(false)} disabled={busy || !token}>
                  Choose only
                </Button>
              </div>

              {stage && (
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
                  {stage}
                </div>
              )}

              {error && <Alert>{error}</Alert>}
            </div>
          </Card>

          <Card title="Agent credentials" subtitle="Proves which agent is acting">
            <Field label="Bearer token">
              <Input
                value={token}
                onChange={(e) => saveToken(e.target.value)}
                placeholder="vla_…"
                className="font-mono text-xs"
              />
            </Field>
            <p className="mt-2 text-[11px] leading-relaxed text-zinc-600">
              Velora resolves this token to an agent and evaluates that identity. An agent_id in
              the request body is only a claim — a mismatch is blocked.
            </p>
          </Card>

          <Card title="Catalog" subtitle="Velora owns this data">
            <ul className="space-y-1.5">
              {(products || []).map((p) => (
                <li key={p.id} className="flex items-center gap-2 text-xs">
                  <span className="tnum w-16 shrink-0 text-right text-zinc-400">
                    {p.price_display}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-zinc-300">{p.name}</span>
                  <span className="shrink-0 text-[10px] text-zinc-600">{p.category}</span>
                  <span className="shrink-0 text-[10px] text-zinc-600">{p.merchant}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="space-y-6">
          {rec ? (
            <>
              <Card title="What the agent understood" subtitle="Parsed from the goal">
                <div className="flex flex-wrap gap-1.5">
                  {rec.intent.max_budget_paise && (
                    <Badge className="bg-ink-800 text-zinc-300 ring-ink-700">
                      budget {inr(rec.intent.max_budget_paise)}
                    </Badge>
                  )}
                  {rec.intent.category && (
                    <Badge className="bg-ink-800 text-zinc-300 ring-ink-700">
                      {rec.intent.category}
                    </Badge>
                  )}
                  {rec.intent.preferences.map((p) => (
                    <Badge key={p} className="bg-ink-800 text-zinc-300 ring-ink-700">
                      {p.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                  {rec.intent.product_query && (
                    <Badge className="bg-ink-800 text-zinc-300 ring-ink-700">
                      “{rec.intent.product_query}”
                    </Badge>
                  )}
                </div>

                {rec.chosen && (
                  <>
                    <p className="mt-4 text-sm leading-relaxed text-zinc-300">{rec.rationale}</p>
                    <div className="mt-3 space-y-1.5">
                      <Candidate item={rec.chosen} chosen />
                      {rec.alternatives.map((alt) => (
                        <Candidate key={alt.product_id} item={alt} />
                      ))}
                    </div>
                    <p className="mt-3 text-[11px] leading-relaxed text-zinc-600">
                      Scoring never considers your policy. The agent is allowed to want something
                      it cannot have — catching that is Velora's job.
                    </p>
                  </>
                )}
              </Card>

              {txnView ? (
                <Card title="Velora's decision" subtitle="Deterministic, and never made by a model">
                  <DecisionPanel txn={txnView.transaction} amountDisplay={txnView.amount_display} />
                </Card>
              ) : (
                <Alert kind="info">
                  The agent made a choice but did not submit it. Press{' '}
                  <strong>Run agent</strong> to ask Velora for permission.
                </Alert>
              )}
            </>
          ) : (
            <Card>
              <Empty
                icon="◇"
                title="No run yet"
                hint="Give the agent a goal and watch it choose — then watch Velora decide whether it may."
              />
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
