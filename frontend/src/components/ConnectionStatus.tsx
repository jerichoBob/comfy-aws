import { useEffect, useState } from 'react'
import clsx from 'clsx'

export function ConnectionStatus() {
  const [connected, setConnected] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const res = await fetch('/api/health', { signal: AbortSignal.timeout(5000) })
        if (!cancelled) setConnected(res.ok)
      } catch {
        if (!cancelled) setConnected(false)
      }
    }

    check()
    const id = setInterval(check, 10_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  if (connected === null) return null

  return (
    <div className="flex items-center gap-1.5 text-xs text-zinc-500">
      <span
        className={clsx(
          'w-2 h-2 rounded-full',
          connected ? 'bg-emerald-400' : 'bg-red-400',
        )}
      />
      {connected ? 'Connected' : 'Unreachable'}
    </div>
  )
}
