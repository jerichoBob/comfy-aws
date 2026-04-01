import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Lightbox } from './Lightbox'

const TEST_URL = 'https://example.com/image.png'

describe('Lightbox', () => {
  it('renders the image with the provided URL', () => {
    render(<Lightbox url={TEST_URL} onClose={() => {}} />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('src', TEST_URL)
  })

  it('calls onClose when ESC key is pressed', async () => {
    const onClose = vi.fn()
    render(<Lightbox url={TEST_URL} onClose={onClose} />)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when backdrop is clicked', () => {
    const onClose = vi.fn()
    render(<Lightbox url={TEST_URL} onClose={onClose} />)
    fireEvent.click(screen.getByTestId('lightbox-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not call onClose when the image itself is clicked', () => {
    const onClose = vi.fn()
    render(<Lightbox url={TEST_URL} onClose={onClose} />)
    fireEvent.click(screen.getByRole('img'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('sets overflow-hidden on body while mounted and restores on unmount', () => {
    const { unmount } = render(<Lightbox url={TEST_URL} onClose={() => {}} />)
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('')
  })
})
