import { useCallback, useState } from 'react'
import type { Job } from './useJob'

export interface HistoryEntry {
  id: string
  status: Job['status']
  thumbnail_url: string | null
  params: Record<string, unknown>
  created_at: string
  duration_seconds?: number
}

const STORAGE_KEY = 'comfy-job-history'
const MAX_ENTRIES = 20

function load(): HistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
  } catch {
    return []
  }
}

function save(entries: HistoryEntry[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
}

export function useJobHistory() {
  const [history, setHistory] = useState<HistoryEntry[]>(load)

  const addEntry = useCallback((job: Job) => {
    setHistory(prev => {
      const entry: HistoryEntry = {
        id: job.id,
        status: job.status,
        thumbnail_url: job.output_urls[0] ?? null,
        params: job.params,
        created_at: new Date().toISOString(),
        duration_seconds: job.duration_seconds,
      }
      // Replace if already exists, otherwise prepend
      const filtered = prev.filter(e => e.id !== job.id)
      const next = [entry, ...filtered].slice(0, MAX_ENTRIES)
      save(next)
      return next
    })
  }, [])

  const clearHistory = useCallback(() => {
    setHistory([])
    localStorage.removeItem(STORAGE_KEY)
  }, [])

  return { history, addEntry, clearHistory }
}
