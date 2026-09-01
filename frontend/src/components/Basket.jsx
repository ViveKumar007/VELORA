import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Mono, Rule, Section, Status } from './ui'
import { DecisionPanel } from './Decision'
import { api } from '../lib/api'
import { openCheckout } from '../lib/razorpay'
import { inr } from '../lib/format'

/**
 * A shopping list you can edit before committing to it.
 *
 * The single-purchase console answers "may I buy this?". A basket answers
 * "may I buy these?", and the person confirming needs to see the whole list,
 * drop what they do not want, and know the total *before* the gate is asked.
 * So the list is editable and inert until Confirm — nothing reaches Velora
 * while you are still deciding.
 *
 * A row is one ingredient, not one card. Excluded rows stay visible and go
 * quiet rather than disappearing, because a list that reflows as you uncheck
 * things is hard to work down.
 */

/** One line: include toggle, what it answers, the product, the price. */
function Line({ line, selected, onToggle, onSwap }) {
  const [open, setOpen] = useState(false)
  const alternatives = line.alternatives || []

  return (
    <li className={`py-3 transition-opacity duration-[var(--dur-base)] ${selected ? '' : 'opacity-40'}`}>
      <div className="flex items-baseline gap-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Include ${line.name}`}
          className="mt-1 h-3.5 w-3.5 shrink-0 cursor-pointer accent-[color:var(--color-brand-500)]"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="eyebrow text-fg-faint">{line.item}</span>
            <span className="min-w-0 truncate text-small text-fg">{line.name}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <Mono>{line.merchant}</Mono>
            {line.quantity && <Mono>{line.quantity}</Mono>}
            {alternatives.length > 0 && (
              <button
                onClick={() => setOpen((v) => !v)}
                className="text-label tracking-normal normal-case text-brand-400 transition-colors hover:text-brand-300"
              >
                {open ? 'hide' : `${alternatives.length} alternative${alternatives.length === 1 ? '' : 's'}`}
              </button>
            )}
          </div>

          {open && (
            <ul className="v-enter mt-2.5 space-y-1 border-l border-ink-800 pl-3">
              {alternatives.map((alt) => (
                <li key={alt.product_id} className="flex items-baseline gap-3">
                  <button
                    onClick={() => {
                      onSwap(alt)
                      setOpen(false)
                    }}
                    className="min-w-0 flex-1 truncate text-left text-small text-fg-subtle transition-colors hover:text-fg"
                  >
                    {alt.name}
                  </button>
                  <span className="tnum shrink-0 text-small text-fg-muted">{alt.price_display}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <span className="tnum shrink-0 text-small font-medium text-fg">{line.price_display}</span>
      </div>
    </li>
  )
}

export default function Basket({ basket, onAuthorized }) {
  // Everything the catalog could fill starts selected; the person removes
  // what they do not want rather than assembling from nothing.
  const [selected, setSelected] = useState(() => new Set())
  const [swaps, setSwaps] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [txn, setTxn] = useState(null)
  const [paying, setPaying] = useState(false)

  useEffect(() => {
    setSelected(new Set((basket?.lines || []).map((l) => l.item)))
    setSwaps({})
    setTxn(null)
    setError(null)
  }, [basket])

  // A swap replaces the product on a line without changing what the line
  // answers, so the list keeps its shape.
  const lines = useMemo(
    () => (basket?.lines || []).map((l) => (swaps[l.item] ? { ...l, ...swaps[l.item] } : l)),
    [basket, swaps],
  )

  const chosen = lines.filter((l) => selected.has(l.item))
  const total = chosen.reduce((sum, l) => sum + l.price_paise, 0)

  if (!basket) return null

  if (basket.status === 'needs_clarification') {
    return <Alert kind="info">{basket.message}</Alert>
  }
  if (basket.status === 'no_match' || !basket.lines?.length) {
    return <Alert kind="warn">{basket.message}</Alert>
  }

  function toggle(item) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(item) ? next.delete(item) : next.add(item)
      return next
    })
  }

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      const out = await api.basketRequest({
        product_ids: chosen.map((l) => l.product_id),
        idempotency_key: `bsk_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
        label: basket.intent?.dish
          ? `${basket.intent.dish} — ${chosen.length} items`
          : `Basket of ${chosen.length} items`,
        rationale: `Assembled for: ${basket.intent?.raw_text || 'a shopping request'}.`,
      })
      setTxn(out)
      onAuthorized?.(out)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  /**
   * Pay the authorized basket. One transaction, so one payment — the same
   * path a single purchase takes, with no special casing.
   */
  async function pay() {
    setPaying(true)
    setError(null)
    try {
      const created = await api.pay(txn.transaction.id)
      setTxn(created)

      const cfg = await api.config()
      if (cfg.payment_provider === 'razorpay') {
        const result = await openCheckout({
          keyId: cfg.razorpay_key_id,
          orderId: created.transaction.payment_order_id,
          amountPaise: created.transaction.requested_amount_paise,
          description: created.transaction.product_name,
          methods: cfg.payment_methods,
        })
        setTxn(await api.confirmPayment(created.transaction.id, result))
      } else {
        setTxn(await api.simulatePayment(created.transaction.id, true))
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setPaying(false)
    }
  }

  const state = txn?.transaction?.state
  const payable = state === 'APPROVED' || state === 'PAYMENT_CREATION_FAILED'
  const settled = state === 'PAYMENT_SUCCESS'

  return (
    <div className="space-y-8">
      <Section
        title="Shopping list"
        description={
          basket.intent?.dish
            ? `Everything needed for ${basket.intent.dish}.`
            : 'Everything the request asked for.'
        }
      >
        <ul className="divide-y divide-ink-900">
          {lines.map((line) => (
            <Line
              key={line.item}
              line={line}
              selected={selected.has(line.item)}
              onToggle={() => toggle(line.item)}
              onSwap={(alt) => setSwaps((prev) => ({ ...prev, [line.item]: alt }))}
            />
          ))}
        </ul>

        {/* Ingredients no merchant stocks. Shown, not hidden: knowing the
            basket is incomplete is part of deciding whether to buy it. */}
        {basket.unavailable?.length > 0 && (
          <ul className="mt-1 divide-y divide-ink-900 border-t border-ink-900">
            {basket.unavailable.map((item) => (
              <li key={item} className="flex items-baseline gap-3 py-3">
                <span className="h-3.5 w-3.5 shrink-0" aria-hidden />
                <span className="eyebrow text-fg-faint">{item}</span>
                <span className="text-small text-fg-faint">not stocked by any merchant</span>
              </li>
            ))}
          </ul>
        )}

        <Rule className="mt-5" />

        <div className="mt-5 flex flex-wrap items-baseline justify-between gap-4">
          <div className="text-small text-fg-muted">
            {chosen.length} of {lines.length} selected
            {basket.merchants?.length > 1 && (
              <span className="text-fg-faint"> · {basket.merchants.join(' + ')}</span>
            )}
          </div>
          <div className="text-right">
            <div className="tnum text-title font-semibold tracking-tight text-fg">{inr(total)}</div>
            <div className="text-label tracking-normal normal-case text-fg-faint">
              judged as one purchase
            </div>
          </div>
        </div>

        {error && (
          <div className="mt-5">
            <Alert>{error}</Alert>
          </div>
        )}

        {!txn && (
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button variant="primary" onClick={confirm} disabled={busy || !chosen.length} className="px-6">
              {busy ? 'Asking Velora…' : `Confirm and request authorization · ${inr(total)}`}
            </Button>
            {!chosen.length && <Status state="muted">nothing selected</Status>}
          </div>
        )}
      </Section>

      {txn && (
        <>
          <Rule />
          <Section
            title="Velora's decision"
            description="One decision for the whole basket. Deterministic, and never made by a model."
          >
            <DecisionPanel
              txn={txn.transaction}
              amountDisplay={txn.amount_display}
              footer={
                <div className="flex flex-wrap items-center gap-3">
                  {payable && (
                    <Button variant="approve" onClick={pay} disabled={paying}>
                      {paying ? 'Paying…' : `Pay ${txn.amount_display}`}
                    </Button>
                  )}
                  {state === 'PENDING_APPROVAL' && (
                    <Link
                      to="/app/approvals"
                      className="text-label tracking-normal normal-case font-medium text-brand-400 transition-colors hover:text-brand-300"
                    >
                      Approve it →
                    </Link>
                  )}
                  {settled && <Status state="ok">paid</Status>}
                </div>
              }
            />
          </Section>
        </>
      )}
    </div>
  )
}
