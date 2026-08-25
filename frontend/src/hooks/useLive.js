import { useCallback, useEffect, useRef, useState } from 'react'
import { OPERATOR_TOKEN } from '../lib/api'

/**
 * Subscribe to the backend's SSE stream.
 *
 * The stream is advisory: a message only says something changed, and the
 * caller refetches. That means a dropped event can never leave the UI
 * asserting a decision the backend disagrees with -- the worst case is a
 * stale view that the next event or poll corrects.
 */
export function useEventStream(onEvent) {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    // EventSource cannot set headers, so the operator token rides as a
    // query parameter when the backend requires one.
    const url = OPERATOR_TOKEN
      ? `/api/events?token=${encodeURIComponent(OPERATOR_TOKEN)}`
      : '/api/events'
    const source = new EventSource(url)

    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)
    source.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data)
        if (parsed.event !== 'connected') handler.current?.(parsed)
      } catch {
        /* ignore malformed frames */
      }
    }

    return () => source.close()
  }, [])

  return connected
}

/**
 * Fetch data, then refetch whenever the server says something changed.
 * Falls back to a slow poll so the UI still converges if SSE is unavailable.
 */
export function useLiveResource(fetcher, deps = [], { poll = 15000 } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const reload = useCallback(async () => {
    try {
      const result = await fetcherRef.current()
      setData(result)
      setError(null)
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    if (!poll) return
    const id = setInterval(reload, poll)
    return () => clearInterval(id)
  }, [reload, poll])

  useEventStream(reload)

  return { data, error, loading, reload }
}

/** Re-render on a timer so countdowns tick without a data refetch. */
export function useTick(ms = 1000) {
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), ms)
    return () => clearInterval(id)
  }, [ms])
}
