import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Field, Input } from '../components/ui'
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
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-6">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-[color:var(--color-ok)] to-[color:var(--color-ok-dim)] text-heading font-bold text-white">
          M
        </div>
        <h1 className="text-title font-semibold tracking-tight text-fg">
          Merchant console
        </h1>
        <p className="mt-1.5 text-small text-fg-subtle">
          Sell to AI buyers. Every purchase gated, explained and audited.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="space-y-4 rounded-xl border border-[color:var(--color-ok)]/20 bg-[color:var(--color-ok)]/[0.03] p-6"
      >
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

        <p className="pt-1 text-center text-label tracking-normal normal-case text-fg-faint">
          Demo merchants: <code className="font-mono">blinkit@velora.local</code>,{' '}
          <code className="font-mono">demostore@velora.local</code> /{' '}
          <code className="font-mono">merchant123</code>
        </p>
      </form>

      <p className="mt-6 text-center text-small text-fg-faint">
        Buying with an agent?{' '}
        <Link to="/login" className="font-medium text-brand-400 hover:text-brand-500">
          Buyer sign-in →
        </Link>
      </p>
    </div>
  )
}
