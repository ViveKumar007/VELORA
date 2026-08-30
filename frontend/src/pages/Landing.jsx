import { Link } from 'react-router-dom'
import AuthFlow from '../components/AuthFlow'
import { Logo, LogoMark } from '../components/Logo'

const PRINCIPLES = [
  {
    title: 'Scoped authority',
    body: 'Define exactly what an agent may buy — amount, category, merchant, how many times, for how long. Everything outside the boundary is refused.',
  },
  {
    title: 'Intelligent approval',
    body: 'Safe purchases clear on their own. Anything above your threshold is held and escalated to you, with the reason stated plainly.',
  },
  {
    title: 'Complete transparency',
    body: 'Every check, decision and payment is recorded in a hash-chained audit trail. Edit any entry and the chain proves it.',
  },
]

const STAGES = [
  ['User', 'sets the boundary'],
  ['AI agent', 'chooses what to buy'],
  ['Velora', 'decides if it may'],
  ['Payment', 'only if approved'],
  ['Audit', 'permanently recorded'],
]

export default function Landing() {
  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-ink-900/80 bg-ink-1000/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Logo size={22} live />
          <nav className="flex items-center gap-2">
            <Link to="/merchant/login"
              className="rounded-lg px-3 py-1.5 text-small font-medium text-fg-subtle transition hover:text-fg"
            >
              For merchants
            </Link>
            <Link to="/login"
              className="rounded-lg bg-ink-800 px-3.5 py-1.5 text-small font-medium text-fg transition hover:bg-ink-700"
            >
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl items-center gap-14 px-6 py-20 lg:grid-cols-[1.05fr_1fr] lg:py-28">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-ink-800 bg-ink-900/60 px-3 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-400 v-live" />
              <span className="eyebrow text-fg-muted">
                Authorization infrastructure for agentic commerce
              </span>
            </div>

            <h1 className="text-5xl font-semibold tracking-tighter text-fg sm:text-6xl">
              Let AI act.
              <br />
              <span className="text-brand-400">Keep control.</span>
            </h1>

            <p className="mt-6 max-w-lg text-heading leading-relaxed text-fg-muted">
              Velora gives AI agents permission to act within limits you define — verifying
              every transaction before money moves.
            </p>

            <div className="mt-9 flex flex-wrap gap-3">
              <Link to="/login"
                className="rounded-xl bg-brand-500 px-5 py-2.5 text-small font-semibold text-white shadow-lg shadow-brand-500/20 transition hover:bg-brand-400"
              >
                Launch dashboard
              </Link>
              <a href="#how"
                className="rounded-xl border border-ink-700 bg-ink-900/60 px-5 py-2.5 text-small font-semibold text-fg transition hover:border-ink-600 hover:bg-ink-800"
              >
                See how it works
              </a>
            </div>

            <p className="mt-8 font-mono text-label tracking-normal normal-case text-fg-faint">
              AI decides what to do. Velora decides what it is allowed to do.
            </p>
          </div>

          <div className="drift">
            <AuthFlow />
          </div>
        </div>
      </section>

      {/* Thesis */}
      <section className="border-y border-ink-900">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="max-w-2xl text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
            AI should have authority.
            <span className="text-fg-faint"> Not unlimited access.</span>
          </h2>

          <div className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-ink-800 bg-ink-800 sm:grid-cols-3">
            {PRINCIPLES.map((p, i) => (
              <div key={p.title} className="bg-ink-950 p-7">
                <div className="mb-4 font-mono text-label tracking-normal normal-case text-brand-400">
                  0{i + 1}
                </div>
                <h3 className="text-body font-semibold text-fg">{p.title}</h3>
                <p className="mt-2.5 text-small leading-relaxed text-fg-subtle">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Flow */}
      <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-20">
        <h2 className="text-3xl font-semibold tracking-tight text-fg">
          One purchase, end to end
        </h2>
        <p className="mt-3 max-w-xl text-small leading-relaxed text-fg-subtle">
          The agent never touches the payment provider. Every request passes through the
          gate first, and a refusal has no route to money.
        </p>

        <ol className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STAGES.map(([title, body], i) => (
            <li key={title}
              className="relative rounded-xl border border-ink-800 bg-ink-950 p-5"
            >
              <div className="mb-3 flex items-center gap-2">
                <span className="grid h-6 w-6 place-items-center rounded-lg bg-brand-500/12 font-mono text-label tracking-normal normal-case text-brand-300 ring-1 ring-brand-500/25">
                  {i + 1}
                </span>
                {i < STAGES.length - 1 && (
                  <span className="hidden h-px flex-1 bg-gradient-to-r from-brand-500/40 to-transparent lg:block" />
                )}
              </div>
              <div className="text-small font-medium text-fg">{title}</div>
              <div className="mt-1 text-small text-fg-subtle">{body}</div>
            </li>
          ))}
        </ol>

        <div className="mt-14 rounded-2xl border border-ink-800 bg-ink-950 p-8">
          <div className="grid gap-8 sm:grid-cols-3">
            <Metric value="13" label="policy checks per decision" note="every one runs, every time" />
            <Metric value="0" label="paths from BLOCKED to paid" note="proven by graph traversal" />
            <Metric value="131" label="tests passing" note="incl. concurrency and tamper" />
          </div>
        </div>
      </section>

      <footer className="border-t border-ink-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-10">
          <div className="flex items-center gap-3">
            <LogoMark size={30} className="text-brand-500" />
            <span className="text-small text-fg-faint">Define the boundary. Let AI do the rest.</span>
          </div>
          <div className="flex gap-5 text-small text-fg-faint">
            <Link to="/login" className="hover:text-fg-muted">Buyer sign-in</Link>
            <Link to="/merchant/login" className="hover:text-fg-muted">Merchant sign-in</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

function Metric({ value, label, note }) {
  return (
    <div>
      <div className="tnum text-4xl font-semibold tracking-tight text-fg">{value}</div>
      <div className="mt-1.5 text-small text-fg-muted">{label}</div>
      <div className="mt-0.5 text-label tracking-normal normal-case text-fg-faint">{note}</div>
    </div>
  )
}
