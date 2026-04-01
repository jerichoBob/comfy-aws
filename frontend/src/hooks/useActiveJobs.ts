import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from './useApi'
import type { Job } from './useJob'

const POLL_INTERVAL_MS = 3000

export function useActiveJobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchActive = useCallback(async () => {
    try {
      const res = await apiFetch('/jobs?status=RUNNING')
      if (!res.ok) return
      const data: Job[] = await res.json()
      setJobs(data)
    } catch {
      // transient — keep polling
    }
  }, [])

  useEffect(() => {
    fetchActive()
    intervalRef.current = setInterval(fetchActive, POLL_INTERVAL_MS)
    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current)
    }
  }, [fetchActive])

  const cancelJob = useCallback(async (jobId: string) => {
    // Optimistic removal
    setJobs(prev => prev.filter(j => j.id !== jobId))
    try {
      await apiFetch(`/jobs/${jobId}`, { method: 'DELETE' })
    } catch {
      // If cancel fails, next poll will restore it
    }
  }, [])

  return { jobs, cancelJob }
}
