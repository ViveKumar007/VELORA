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

      {/* Hero.

          The instrument on the right is the thesis: a real evaluation
          sequence running on a loop, refusing every third purchase. A gate
          that only ever says yes demonstrates nothing, so the refusal is
          part of the pitch rather than hidden from it. */}
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl items-center gap-16 px-6 py-20 lg:grid-cols-[1.05fr_1fr] lg:py-28">
          <div>
            <div className="mb-7 flex items-center gap-2.5">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-400 v-live" />
              <span className="eyebrow text-fg-subtle">
                Authorization infrastructure for agentic commerce
              </span>
            </div>

            <h1 className="text-display font-semibold text-balance text-fg">
              Let AI act.
              <br />
              <span className="text-brand-400">Keep control.</span>
            </h1>

            <p className="mt-7 max-w-md text-heading leading-relaxed text-fg-muted">
              Velora gives AI agents permission to act within limits you define — verifying
              every transaction before money moves.
            </p>

            <div className="mt-10 flex flex-wrap items-center gap-3">
              <Link to="/login"
                className="rounded-[var(--radius-sm)] bg-brand-500 px-5 py-2.5 text-small font-semibold text-white shadow-[var(--shadow-raise)] transition-all duration-[var(--dur-fast)] ease-[var(--ease-out-soft)] hover:bg-brand-400 active:translate-y-px"
              >
                Launch dashboard
              </Link>
              <a href="#how"
                className="group inline-flex items-center gap-2 px-1 py-2.5 text-small font-medium text-fg-muted transition-colors duration-[var(--dur-fast)] hover:text-fg"
              >
                See how it works
                <span className="transition-transform duration-[var(--dur-base)] ease-[var(--ease-out-soft)] group-hover:translate-x-0.5">
                  ↓
                </span>
              </a>
            </div>

            <p className="mt-10 border-l border-ink-800 pl-4 font-mono text-label tracking-normal normal-case leading-relaxed text-fg-faint">
              AI decides what to do.
              <br />
              Velora decides what it is allowed to do.
            </p>
          </div>

          <AuthFlow />
        </div>
      </section>

      {/* Thesis.

          Three independent properties, so they are set as three columns
          divided by hairlines rather than three numbered cards. Numbering
          them would assert a sequence that does not exist — scoped authority
          is not step one of transparency. */}
      <section className="border-y border-ink-900">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <h2 className="max-w-2xl text-title font-semibold tracking-tight text-balance text-fg">
            AI should have authority.
            <span className="text-fg-faint"> Not unlimited access.</span>
          </h2>

          <div className="mt-16 grid gap-12 sm:grid-cols-3 sm:gap-0">
            {PRINCIPLES.map((p, i) => (
              <div key={p.title}
                className={`sm:px-8 ${i === 0 ? 'sm:pl-0' : 'sm:border-l sm:border-ink-900'} ${
                  i === PRINCIPLES.length - 1 ? 'sm:pr-0' : ''
                }`}
              >
                <h3 className="text-heading font-medium text-fg">{p.title}</h3>
                <p className="mt-3 text-small leading-relaxed text-fg-subtle">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Flow.

          This one genuinely IS ordered — a purchase cannot be audited before
          it is decided — so the sequence is drawn as a single connected rail
          with a node per stage, in the language of the mark. Five separate
          boxes would have broken one continuous process into five unrelated
          facts. */}
      <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-24">
        <h2 className="text-title font-semibold tracking-tight text-fg">
          One purchase, end to end
        </h2>
        <p className="mt-4 max-w-xl text-body leading-relaxed text-fg-subtle">
          The agent never touches the payment provider. Every request passes through the
          gate first, and a refusal has no route to money.
        </p>

        <ol className="mt-16 grid gap-y-9 sm:grid-cols-2 lg:grid-cols-5 lg:gap-x-6">
          {STAGES.map(([title, body], i) => (
            <li key={title} className="relative lg:pr-6">
              {/* The rail. It stops at the last node rather than running off
                  the edge, because the sequence genuinely ends there. */}
              <span
                aria-hidden
                className={`absolute top-[5px] left-0 hidden h-px lg:block ${
                  i === STAGES.length - 1 ? 'w-0' : 'w-full'
                } ${i === 0 ? 'bg-brand-500/40' : 'bg-ink-800'}`}
              />
              <span
                aria-hidden
                className={`relative block h-[11px] w-[11px] rounded-full ring-4 ring-[color:var(--color-ink-1000)] ${
                  i === 0 ? 'bg-brand-500' : 'bg-ink-700'
                }`}
              />
              <div className="mt-5 text-small font-medium text-fg">{title}</div>
              <div className="mt-1.5 text-small leading-relaxed text-fg-subtle">{body}</div>
            </li>
          ))}
        </ol>

        {/* Bare figures on a rule. A statistic is not an object and does not
            need a container drawn around it. */}
        <div className="mt-24 grid gap-10 border-t border-ink-900 pt-10 sm:grid-cols-3">
          <Metric value="13" label="policy checks per decision" note="every one runs, every time" />
          <Metric value="0" label="paths from BLOCKED to paid" note="proven by graph traversal" />
          <Metric value="131" label="tests passing" note="incl. concurrency and tamper" />
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
      <div className="tnum text-display font-semibold text-fg">{value}</div>
      <div className="mt-2 text-small text-fg-muted">{label}</div>
      <div className="mt-1 text-label tracking-normal normal-case text-fg-faint">{note}</div>
    </div>
  )
}
