import { useNavigate } from 'react-router-dom'
import { Button, Empty, Figure, Loading, Mono, Rule, Section, Status } from '../components/ui'
import { useLiveResource } from '../hooks/useLive'
import { api } from '../lib/api'
import { clearSession, setProfile } from '../lib/session'
import { inr, paise } from '../lib/format'

/**
 * The seller's view.
 *
 * The figure this page exists for is "alternatives offered": purchases the
 * gate refused where an in-policy substitute was returned instead. Those are
 * sales a plain guardrail would simply have lost, and they are the reason a
 * merchant should want to be gated rather than merely tolerate it.
 */
export default function MerchantConsole() {
  const navigate = useNavigate()
  const { data, loading, error } = useLiveResource(() => api.merchantConsole(), [], {
    poll: 10000,
  })
  const { data: catalog } = useLiveResource(() => api.agentCatalog(), [], { poll: 0 })

  function signOut() {
    clearSession('merchant')
    setProfile('merchant', null)
    navigate('/merchant/login', { replace: true })
  }

  if (loading && !data) return <Loading label="Opening console" />
  if (error) {
    navigate('/merchant/login', { replace: true })
    return null
  }

  const m = data.merchant
  const mine = (catalog?.items || []).filter((i) => i.merchant === m.name)

  return (
    <div className="v-page space-y-12">
      <header className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <h1 className="text-title font-semibold tracking-tight text-fg">{m.name}</h1>
          <p className="mt-2 max-w-md text-small text-fg-muted">{m.description}</p>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <Mono>{m.email}</Mono>
            {m.agent_ready && <Status state="ok">agent-ready</Status>}
          </div>
        </div>
        <Button variant="ghost" onClick={signOut}>
          Sign out
        </Button>
      </header>

      <Rule />

      <div className="grid grid-cols-2 gap-x-8 gap-y-7 sm:grid-cols-4">
        <Figure value={data.products} label="Products listed" note="in the agent catalog" />
        <Figure value={paise(data.revenue_paise)} label="Settled revenue" tone={data.revenue_paise ? 'ok' : 'default'} note={`${data.paid} paid`}
        />
        <Figure value={data.blocked} label="Blocked by policy" tone={data.blocked ? 'danger' : 'default'} note="buyer outside their limits"
        />
        <Figure value={data.recovery_offered} label="Alternatives offered" tone={data.recovery_offered ? 'warn' : 'default'} note="sales a plain guardrail loses"
        />
      </div>

      {data.blocked > 0 && (
        <p className="max-w-2xl text-body leading-relaxed text-fg-muted">
          <span className="text-fg">
            {data.recovery_offered} of your {data.blocked} blocked{' '}
            {data.blocked === 1 ? 'purchase' : 'purchases'}
          </span>{' '}
          came back with an in-policy alternative for the buyer. A guardrail that only says
          no would have lost those outright.
        </p>
      )}

      <Section title="Agent-readable catalog" description="What an AI buyer reads when it discovers this storefront."
      >
        {!mine.length ? (
          <Empty title="No products listed" />
        ) : (
          <div className="edge-fade -mx-2 overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead>
                <tr className="border-b border-ink-800">
                  {['Product', 'Price', 'Category', 'Rating', 'product_id'].map((h) => (
                    <th key={h} className="eyebrow px-2 pb-2.5 text-left font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-900">
                {mine.map((item) => (
                  <tr key={item.product_id} className="transition-colors hover:bg-ink-950">
                    <td className="px-2 py-3 text-small text-fg">{item.name}</td>
                    <td className="tnum px-2 py-3 text-small text-fg-muted">
                      {inr(item.price_paise)}
                    </td>
                    <td className="px-2 py-3">
                      <Mono>{item.category}</Mono>
                    </td>
                    <td className="tnum px-2 py-3 text-small text-fg-muted">{item.rating}</td>
                    <td className="px-2 py-3">
                      <Mono>{item.product_id}</Mono>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-6 max-w-2xl text-small leading-relaxed text-fg-faint">
          Published at <span className="font-mono text-fg-subtle">GET /api/merchants/catalog</span>{' '}
          together with the purchase protocol. An AI buyer reads that one document and knows
          both what you sell and exactly how to transact — including that every purchase is
          gated and may be refused.
        </p>
      </Section>
    </div>
  )
}
