import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Field, Input } from '../components/ui'
import { LogoMark } from '../components/Logo'
import { api } from '../lib/api'

/**
 * Merchant sign-in.
 *
 * Deliberately a different colour and a different promise from the buyer
 * door. A seller and a buyer have opposed interests, and the UI should make
 * it obvious which side of that line you are standing on.
 */
export default function MerchantLogin({ onSignedIn }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('demostore@velora.local')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const merchant = await api.merchantLogin(email, password)
      onSignedIn?.(merchant)
      navigate('/merchant', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="v-page mx-auto flex min-h-[88vh] max-w-sm flex-col justify-center px-6">
      {/* Same mark, seller's colour. The side of the deal you are on is
          signalled by hue and wording, not by a different logo. */}
      <Link to="/" className="mb-10 inline-flex w-fit items-center gap-3">
        <LogoMark size={36} className="text-[color:var(--color-ok)]" />
        <span className="leading-none">
          <span className="block text-heading font-semibold tracking-tight text-fg">velora</span>
          <span className="mt-1 block eyebrow text-[color:var(--color-ok)]/70 uppercase">
            Merchant
          </span>
        </span>
      </Link>

      <h1 className="text-title font-semibold tracking-tight text-balance text-fg">
        Sell to AI buyers.
      </h1>
      <p className="mt-3 text-body leading-relaxed text-fg-muted">
        Every purchase gated, explained and audited — and every refusal handed back with an
        alternative the buyer is allowed to accept.
      </p>

      <form onSubmit={submit} className="mt-10 space-y-5">
        <Field label="Merchant email">
          <Input type="email" value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </Field>

        <Field label="Password">
          <Input type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password" placeholder="••••••••"
            required
          />
        </Field>

        {error && <Alert>{error}</Alert>}

        <Button type="submit" variant="approve" disabled={busy} className="w-full">
          {busy ? 'Signing in…' : 'Sign in to console'}
        </Button>
      </form>

      <div className="mt-10 border-t border-ink-900 pt-5">
        <p className="text-label tracking-normal normal-case text-fg-faint">
          Demo merchants{' '}
          <span className="font-mono text-fg-subtle">blinkit@velora.local</span>,{' '}
          <span className="font-mono text-fg-subtle">demostore@velora.local</span>
          <span className="mx-1.5 text-ink-700">/</span>
          <span className="font-mono text-fg-subtle">merchant123</span>
        </p>
        <p className="mt-2.5 text-label tracking-normal normal-case text-fg-faint">
          Buying with an agent?{' '}
          <Link to="/login"
            className="font-medium text-brand-400 transition-colors hover:text-brand-300"
          >
            Buyer sign-in →
          </Link>
        </p>
      </div>
    </div>
  )
}
