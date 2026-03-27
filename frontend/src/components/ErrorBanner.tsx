import { AlertCircle, RotateCcw } from 'lucide-react'

interface Props {
  message: string
  onReset: () => void
}

export function ErrorBanner({ message, onReset }: Props) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-red-800 bg-red-900/30 p-4">
      <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-red-300 font-medium">Generation failed</p>
        <p className="text-xs text-red-400 mt-1 break-words">{message}</p>
      </div>
      <button
        type="button"
        onClick={onReset}
        className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors shrink-0"
      >
        <RotateCcw size={12} />
        Try again
      </button>
    </div>
  )
}
