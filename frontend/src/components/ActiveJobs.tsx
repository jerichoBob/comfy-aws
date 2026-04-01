import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import type { Job } from '../hooks/useJob'

interface Props {
  jobs: Job[]
  onCancel: (jobId: string) => void
}

function useElapsed(createdAt: string): string {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const start = new Date(createdAt).getTime()
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [createdAt])

  if (elapsed < 60) return `${elapsed}s`
  return `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
}

function ActiveJobRow({ job, onCancel }: { job: Job; onCancel: (id: string) => void }) {
  const elapsed = useElapsed(job.created_at as unknown as string)
  const prompt = String(job.params.positive_prompt ?? job.id)

  return (
    <div className="flex items-center gap-2 px-4 py-2.5 border-b border-zinc-800/50">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-300 truncate">{prompt}</p>
        <p className="text-xs text-amber-400 mt-0.5">{elapsed}</p>
      </div>
      <button
        type="button"
        onClick={() => onCancel(job.id)}
        title="Cancel job"
        className="shrink-0 p-1 text-zinc-500 hover:text-red-400 transition-colors"
      >
        <X size={13} />
      </button>
    </div>
  )
}

export function ActiveJobs({ jobs, onCancel }: Props) {
  if (jobs.length === 0) return null

  return (
    <div className="border-b border-zinc-800">
      <div className="px-4 py-2 flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-400" />
        </span>
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Active ({jobs.length})
        </span>
      </div>
      {jobs.map(job => (
        <ActiveJobRow key={job.id} job={job} onCancel={onCancel} />
      ))}
    </div>
  )
}
