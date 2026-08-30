import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Field, Input } from '../components/ui'
import { api } from '../lib/api'

/**
 * Buyer sign-in.
 *
 * Visually distinct from the merchant door on purpose — brand violet, "define
 * the boundary" framing. Someone who lands on the wrong one should be able to
 * tell at a glance, before they type a password into it.
 */
export default function Login({ onSignedIn }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('demo@velora.local')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const user = await api.login(email, password)
      onSignedIn?.(user)
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-md flex-col justify-center px-6">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 text-heading font-bold text-white">
          V
        </div>
        <h1 className="text-title font-semibold tracking-tight text-fg">
          Sign in to Velora
        </h1>
        <p className="mt-1.5 text-small text-fg-subtle">
          Define what your agents may spend, and approve what they cannot.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="space-y-4 rounded-xl border border-ink-800 bg-ink-900/60 p-6"
      >
        <Field label="Email">
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

        <Button type="submit" variant="primary" disabled={busy} className="w-full">
          {busy ? 'Signing in…' : 'Sign in'}
        </Button>

        <p className="pt-1 text-center text-label tracking-normal normal-case text-fg-faint">
          Demo account: <code className="font-mono">demo@velora.local</code> /{' '}
          <code className="font-mono">velora123</code>
        </p>
      </form>

      <p className="mt-6 text-center text-small text-fg-faint">
        Selling through Velora?{' '}
        <Link to="/merchant/login" className="font-medium text-brand-400 hover:text-brand-500">
          Merchant sign-in →
        </Link>
      </p>
    </div>
  )
}
