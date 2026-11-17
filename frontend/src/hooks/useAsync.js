import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

/** Run an async loader on mount / when deps change; returns {data, error, loading, reload, setData}. */
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const reload = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setState((s) => ({ ...s, loading: true }))
    try {
      const data = await loaderRef.current()
      setState({ data, error: null, loading: false })
      return data
    } catch (error) {
      setState((s) => ({ ...s, error, loading: false }))
      return null
    }
  }, [])

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  const setData = useCallback((updater) => {
    setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater }))
  }, [])

  return { ...state, reload, setData }
}

/** Poll a Celery task until it finishes. */
export function useTaskPoller() {
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])

  return useCallback(
    (taskId, { interval = 2000, onUpdate } = {}) =>
      new Promise((resolve, reject) => {
        const started = Date.now()
        const tick = async () => {
          try {
            const status = await api.task(taskId)
            onUpdate?.(status, Math.round((Date.now() - started) / 1000))
            if (status.state === 'SUCCESS') return resolve(status.result)
            if (status.state === 'FAILURE' || status.state === 'REVOKED') {
              return reject(new Error(status.error || 'Task failed'))
            }
          } catch (err) {
            if (err.status && err.status !== 503) return reject(err)
          }
          timer.current = setTimeout(tick, interval)
        }
        tick()
      }),
    [],
  )
}

/** Re-run ``fn`` every ``ms`` while ``active`` is true. */
export function useInterval(fn, ms, active) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!active) return undefined
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms, active])
}
