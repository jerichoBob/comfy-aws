import clsx from 'clsx'
import { Loader2 } from 'lucide-react'

interface Props {
  loading: boolean
  disabled?: boolean
  onClick: () => void
}

export function SubmitButton({ loading, disabled, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading || disabled}
      className={clsx(
        'w-full flex items-center justify-center gap-2',
        'rounded-md px-4 py-3 text-sm font-semibold',
        'transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-2 focus:ring-offset-zinc-900',
        loading || disabled
          ? 'bg-zinc-700 text-zinc-500 cursor-not-allowed'
          : 'bg-violet-600 text-white hover:bg-violet-500',
      )}
    >
      {loading && <Loader2 size={16} className="animate-spin" />}
      {loading ? 'Generating…' : 'Generate'}
    </button>
  )
}
