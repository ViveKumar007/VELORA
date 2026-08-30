/**
 * Razorpay Checkout integration.
 *
 * The browser never sees the key secret — only the publishable key id, which
 * Razorpay designs to be public. Card details are entered inside Razorpay's
 * own hosted iframe, so they never touch our page or our server. That is not
 * a convenience: RBI's card-on-file rules forbid us from storing them.
 *
 * The result Checkout hands back is untrusted. It goes straight to
 * /payment/confirm, where the server verifies the signature before anything
 * settles.
 */

const CHECKOUT_SRC = 'https://checkout.razorpay.com/v1/checkout.js'

let loaderPromise = null

/** Load checkout.js once, lazily. Resolves to the global Razorpay constructor. */
export function loadCheckout() {
  if (window.Razorpay) return Promise.resolve(window.Razorpay)
  if (loaderPromise) return loaderPromise

  loaderPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = CHECKOUT_SRC
    script.async = true
    script.onload = () =>
      window.Razorpay
        ? resolve(window.Razorpay)
        : reject(new Error('Razorpay Checkout loaded but did not register.'))
    script.onerror = () => {
      loaderPromise = null
      reject(new Error('Could not load Razorpay Checkout. Check your connection.'))
    }
    document.head.appendChild(script)
  })

  return loaderPromise
}

/**
 * Open Checkout for an order and resolve with the (still unverified) result.
 *
 * Rejects if the user dismisses the modal, so the caller can leave the
 * transaction in PAYMENT_CREATED rather than guessing at an outcome.
 */
export function openCheckout({
  keyId,
  orderId,
  amountPaise,
  name,
  description,
  methods,
}) {
  return loadCheckout().then(
    (Razorpay) =>
      new Promise((resolve, reject) => {
        const options = {
          key: keyId,
          order_id: orderId,
          amount: amountPaise,
          currency: 'INR',
          name: name || 'Velora',
          description: description || 'Authorized by Velora',
          theme: { color: '#6d6ef0' },
          handler: (response) => resolve(response),
          modal: {
            ondismiss: () =>
              reject(new Error('Checkout was closed before payment completed.')),
          },
        }

        // Only offer methods the account actually has enabled. Showing UPI on
        // an account where it is switched off produces a dead end that reads
        // as a bug in this app rather than a Razorpay account setting.
        if (methods) options.method = methods

        const rzp = new Razorpay(options)

        // A failed attempt is not a settled transaction. Surface Razorpay's
        // own wording — "international cards not supported" is actionable,
        // "something went wrong" is not.
        rzp.on('payment.failed', (event) => {
          const err = event?.error || {}
          const parts = [err.description, err.reason && `(${err.reason})`].filter(Boolean)
          reject(new Error(parts.join(' ') || 'Payment failed at Razorpay.'))
        })

        rzp.open()
      }),
  )
}
