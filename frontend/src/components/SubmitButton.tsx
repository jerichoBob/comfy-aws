import clsx from 'clsx'
import { Loader2, AlertTriangle } from 'lucide-react'

interface Props {
  loading: boolean
  disabled?: boolean
  onClick: () => void
  missingParams?: string[]
}

export function SubmitButton({ loading, disabled, onClick, missingParams = [] }: Props) {
  const blocked = missingParams.length > 0

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={onClick}
        disabled={loading || disabled || blocked}
        className={clsx(
          'w-full flex items-center justify-center gap-2',
          'rounded-md px-4 py-3 text-sm font-semibold',
          'transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-2 focus:ring-offset-zinc-900',
          loading || disabled || blocked
            ? 'bg-zinc-700 text-zinc-500 cursor-not-allowed'
            : 'bg-violet-600 text-white hover:bg-violet-500',
        )}
      >
        {loading && <Loader2 size={16} className="animate-spin" />}
        {loading ? 'Generating…' : 'Generate'}
      </button>

      {blocked && (
        <div className="flex items-start gap-2 text-xs text-amber-400 bg-amber-900/20 border border-amber-800/40 rounded-md px-3 py-2">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span>
            This workflow requires{' '}
            <span className="font-mono">{missingParams.join(', ')}</span>
            {' '}which isn't supported in the UI yet.
          </span>
        </div>
      )}
    </div>
  )
}
