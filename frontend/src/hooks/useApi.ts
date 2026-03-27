import { useEffect, useState } from 'react'

export interface Models {
  checkpoints: string[]
  loras: string[]
  vaes: string[]
}

export interface WorkflowParam {
  type: string
  required?: boolean
  default?: unknown
}

export interface Workflow {
  id: string
  params: Record<string, WorkflowParam>
}

export function getApiKey(): string {
  return localStorage.getItem('comfy-api-key') ?? ''
}

export function setApiKey(key: string): void {
  localStorage.setItem('comfy-api-key', key)
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const key = getApiKey()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(key ? { 'X-API-Key': key } : {}),
    ...(init?.headers as Record<string, string> ?? {}),
  }
  return fetch(`/api${path}`, { ...init, headers })
}

export function useApi() {
  const [models, setModels] = useState<Models>({ checkpoints: [], loras: [], vaes: [] })
  const [workflows, setWorkflows] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [modelsRes, workflowsRes] = await Promise.all([
          apiFetch('/models'),
          apiFetch('/workflows'),
        ])
        if (!modelsRes.ok || !workflowsRes.ok) throw new Error('API fetch failed')
        const [modelsData, workflowsData] = await Promise.all([
          modelsRes.json(),
          workflowsRes.json(),
        ])
        if (!cancelled) {
          setModels(modelsData)
          setWorkflows(workflowsData.workflows ?? [])
        }
      } catch (e) {
        if (!cancelled) setError(String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  return { models, workflows, loading, error }
}
