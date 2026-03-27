import { Clock, Download, Hash, Box } from 'lucide-react'
import type { Job } from '../hooks/useJob'

interface Props {
  job: Job
}

export function ResultPanel({ job }: Props) {
  const imageUrl = job.output_urls[0]
  const checkpoint = String(job.params.checkpoint ?? '—')
  const seed = String(job.params.seed ?? '—')

  return (
    <div className="flex flex-col gap-4">
      {imageUrl && (
        <div className="rounded-lg overflow-hidden border border-zinc-700 bg-zinc-800">
          <img
            src={imageUrl}
            alt="Generated output"
            className="w-full object-contain max-h-[60vh]"
          />
        </div>
      )}

      <div className="flex flex-wrap gap-4 text-sm text-zinc-400">
        {job.duration_seconds != null && (
          <span className="flex items-center gap-1">
            <Clock size={14} className="text-zinc-500" />
            {job.duration_seconds}s
          </span>
        )}
        <span className="flex items-center gap-1">
          <Hash size={14} className="text-zinc-500" />
          {seed}
        </span>
        <span className="flex items-center gap-1 truncate max-w-xs">
          <Box size={14} className="text-zinc-500" />
          <span className="truncate">{checkpoint}</span>
        </span>
      </div>

      {imageUrl && (
        <a
          href={imageUrl}
          download
          className="inline-flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300 transition-colors"
        >
          <Download size={14} />
          Download image
        </a>
      )}
    </div>
  )
}
