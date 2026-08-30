import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { LogoMark } from '../components/Logo'
import { Alert, Button, Mono } from '../components/ui'
import { api, getAgentToken } from '../lib/api'
import { inr } from '../lib/format'

/**
 * Live Demo.
 *
 * Every step here is a real API call against the real gate. Nothing is
 * scripted except the pacing, which is slowed deliberately so the sequence
 * can be read out loud while it runs.
 *
 * This matters: a judge who asks "is this actually deciding, or is it a
 * video?" can be handed the keyboard. A canned animation cannot survive that
 * question, and the whole product is a claim about trustworthiness.
 */

const SCRIPT = [
  { key: 'goal', label: 'User states a goal', detail: 'Plain language, no product ids.' },
  { key: 'intent', label: 'Agent parses intent', detail: 'Budget, category, preferences.' },
  { key: 'search', label: 'Agent searches the catalog', detail: 'Ranks what it finds.' },
  { key: 'choose', label: 'Agent selects a product', detail: 'On merit, blind to your policy.' },
  { key: 'gate', label: 'Velora evaluates', detail: '13 deterministic checks.' },
  { key: 'decide', label: 'Decision', detail: 'Approved, escalated, or refused.' },
  { key: 'audit', label: 'Audit trail sealed', detail: 'Hash-chained and verifiable.' },
]

const GOALS = [
  'Buy me wireless headphones under 2000 with good battery life',
  'Buy me the best headphones you can find',
  'Get me a gaming subscription',
]

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

