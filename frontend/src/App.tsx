import { useEffect, useState } from 'react'
import { ApiKeyInput } from './components/ApiKeyInput'
import { ConnectionStatus } from './components/ConnectionStatus'
import { ErrorBanner } from './components/ErrorBanner'
import { JobHistory } from './components/JobHistory'
import { PromptForm } from './components/PromptForm'
import { ResultPanel } from './components/ResultPanel'
import { SettingsPanel } from './components/SettingsPanel'
import { Sidebar } from './components/Sidebar'
import { SubmitButton } from './components/SubmitButton'
import { useApi } from './hooks/useApi'
import { useJob } from './hooks/useJob'
import { useJobHistory } from './hooks/useJobHistory'

export default function App() {
  const { models, workflows, loading } = useApi()
  const { state, submit, reset } = useJob()
  const { history, addEntry, clearHistory } = useJobHistory()

  // Sidebar selections
  const [workflow, setWorkflow] = useState('')
  const [checkpoint, setCheckpoint] = useState('')
  const [sampler, setSampler] = useState('euler')
  const [scheduler, setScheduler] = useState('normal')

  // Prompt + settings
  const [positive, setPositive] = useState('')
  const [negative, setNegative] = useState('')
  const [steps, setSteps] = useState(20)
  const [cfg, setCfg] = useState(7)
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 2 ** 32))
  const [width, setWidth] = useState(1024)
  const [height, setHeight] = useState(1024)

  // Set defaults once data loads
  useEffect(() => {
    if (workflows.length > 0 && !workflow) setWorkflow(workflows[0])
  }, [workflows, workflow])

  useEffect(() => {
    if (models.checkpoints.length > 0 && !checkpoint) setCheckpoint(models.checkpoints[0])
  }, [models.checkpoints, checkpoint])

  // Record completed/failed jobs to history
  useEffect(() => {
    if (state.phase === 'done') addEntry(state.job)
    if (state.phase === 'failed' && state.job) addEntry(state.job)
  }, [state, addEntry])

  const handleSubmit = () => {
    if (!positive.trim()) return
    submit(workflow, {
      positive_prompt: positive,
      negative_prompt: negative || undefined,
      checkpoint,
      sampler_name: sampler,
      scheduler,
      steps,
      cfg,
      seed,
      width,
      height,
    })
  }

  const isLoading = state.phase === 'submitting' || state.phase === 'polling'

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Left sidebar */}
      <Sidebar
        models={models}
        workflows={workflows}
        loading={loading}
        selectedCheckpoint={checkpoint}
        selectedWorkflow={workflow}
        selectedSampler={sampler}
        selectedScheduler={scheduler}
        onCheckpointChange={setCheckpoint}
        onWorkflowChange={setWorkflow}
        onSamplerChange={setSampler}
        onSchedulerChange={setScheduler}
      />

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-3 border-b border-zinc-800 shrink-0">
          <span className="text-sm text-zinc-500">
            {state.phase === 'polling' ? 'Generating…' : state.phase === 'done' ? 'Complete' : 'Ready'}
          </span>
          <div className="flex items-center gap-3">
            <ConnectionStatus />
            <ApiKeyInput />
          </div>
        </header>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-2xl mx-auto p-6 flex flex-col gap-6">
            <PromptForm
              positive={positive}
              negative={negative}
              onPositiveChange={setPositive}
              onNegativeChange={setNegative}
            />

            <SettingsPanel
              steps={steps}
              cfg={cfg}
              seed={seed}
              width={width}
              height={height}
              onStepsChange={setSteps}
              onCfgChange={setCfg}
              onSeedChange={setSeed}
              onWidthChange={setWidth}
              onHeightChange={setHeight}
            />

            <SubmitButton loading={isLoading} onClick={handleSubmit} />

            {state.phase === 'failed' && (
              <ErrorBanner message={state.error} onReset={reset} />
            )}

            {state.phase === 'done' && (
              <ResultPanel job={state.job} />
            )}
          </div>
        </div>
      </main>

      {/* Right panel: job history */}
      <aside className="w-64 shrink-0 border-l border-zinc-800 overflow-y-auto bg-zinc-900">
        <JobHistory history={history} onClear={clearHistory} />
      </aside>
    </div>
  )
}
