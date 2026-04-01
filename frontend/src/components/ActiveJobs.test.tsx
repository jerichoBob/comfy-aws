import { render, screen, fireEvent } from '@testing-library/react'
import { ActiveJobs } from './ActiveJobs'
import type { Job } from '../hooks/useJob'

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    workflow_id: 'txt2img-sdxl',
    params: { positive_prompt: 'a rocket in space' },
    status: 'RUNNING',
    output_urls: [],
    created_at: new Date().toISOString(),
    ...overrides,
  } as unknown as Job
}

describe('ActiveJobs', () => {
  it('renders nothing when jobs list is empty', () => {
    const { container } = render(<ActiveJobs jobs={[]} onCancel={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders an active job entry with the prompt', () => {
    render(<ActiveJobs jobs={[makeJob()]} onCancel={() => {}} />)
    expect(screen.getByText('a rocket in space')).toBeInTheDocument()
  })

  it('shows the job count in the header', () => {
    render(<ActiveJobs jobs={[makeJob(), makeJob({ id: 'job-2' })]} onCancel={() => {}} />)
    expect(screen.getByText('Active (2)')).toBeInTheDocument()
  })

  it('calls onCancel with the job id when cancel button clicked', () => {
    const onCancel = vi.fn()
    render(<ActiveJobs jobs={[makeJob()]} onCancel={onCancel} />)
    fireEvent.click(screen.getByTitle('Cancel job'))
    expect(onCancel).toHaveBeenCalledWith('job-1')
  })
})
