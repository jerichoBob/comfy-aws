import clsx from 'clsx'
import type { Models } from '../hooks/useApi'

interface Props {
  models: Models
  workflows: string[]
  loading: boolean
  selectedCheckpoint: string
  selectedWorkflow: string
  selectedSampler: string
  selectedScheduler: string
  onCheckpointChange: (v: string) => void
  onWorkflowChange: (v: string) => void
  onSamplerChange: (v: string) => void
  onSchedulerChange: (v: string) => void
}

const SAMPLERS = ['euler', 'euler_ancestral', 'dpm_2', 'dpm_2_ancestral', 'heun', 'lms', 'ddim']
const SCHEDULERS = ['normal', 'karras', 'exponential', 'sgm_uniform', 'simple']

function Skeleton() {
  return <div className="h-9 rounded-md bg-zinc-700 animate-pulse" />
}

function Select({
  label,
  value,
  options,
  onChange,
  loading,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
  loading?: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">{label}</label>
      {loading ? (
        <Skeleton />
      ) : (
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          className={clsx(
            'w-full rounded-md px-3 py-2 text-sm text-zinc-100',
            'bg-zinc-800 border border-zinc-700',
            'focus:outline-none focus:ring-2 focus:ring-violet-500',
          )}
        >
          {options.length === 0 && <option value="">— none available —</option>}
          {options.map(o => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      )}
    </div>
  )
}

export function Sidebar({
  models,
  workflows,
  loading,
  selectedCheckpoint,
  selectedWorkflow,
  selectedSampler,
  selectedScheduler,
  onCheckpointChange,
  onWorkflowChange,
  onSamplerChange,
  onSchedulerChange,
}: Props) {
  return (
    <aside className="flex flex-col gap-5 w-64 shrink-0 p-5 bg-zinc-900 border-r border-zinc-800 min-h-screen">
      <div className="text-sm font-semibold text-zinc-200 tracking-tight">comfy-aws</div>

      <Select
        label="Workflow"
        value={selectedWorkflow}
        options={workflows}
        onChange={onWorkflowChange}
        loading={loading}
      />
      <Select
        label="Checkpoint"
        value={selectedCheckpoint}
        options={models.checkpoints}
        onChange={onCheckpointChange}
        loading={loading}
      />
      <Select
        label="Sampler"
        value={selectedSampler}
        options={SAMPLERS}
        onChange={onSamplerChange}
      />
      <Select
        label="Scheduler"
        value={selectedScheduler}
        options={SCHEDULERS}
        onChange={onSchedulerChange}
      />
    </aside>
  )
}
