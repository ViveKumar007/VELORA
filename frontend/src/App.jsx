import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useEventStream } from './hooks/useLive'
import { useLiveResource } from './hooks/useLive'
import { api } from './lib/api'
import AgentConsole from './pages/AgentConsole'
import Approvals from './pages/Approvals'
import AuditTrail from './pages/AuditTrail'
import Dashboard from './pages/Dashboard'
import Policies from './pages/Policies'
import Transactions from './pages/Transactions'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/policies', label: 'Authorizations' },
  { to: '/console', label: 'Agent Console' },
  { to: '/approvals', label: 'Approvals', badge: true },
  { to: '/transactions', label: 'Transactions' },
]

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-600 text-[13px] font-bold text-white">
        V
      </div>
      <div className="leading-tight">
        <div className="text-sm font-semibold tracking-tight text-zinc-100">Velora</div>
        <div className="text-[10px] text-zinc-600">Define the boundary.</div>
      </div>
    </div>
  )
}

export default function App() {
  const connected = useEventStream(() => {})
  const { data: approvals } = useLiveResource(() => api.approvals(), [], { poll: 20000 })
  const pendingCount = approvals?.length || 0

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-20 border-b border-ink-800 bg-ink-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-8 px-6 py-3">
          <Logo />

          <nav className="flex flex-1 items-center gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `relative rounded-lg px-3 py-1.5 text-[13px] font-medium transition ${
                    isActive
                      ? 'bg-ink-800 text-zinc-100'
                      : 'text-zinc-500 hover:bg-ink-900 hover:text-zinc-300'
                  }`
                }
              >
                {item.label}
                {item.badge && pendingCount > 0 && (
                  <span className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500/20 px-1 text-[10px] font-semibold text-amber-300 ring-1 ring-amber-500/40">
                    {pendingCount}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                connected ? 'live-dot bg-emerald-400' : 'bg-zinc-600'
              }`}
            />
            <span className="text-[11px] text-zinc-600">{connected ? 'Live' : 'Offline'}</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-7">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/policies" element={<Policies />} />
          <Route path="/console" element={<AgentConsole />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/audit/:id" element={<AuditTrail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="mx-auto max-w-7xl px-6 pb-8 pt-2">
        <p className="text-[11px] text-zinc-700">
          AI decides what to do. Velora decides what it is allowed to do.
        </p>
      </footer>
    </div>
  )
}
