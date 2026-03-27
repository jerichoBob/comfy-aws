interface Props {
  positive: string
  negative: string
  onPositiveChange: (v: string) => void
  onNegativeChange: (v: string) => void
}

function Textarea({
  label,
  value,
  rows,
  onChange,
}: {
  label: string
  value: string
  rows: number
  onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">{label}</label>
        <span className="text-xs text-zinc-600">{value.length}</span>
      </div>
      <textarea
        value={value}
        rows={rows}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-md px-3 py-2 text-sm text-zinc-100 bg-zinc-800 border border-zinc-700 resize-y focus:outline-none focus:ring-2 focus:ring-violet-500 placeholder-zinc-600"
        placeholder={label === 'Positive prompt' ? 'Describe what you want to see…' : 'Describe what to avoid…'}
      />
    </div>
  )
}

export function PromptForm({ positive, negative, onPositiveChange, onNegativeChange }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <Textarea label="Positive prompt" value={positive} rows={4} onChange={onPositiveChange} />
      <Textarea label="Negative prompt" value={negative} rows={2} onChange={onNegativeChange} />
    </div>
  )
}
