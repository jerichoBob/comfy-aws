import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from './useApi'

export type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export interface Job {
  id: string
  status: JobStatus
  output_urls: string[]
  error?: string
  duration_seconds?: number
  params: Record<string, unknown>
}

type State =
  | { phase: 'idle' }
  | { phase: 'submitting' }
  | { phase: 'polling'; jobId: string }
  | { phase: 'done'; job: Job }
  | { phase: 'failed'; error: string; job?: Job }

export function useJob() {
  const [state, setState] = useState<State>({ phase: 'idle' })
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const clearPolling = () => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }

  useEffect(() => () => clearPolling(), [])

  const submit = useCallback(async (workflowId: string, params: Record<string, unknown>) => {
    setState({ phase: 'submitting' })
    clearPolling()
    try {
      const res = await apiFetch('/jobs', {
        method: 'POST',
        body: JSON.stringify({ workflow_id: workflowId, params }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        setState({ phase: 'failed', error: body.detail ?? 'Submit failed' })
        return
      }
      const job: Job = await res.json()
      setState({ phase: 'polling', jobId: job.id })

      intervalRef.current = setInterval(async () => {
        try {
          const pollRes = await apiFetch(`/jobs/${job.id}`)
          if (!pollRes.ok) return
          const polled: Job = await pollRes.json()
          if (polled.status === 'COMPLETED') {
            clearPolling()
            setState({ phase: 'done', job: polled })
          } else if (polled.status === 'FAILED' || polled.status === 'CANCELLED') {
            clearPolling()
            setState({ phase: 'failed', error: polled.error ?? 'Job failed', job: polled })
          }
        } catch {
          // transient network error — keep polling
        }
      }, 2000)
    } catch (e) {
      setState({ phase: 'failed', error: String(e) })
    }
  }, [])

  const reset = useCallback(() => {
    clearPolling()
    setState({ phase: 'idle' })
  }, [])

  return { state, submit, reset }
}
