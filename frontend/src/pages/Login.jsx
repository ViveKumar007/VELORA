import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Field, Input } from '../components/ui'
import { Logo } from '../components/Logo'
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
    <div className="v-page mx-auto flex min-h-[88vh] max-w-sm flex-col justify-center px-6">
      {/* The mark itself, at its real proportions. The previous gradient
          square with a letter in it was the one element on this screen that
          could have belonged to any product. */}
      <Link to="/" className="mb-10 inline-flex w-fit">
        <Logo size={24} live />
      </Link>

      <h1 className="text-title font-semibold tracking-tight text-balance text-fg">
        Define the boundary.
      </h1>
      <p className="mt-3 text-body leading-relaxed text-fg-muted">
        Sign in to set what your agents may spend, and to decide on what they cannot.
      </p>

      {/* No panel. The fields are the form; a border around them would only
          repeat what the whitespace already says. */}
      <form onSubmit={submit} className="mt-10 space-y-5">
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
      </form>

      <div className="mt-10 border-t border-ink-900 pt-5">
        <p className="text-label tracking-normal normal-case text-fg-faint">
          Demo account <span className="font-mono text-fg-subtle">demo@velora.local</span>
          <span className="mx-1.5 text-ink-700">/</span>
          <span className="font-mono text-fg-subtle">velora123</span>
        </p>
        <p className="mt-2.5 text-label tracking-normal normal-case text-fg-faint">
          Selling through Velora?{' '}
          <Link to="/merchant/login"
            className="font-medium text-brand-400 transition-colors hover:text-brand-300"
          >
            Merchant sign-in →
          </Link>
        </p>
      </div>
    </div>
  )
}
