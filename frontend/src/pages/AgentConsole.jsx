import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Basket from '../components/Basket'
import { DecisionPanel } from '../components/Decision'
import { Alert, Badge, Button, Field, Input, Mono, Empty, Rule, Section } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api, getAgentToken, setAgentToken } from '../lib/api'
import { inr } from '../lib/format'

const PRESETS = [
  'Buy me wireless headphones under 2000 with good battery life',
  'Find the cheapest headphones under 2000',
  'Buy me the best headphones you can find',
  'Get me a gaming subscription',
]

/** A score is a position on a scale, so it is drawn as a hairline track with
 *  a filled portion — the same visual grammar as the budget meter. */
function ScoreBar({ value }) {
  return (
    <div className="h-px w-16 bg-ink-700">
      <div
        className="h-full bg-brand-400 transition-[width] duration-[var(--dur-slow)] ease-[var(--ease-out-soft)]" style={{ width: `${Math.round(value * 100)}%` }}
      />
    </div>
  )
}

/** A candidate IS an object — it earns a surface. The chosen one is marked by
 *  a lit left edge rather than by a fill, so the row still reads as a row. */
function Candidate({ item, chosen }) {
  return (
    <div
      className={`flex items-center gap-3 rounded-[var(--radius-sm)] border-y border-r px-3 py-2.5 transition-colors duration-[var(--dur-base)] ${
        chosen
          ? 'border-l-2 border-y-brand-500/25 border-r-brand-500/25 border-l-brand-500 bg-brand-500/[0.06]'
          : 'border-l-2 border-ink-900 border-l-transparent hover:border-y-ink-800 hover:border-r-ink-800 hover:bg-ink-950'
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-small font-medium text-fg">{item.name}</span>
          {chosen && (
            <Badge className="bg-brand-500/15 text-brand-400 ring-brand-500/30">chosen</Badge>
          )}
          {!item.within_budget && (
            <Badge className="bg-zinc-500/10 text-fg-muted ring-zinc-500/30">over budget</Badge>
          )}
        </div>
        {item.notes?.length > 0 && (
          <p className="mt-0.5 truncate text-label tracking-normal normal-case text-fg-faint">{item.notes.join(' · ')}</p>
        )}
      </div>
      <span className="tnum shrink-0 text-small text-fg-muted">{item.price_display}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <ScoreBar value={item.score} />
        <span className="tnum w-8 text-right text-label tracking-normal normal-case text-fg-faint">
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
  const [stopped, setStopped] = useState(null)
  const [basket, setBasket] = useState(null)
  const stageTimer = useRef(null)
  const abortRef = useRef(null)

  // Leaving a timer armed across an unmount would set state on a component
  // that no longer exists; leaving a request in flight wastes a decision
  // nobody is waiting for.
  useEffect(
    () => () => {
      clearTimeout(stageTimer.current)
      abortRef.current?.abort()
    },
    [],
  )

  const { data: products } = useLiveResource(() => api.products(), [], { poll: 0 })

  function saveToken(value) {
    setToken(value)
    setAgentToken(value)
  }

  /**
   * Stop watching the run.
   *
   * Be precise about what this does: it abandons the response, not the work.
   * Velora has no idea the browser walked away, so a request that already
   * reached the gate is still evaluated, still decided and still recorded.
   * Calling this "cancel the purchase" would be a lie on a screen about
   * spending money, which is why the notice says where to go and look.
   */
  function stop() {
    abortRef.current?.abort()
  }

  /**
   * Ask for the whole list rather than one product. Proposes only -- nothing
   * reaches the gate until the person confirms what they actually want.
   */
  async function buildBasket() {
    setError(null)
    setResult(null)
    setStopped(null)
    setBasket(null)
    setBusy(true)
    setStage('Reading the recipe and searching the catalog…')

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const out = await api.basket(goal, { signal: controller.signal })
      setBasket(out.basket)
    } catch (err) {
      if (err?.name === 'AbortError') setStopped('Stopped. Nothing was sent to Velora.')
      else setError(err.message)
    } finally {
      clearTimeout(stageTimer.current)
      abortRef.current = null
      setBusy(false)
      setStage(null)
    }
  }

  /**
   * The second stage caption is on a timer, and the timer has to be cancelled
   * when the run finishes.
   *
   * It was not. A run that completed in under 450ms cleared the caption in
   * `finally`, and then the orphaned timer fired afterwards and set it back
   * to "Asking Velora for permission…" with nothing left to clear it. The
   * console sat there apparently working forever, next to a finished result.
   * Fast responses made it near-permanent rather than rare.
   */
  async function run(autoSubmit) {
    setError(null)
    setResult(null)
    setStopped(null)
    setBasket(null)
    setBusy(true)
    setStage('Reading the goal and searching the catalog…')

    const controller = new AbortController()
    abortRef.current = controller

    clearTimeout(stageTimer.current)
    if (autoSubmit) {
      stageTimer.current = setTimeout(
        () => setStage('Asking Velora for permission…'),
        450,
      )
    }

    try {
      const out = await api.runAgent(
        { goal, auto_submit: autoSubmit },
        { signal: controller.signal },
      )
      setResult(out)
    } catch (err) {
      if (err?.name === 'AbortError') {
        setStopped(
          autoSubmit
            ? 'Stopped. The agent may already have asked Velora — any decision it reached is recorded in Transactions.'
            : 'Stopped before the agent finished choosing. Nothing was sent to Velora.',
        )
      } else {
        setError(err.message)
      }
    } finally {
      clearTimeout(stageTimer.current)
      abortRef.current = null
      setBusy(false)
      setStage(null)
    }
  }

  const rec = result?.recommendation
  const txnView = result?.transaction

  return (
    <div className="v-page space-y-10">
      <header>
        <h1 className="text-title font-semibold tracking-tight text-fg">Agent Console</h1>
        <p className="mt-2 max-w-lg text-small text-fg-muted">
          The agent chooses what to buy. It cannot see your policy, and it cannot pay.
        </p>
      </header>

      {!token && (
        <Alert kind="warn">
          <div className="font-medium">No agent token set.</div>
          <div className="mt-0.5">
            Paste the token printed by <code className="font-mono">python -m app.seed</code>, or
            register an agent on the Authority page.
          </div>
        </Alert>
      )}

      <Rule />

      <div className="grid gap-14 lg:grid-cols-[minmax(0,380px)_1fr]">
        {/* Composer. Sections divided by rules, matching Authority — the two
            pages are the same kind of act (instructing something) and should
            not look like different products. */}
        <div className="space-y-10">
          <Section title="Goal" description="Plain language. No product ids.">
            <textarea value={goal}
              onChange={(e) => setGoal(e.target.value)} rows={2}
              className="w-full resize-none rounded-[var(--radius-sm)] border border-[color:var(--color-border-control)] bg-ink-900 px-3 py-2.5 text-body leading-relaxed text-fg transition-colors duration-[var(--dur-fast)] placeholder:text-fg-faint hover:border-ink-500 focus:border-brand-500"
            />

            <div className="mt-3 flex flex-wrap gap-1.5">
              {PRESETS.map((preset) => (
                <button key={preset} type="button"
                  onClick={() => setGoal(preset)}
                  className={`rounded-[var(--radius-sm)] border px-2.5 py-1 text-label tracking-normal normal-case transition-all duration-[var(--dur-fast)] ${
                    goal === preset
                      ? 'border-brand-500/50 bg-brand-500/12 text-brand-300'
                      : 'border-ink-800 bg-ink-900 text-fg-subtle hover:border-ink-600 hover:text-fg-muted'
                  }`}
                >
                  {preset.length > 34 ? `${preset.slice(0, 34)}…` : preset}
                </button>
              ))}
            </div>

            {/* While a run is in flight, the secondary action becomes Stop.
                Swapping it rather than adding a third button keeps the row
                the same width and never offers two ways to start at once. */}
            <div className="mt-5 flex gap-2">
              <Button variant="primary"
                onClick={() => run(true)} disabled={busy || !token}
                className="flex-1"
              >
                {busy ? 'Working…' : 'Run agent'}
              </Button>
              {busy ? (
                <Button variant="danger" onClick={stop}>
                  Stop
                </Button>
              ) : (
                <Button onClick={() => run(false)} disabled={!token}>
                  Choose only
                </Button>
              )}
            </div>

            {/* A recipe is a list, not a product. This asks the agent for
                every ingredient rather than the single best thing. */}
            <div className="mt-2">
              <Button onClick={buildBasket} disabled={busy || !token} className="w-full">
                {busy ? 'Working…' : 'Build shopping list'}
              </Button>
            </div>

            {/* The live node, in the language of the mark. */}
            {stage && (
              <div className="v-enter mt-4 flex items-center gap-2.5 text-small text-fg-subtle">
                <span className="v-live h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                {stage}
              </div>
            )}

            {stopped && !busy && (
              <div className="v-enter mt-4 flex items-start gap-2.5 text-small text-fg-subtle">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-600" />
                <span className="leading-relaxed">
                  {stopped}{' '}
                  <Link to="/app/transactions"
                    className="font-medium text-brand-400 transition-colors hover:text-brand-300"
                  >
                    Transactions
                  </Link>
                </span>
              </div>
            )}

            {error && <div className="mt-4"><Alert>{error}</Alert></div>}
          </Section>

          <Rule />

          <Section title="Credentials" description="Proves which agent is acting.">
            <Field label="Bearer token">
              <Input value={token}
                onChange={(e) => saveToken(e.target.value)} placeholder="vla_…"
                className="font-mono text-small"
              />
            </Field>
            <p className="mt-3 text-label tracking-normal normal-case leading-relaxed text-fg-faint">
              Velora resolves this token to an agent and evaluates that identity. An{' '}
              <span className="font-mono">agent_id</span> in the request body is only a claim —
              a mismatch is blocked.
            </p>
          </Section>

          <Rule />

          <Section title="Catalog" description="Velora owns this data, not the agent.">
            <ul className="divide-y divide-ink-900">
              {(products || []).map((p) => (
                <li key={p.id} className="flex items-baseline gap-3 py-2">
                  <span className="tnum w-16 shrink-0 text-right text-small text-fg-muted">
                    {p.price_display}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-small text-fg-muted">
                    {p.name}
                  </span>
                  <Mono className="shrink-0">{p.merchant}</Mono>
                </li>
              ))}
            </ul>
          </Section>
        </div>

        {/* Result */}
        <div className="space-y-10">
          {basket ? (
            <Basket basket={basket} />
          ) : rec ? (
            <>
              <Section title="What the agent understood" description={
                  rec.intent.source === 'gemini'
                    ? 'Read by Gemini. It reads the request; it never picks the product.'
                    : 'Read by the offline rules parser.'
                }
              >
                <div className="flex flex-wrap gap-1.5">
                  {rec.intent.max_budget_paise && (
                    <Badge className="bg-ink-850 text-fg-muted ring-ink-800">
                      budget {inr(rec.intent.max_budget_paise)}
                    </Badge>
                  )}
                  {rec.intent.category && (
                    <Badge className="bg-ink-850 text-fg-muted ring-ink-800">
                      {rec.intent.category}
                    </Badge>
                  )}
                  {rec.intent.preferences.map((p) => (
                    <Badge key={p} className="bg-ink-850 text-fg-muted ring-ink-800">
                      {p.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                  {rec.intent.dish && (
                    <Badge className="bg-brand-500/12 text-brand-300 ring-brand-500/25">
                      {rec.intent.kind === 'cook' ? 'cooking' : 'for'} {rec.intent.dish}
                    </Badge>
                  )}
                  {(rec.intent.required_items || []).map((item) => (
                    <Badge key={item} className="bg-ink-850 text-fg-muted ring-ink-800">
                      {item}
                    </Badge>
                  ))}
                  {!rec.intent.dish && rec.intent.product_query && (
                    <Badge className="bg-ink-850 text-fg-muted ring-ink-800">
                      “{rec.intent.product_query}”
                    </Badge>
                  )}
                </div>

                {/* The agent declined, and says why. It used to fall silent
                    here and show an empty panel, which read as a bug rather
                    than as an answer. */}
                {rec.status && rec.status !== 'ok' && (
                  <div className="mt-5 max-w-lg">
                    <Alert kind={rec.status === 'needs_clarification' ? 'info' : 'warn'}>
                      {rec.rationale}
                    </Alert>
                    {rec.unavailable?.length > 0 && (
                      <p className="mt-3 text-label tracking-normal normal-case leading-relaxed text-fg-faint">
                        Not stocked by any merchant: {rec.unavailable.join(', ')}.
                      </p>
                    )}
                  </div>
                )}

                {rec.chosen && (
                  <>
                    <p className="mt-5 max-w-lg text-body leading-relaxed text-fg-muted">
                      {rec.rationale}
                    </p>
                    <div className="mt-5 space-y-1.5">
                      <Candidate item={rec.chosen} chosen />
                      {rec.alternatives.map((alt) => (
                        <Candidate key={alt.product_id} item={alt} />
                      ))}
                    </div>
                    {rec.unavailable?.length > 0 && (
                      <p className="mt-4 max-w-lg text-label tracking-normal normal-case leading-relaxed text-[color:var(--color-warn)]">
                        Partly filled. No merchant stocks: {rec.unavailable.join(', ')}.
                      </p>
                    )}
                    <p className="mt-4 max-w-lg text-label tracking-normal normal-case leading-relaxed text-fg-faint">
                      Scoring never considers your policy. The agent is allowed to want something
                      it cannot have — catching that is Velora's job.
                    </p>
                  </>
                )}
              </Section>

              {txnView ? (
                <>
                  <Rule />
                  <Section title="Velora's decision" description="Deterministic, and never made by a model."
                  >
                    <DecisionPanel txn={txnView.transaction} amountDisplay={txnView.amount_display} />
                  </Section>
                </>
              ) : (
                <Alert kind="info">
                  The agent made a choice but did not submit it. Press{' '}
                  <strong>Run agent</strong> to ask Velora for permission.
                </Alert>
              )}
            </>
          ) : (
            <Empty title="No run yet" hint="Give the agent a goal and watch it choose — then watch Velora decide whether it may."
            />
          )}
        </div>
      </div>
    </div>
  )
}
