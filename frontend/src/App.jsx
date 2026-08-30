import { useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Logo, LogoMark } from './components/Logo'
import { useEventStream, useLiveResource } from './hooks/useLive'
import { api } from './lib/api'
import { clearSession, getProfile, getSession, setProfile } from './lib/session'
import AgentConsole from './pages/AgentConsole'
import Agents from './pages/Agents'
import Approvals from './pages/Approvals'
import AuditTrail from './pages/AuditTrail'
import Dashboard from './pages/Dashboard'
import DemoMode from './pages/DemoMode'
import Landing from './pages/Landing'
import Login from './pages/Login'
import MerchantConsole from './pages/MerchantConsole'
import MerchantLogin from './pages/MerchantLogin'
import Policies from './pages/Policies'
import Transactions from './pages/Transactions'

const NAV = [
  { to: '/app', label: 'Overview', end: true },
  { to: '/app/agents', label: 'Agents' },
  { to: '/app/console', label: 'Agent Console' },
  { to: '/app/policies', label: 'Authorization' },
  { to: '/app/approvals', label: 'Approvals', badge: true },
  { to: '/app/transactions', label: 'Transactions' },
]

function greeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

/** Buyer shell: sidebar command centre. */
function BuyerShell({ children }) {
  const navigate = useNavigate()
  const [drawer, setDrawer] = useState(false)
  const connected = useEventStream(() => {})
  const { data: approvals } = useLiveResource(() => api.approvals(), [], { poll: 20000 })
  const profile = getProfile('user')
  const pending = approvals?.length || 0

  function signOut() {
    clearSession('user')
    setProfile('user', null)
    navigate('/login', { replace: true })
  }

  const nav = (
    <nav className="flex flex-col gap-0.5">
      {NAV.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end}
          onClick={() => setDrawer(false)}
          className={({ isActive }) =>
            `flex items-center justify-between rounded-lg px-3 py-2 text-small font-medium transition ${
              isActive
                ? 'bg-brand-500/12 text-brand-300 ring-1 ring-brand-500/20'
                : 'text-fg-subtle hover:bg-ink-900 hover:text-fg'
            }`
          }
        >
          {item.label}
          {item.badge && pending > 0 && (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[color:var(--color-warn)]/20 px-1 text-label tracking-normal normal-case font-semibold text-[color:var(--color-warn)] ring-1 ring-[color:var(--color-warn)]/40">
              {pending}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="flex min-h-full">
      {/* Sidebar — desktop */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-ink-900 bg-ink-1000 px-4 py-5 lg:flex">
        <NavLink to="/" className="mb-8 px-1">
          <Logo size={22} live={connected} />
        </NavLink>
        {nav}
        <div className="mt-auto space-y-2 pt-6">
          <NavLink to="/app/demo"
            onClick={() => setDrawer(false)}
            className="block rounded-lg border border-brand-500/25 bg-brand-500/[0.07] px-3 py-2.5 text-small font-medium text-brand-300 transition hover:bg-brand-500/12"
          >
            ▸ Live Demo
          </NavLink>
          <div className="flex items-center justify-between rounded-lg px-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-label tracking-normal normal-case text-fg-muted">
                {profile?.name || 'Signed in'}
              </div>
              <div className="truncate text-label tracking-normal normal-case text-fg-faint">{profile?.email}</div>
            </div>
            <button
              onClick={signOut}
              className="ml-2 shrink-0 text-label tracking-normal normal-case text-fg-faint transition hover:text-fg-muted"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Drawer — mobile */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setDrawer(false)}
          />
          <aside className="v-enter absolute top-0 bottom-0 left-0 w-64 border-r border-ink-800 bg-ink-1000 px-4 py-5">
            <div className="mb-8 px-1">
              <Logo size={22} live={connected} />
            </div>
            {nav}
            <div className="mt-8">
              <NavLink to="/app/demo"
                onClick={() => setDrawer(false)}
                className="block rounded-lg border border-brand-500/25 bg-brand-500/[0.07] px-3 py-2.5 text-small font-medium text-brand-300"
              >
                ▸ Live Demo
              </NavLink>
              <button
                onClick={signOut}
                className="mt-2 w-full rounded-lg px-3 py-2 text-left text-small text-fg-subtle"
              >
                Sign out
              </button>
            </div>
          </aside>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 border-b border-ink-900 bg-ink-1000/85 backdrop-blur-xl">
          <div className="flex items-center gap-4 px-5 py-3.5 lg:px-8">
            <button
              onClick={() => setDrawer(true)}
              className="rounded-lg p-1.5 text-fg-subtle transition hover:bg-ink-900 hover:text-fg lg:hidden" aria-label="Open navigation"
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M2 5h14M2 9h14M2 13h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>

            <div className="min-w-0 flex-1">
              <div className="truncate text-small font-medium text-fg">
                {greeting()}
                {profile?.name ? `, ${profile.name.split(' ')[0]}` : ''}
              </div>
              <div className="truncate text-label tracking-normal normal-case text-fg-faint">
                {pending > 0
                  ? `${pending} purchase${pending === 1 ? '' : 's'} awaiting your approval.`
                  : 'Your agents are operating within authorized limits.'}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  connected ? 'v-live bg-[color:var(--color-ok)]' : 'bg-ink-700'
                }`}
              />
              <span className="hidden text-label tracking-normal normal-case text-fg-faint sm:inline">
                {connected ? 'Live' : 'Offline'}
              </span>
              <div className="ml-2 grid h-7 w-7 place-items-center rounded-full bg-ink-800 text-label tracking-normal normal-case font-semibold text-fg-muted">
                {(profile?.name || 'U').charAt(0).toUpperCase()}
              </div>
            </div>
          </div>
        </header>

        <main className="px-5 py-7 lg:px-8">{children}</main>
      </div>
    </div>
  )
}

/** Merchant shell: same structure, unmistakably a different side of the deal. */
function MerchantShell({ children }) {
  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-20 border-b border-[color:var(--color-ok)]/15 bg-ink-1000/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <LogoMark size={30} className="text-[color:var(--color-ok)]" />
            <div className="leading-none">
              <div className="text-heading font-semibold tracking-tight text-fg">velora</div>
              <div className="mt-1 eyebrow text-[color:var(--color-ok)]/70 uppercase">
                Merchant console
              </div>
            </div>
          </div>
          <span className="text-label tracking-normal normal-case text-fg-faint">Seller view</span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  )
}

function Guard({ kind, children }) {
  if (!getSession(kind)) {
    return <Navigate to={kind === 'merchant' ? '/merchant/login' : '/login'} replace />
  }
  return children
}

export default function App() {
  const [, bumpState] = useState(0)
  const bump = () => bumpState((n) => n + 1)

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login onSignedIn={bump} />} />
      <Route path="/merchant/login" element={<MerchantLogin onSignedIn={bump} />} />

      <Route path="/merchant" element={
          <Guard kind="merchant">
            <MerchantShell>
              <MerchantConsole />
            </MerchantShell>
          </Guard>
        }
      />

      <Route path="/app/demo" element={
          <Guard kind="user">
            <DemoMode />
          </Guard>
        }
      />

      <Route path="/app/*" element={
          <Guard kind="user">
            <BuyerShell>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/policies" element={<Policies />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="/console" element={<AgentConsole />} />
                <Route path="/approvals" element={<Approvals />} />
                <Route path="/transactions" element={<Transactions />} />
                <Route path="/audit/:id" element={<AuditTrail />} />
                <Route path="*" element={<Navigate to="/app" replace />} />
              </Routes>
            </BuyerShell>
          </Guard>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