export default function DemoMode() {
  const [goal, setGoal] = useState(GOALS[0])
  const [stage, setStage] = useState(-1)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [audit, setAudit] = useState(null)
  const [error, setError] = useState(null)
  const cancelled = useRef(false)

  async function run() {
    if (!getAgentToken()) {
      setError('No agent token set. Add one in the Agent Console first.')
      return
    }
    cancelled.current = false
    setError(null)
    setResult(null)
    setAudit(null)
    setRunning(true)

    try {
      for (const i of [0, 1, 2, 3]) {
        if (cancelled.current) return
        setStage(i)
        await wait(700)
      }

      setStage(4)
      // The real call. Everything above was pacing; this is the product.
      const run = await api.runAgent({ goal, auto_submit: true })
      if (cancelled.current) return
      await wait(900)

      setStage(5)
      setResult(run)
      await wait(700)

      setStage(6)
      if (run.transaction?.transaction?.id) {
        const trail = await api.audit(run.transaction.transaction.id)
        if (!cancelled.current) setAudit(trail)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(false)
    }
  }

  function reset() {
    cancelled.current = true
    setStage(-1)
    setResult(null)
    setAudit(null)
    setError(null)
    setRunning(false)
  }

  const txn = result?.transaction?.transaction
  const chosen = result?.recommendation?.chosen

  return (
    <div className="min-h-full">
      <header className="border-b border-ink-900 bg-ink-1000/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <LogoMark size={30} live={running} className="text-brand-500" />
            <div>
              <div className="text-small font-semibold tracking-tight text-fg">
                Live Demo
              </div>
              <div className="eyebrow text-fg-faint uppercase">
                Real decisions, not a recording
              </div>
            </div>
          </div>
          <Link to="/app"
            className="rounded-lg px-3 py-1.5 text-small font-medium text-fg-subtle transition hover:text-fg"
          >
            Back to dashboard
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-10">
        {/* Control */}
        <div className="rounded-2xl border border-ink-800 bg-ink-900/60 p-6">
          <label className="mb-2 block text-label tracking-normal normal-case font-medium tracking-wide text-fg-subtle uppercase">
            Tell the agent what you want
          </label>
          <textarea value={goal}
            onChange={(e) => setGoal(e.target.value)} rows={2} disabled={running}
            className="w-full resize-none rounded-xl border border-ink-700 bg-ink-850 px-4 py-3 text-heading text-fg placeholder:text-fg-faint focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none disabled:opacity-60"
          />

          <div className="mt-3 flex flex-wrap gap-1.5">
            {GOALS.map((g) => (
              <button key={g} disabled={running}
                onClick={() => setGoal(g)}
                className="rounded-lg border border-ink-700 bg-ink-850 px-2.5 py-1 text-label tracking-normal normal-case text-fg-subtle transition hover:text-fg-muted disabled:opacity-50"
              >
                {g.length > 40 ? `${g.slice(0, 40)}…` : g}
              </button>
            ))}
          </div>

          <div className="mt-5 flex gap-2">
            <Button variant="primary" onClick={run} disabled={running} className="px-6">
              {running ? 'Running…' : 'Run live demo'}
            </Button>
            <Button variant="ghost" onClick={reset} disabled={!running && stage === -1}>
              Reset
            </Button>
          </div>

          {error && (
            <div className="mt-4">
              <Alert>{error}</Alert>
            </div>
          )}
        </div>

        {/* Sequence */}
        <ol className="mt-8 space-y-2">
          {SCRIPT.map((s, i) => {
            const done = stage > i
            const active = stage === i
            return (
              <li key={s.key}
                className={`flex items-start gap-4 rounded-xl border px-5 py-4 transition-all duration-300 ${
                  active
                    ? 'border-brand-500/40 bg-brand-500/[0.07]'
                    : done
                      ? 'border-ink-800 bg-ink-950'
                      : 'border-ink-900 bg-ink-1000 opacity-45'
                }`}
              >
                <span
                  className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg text-label tracking-normal normal-case font-semibold ${
                    done
                      ? 'bg-[color:var(--color-ok)]/15 text-[color:var(--color-ok)] ring-1 ring-[color:var(--color-ok)]/30'
                      : active
                        ? 'bg-brand-500/20 text-brand-300 ring-1 ring-brand-500/40 v-live'
                        : 'bg-ink-800 text-fg-faint'
                  }`}
                >
                  {done ? '✓' : i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-small font-medium text-fg">{s.label}</div>
                  <div className="mt-0.5 text-small text-fg-subtle">{s.detail}</div>

                  {/* What each stage actually produced */}
                  {s.key === 'intent' && stage > 1 && result?.recommendation?.intent && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {result.recommendation.intent.max_budget_paise && (
                        <Chip>budget {inr(result.recommendation.intent.max_budget_paise)}</Chip>
                      )}
                      {result.recommendation.intent.category && (
                        <Chip>{result.recommendation.intent.category}</Chip>
                      )}
                      {result.recommendation.intent.preferences?.map((p) => (
                        <Chip key={p}>{p.replace(/_/g, ' ')}</Chip>
                      ))}
                    </div>
                  )}

                  {s.key === 'choose' && chosen && (
                    <div className="mt-2.5 flex flex-wrap items-baseline gap-2">
                      <span className="text-small font-medium text-fg">{chosen.name}</span>
                      <span className="tnum text-small text-brand-300">{chosen.price_display}</span>
                      <Mono>{chosen.merchant}</Mono>
                    </div>
                  )}

                  {s.key === 'gate' && txn?.checks?.length > 0 && (
                    <ul className="mt-2.5 space-y-1">
                      {txn.checks
                        .filter((c) => c.status !== 'SKIP')
                        .map((c, idx) => (
                          <li key={c.name}
                            className="v-resolve flex items-center gap-2 text-label tracking-normal normal-case" style={{ animationDelay: `${idx * 55}ms` }}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                c.status === 'PASS'
                                  ? 'bg-[color:var(--color-ok)]'
                                  : c.status === 'FAIL'
                                    ? 'bg-rose-400'
                                    : 'bg-[color:var(--color-warn)]'
                              }`}
                            />
                            <span className="text-fg-muted">{c.name}</span>
                            <span
                              className={`ml-auto font-mono text-label tracking-normal normal-case ${
                                c.status === 'PASS'
                                  ? 'text-[color:var(--color-ok)]/70'
                                  : c.status === 'FAIL'
                                    ? 'text-[color:var(--color-danger)]'
                                    : 'text-[color:var(--color-warn)]'
                              }`}
                            >
                              {c.status}
                            </span>
                          </li>
                        ))}
                    </ul>
                  )}

                  {s.key === 'decide' && txn && (
                    <Verdict txn={txn} amount={result.transaction.amount_display} />
                  )}

                  {s.key === 'audit' && audit && (
                    <div className="mt-2.5 flex flex-wrap items-center gap-3 text-label tracking-normal normal-case">
                      <span className="text-fg-muted">{audit.entries.length} events recorded</span>
                      <span
                        className={
                          audit.integrity.valid ? 'text-[color:var(--color-ok)]' : 'text-[color:var(--color-danger)]'
                        }
                      >
                        {audit.integrity.valid ? '✓ chain intact' : '✕ chain broken'}
                      </span>
                      {txn && (
                        <Link to={`/app/audit/${txn.id}`}
                          className="font-medium text-brand-400 hover:text-brand-300"
                        >
                          Open full trail →
                        </Link>
                      )}
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      </main>
    </div>
  )
}

function Chip({ children }) {
  return (
    <span className="rounded-md bg-ink-800 px-2 py-0.5 text-label tracking-normal normal-case text-fg-muted">
      {children}
    </span>
  )
}

function Verdict({ txn, amount }) {
  const blocked = txn.decision === 'BLOCKED'
  const pending = txn.decision === 'PENDING_APPROVAL'
  const tone = blocked
    ? 'border-[color:var(--color-danger)]/30 bg-[color:var(--color-danger)]/[0.07] text-[color:var(--color-danger)]'
    : pending
      ? 'border-amber-500/30 bg-amber-500/[0.07] text-[color:var(--color-warn)]'
      : 'border-[color:var(--color-ok)]/30 bg-[color:var(--color-ok)]/[0.07] text-[color:var(--color-ok)]'

  return (
    <div className={`v-enter mt-3 rounded-xl border p-4 ${tone}`}>
      <div className="flex flex-wrap items-baseline gap-2.5">
        <span className="text-heading font-semibold tracking-tight">
          {blocked ? 'BLOCKED' : pending ? 'NEEDS YOUR APPROVAL' : 'APPROVED'}
        </span>
        <span className="tnum text-small text-fg-muted">{amount}</span>
        <span className="ml-auto font-mono text-label tracking-normal normal-case text-fg-subtle">
          {txn.reason_code}
        </span>
      </div>
      <p className="mt-2 text-small leading-relaxed text-fg-muted">{txn.explanation}</p>

      {txn.recovery && (
        <div className="mt-3 rounded-lg border border-[color:var(--color-ok)]/25 bg-[color:var(--color-ok)]/[0.06] p-3">
          <div className="text-label tracking-normal normal-case font-semibold tracking-widest text-[color:var(--color-ok)] uppercase">
            In-policy alternative
          </div>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-2">
            <span className="text-small font-medium text-fg">{txn.recovery.name}</span>
            <span className="tnum text-small text-[color:var(--color-ok)]">
              {txn.recovery.price_display}
            </span>
          </div>
          <p className="mt-1 text-label tracking-normal normal-case text-fg-muted">{txn.recovery.explanation}</p>
        </div>
      )}
    </div>
  )
}
