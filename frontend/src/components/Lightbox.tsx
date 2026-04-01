import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X, ClipboardCopy, Check } from 'lucide-react'

export interface LightboxMeta {
  positive_prompt?: string
  negative_prompt?: string
  checkpoint?: string
  sampler_name?: string
  scheduler?: string
  steps?: number
  cfg?: number
  seed?: number | string
  width?: number
  height?: number
  duration_seconds?: number
}

interface Props {
  url: string
  meta?: LightboxMeta
  onClose: () => void
  onCopyToSession?: (meta: LightboxMeta) => void
}

export function Lightbox({ url, meta, onClose, onCopyToSession }: Props) {
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const [copied, setCopied] = useState(false)

  function handleCopy() {
    if (!meta || !onCopyToSession) return
    onCopyToSession(meta)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
      onClick={onClose}
      data-testid="lightbox-backdrop"
    >
      <div
        className="flex max-w-[95vw] max-h-[95vh] gap-4 items-start"
        onClick={e => e.stopPropagation()}
      >
        {/* Image */}
        <img
          src={url}
          alt="Full size output"
          className="max-w-[75vw] max-h-[90vh] object-contain rounded shadow-2xl shrink-0"
        />

        {/* Metadata panel */}
        {meta && (
          <div className="w-64 shrink-0 bg-zinc-900/90 border border-zinc-700 rounded-lg p-4 text-sm text-zinc-300 flex flex-col gap-3 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">Generation Info</span>
              <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
                <X size={14} />
              </button>
            </div>

            {meta.positive_prompt && (
              <div>
                <div className="text-xs text-zinc-500 mb-1">Prompt</div>
                <div className="text-xs leading-relaxed">{String(meta.positive_prompt)}</div>
              </div>
            )}

            {meta.negative_prompt && (
              <div>
                <div className="text-xs text-zinc-500 mb-1">Negative</div>
                <div className="text-xs leading-relaxed text-zinc-400">{String(meta.negative_prompt)}</div>
              </div>
            )}

            {meta.checkpoint && (
              <Row label="Checkpoint" value={String(meta.checkpoint)} />
            )}

            <div className="grid grid-cols-2 gap-2">
              {meta.sampler_name && <Row label="Sampler" value={String(meta.sampler_name)} />}
              {meta.scheduler && <Row label="Scheduler" value={String(meta.scheduler)} />}
              {meta.steps != null && <Row label="Steps" value={String(meta.steps)} />}
              {meta.cfg != null && <Row label="CFG" value={String(meta.cfg)} />}
              {meta.seed != null && <Row label="Seed" value={String(meta.seed)} />}
              {meta.width != null && meta.height != null && (
                <Row label="Size" value={`${meta.width}×${meta.height}`} />
              )}
              {meta.duration_seconds != null && (
                <Row label="Time" value={`${meta.duration_seconds}s`} />
              )}
            </div>

            {onCopyToSession && (
              <button
                type="button"
                onClick={handleCopy}
                className="mt-1 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium transition-colors"
              >
                {copied ? <Check size={13} /> : <ClipboardCopy size={13} />}
                {copied ? 'Copied to session!' : 'Copy to current session'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>,
    document.body
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-xs font-mono break-all">{value}</div>
    </div>
  )
}
