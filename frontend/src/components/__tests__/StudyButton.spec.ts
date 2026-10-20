import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { failure, mockApi, mountAt, signIn, stub } from '@/test/helpers'
import StudyButton from '../StudyButton.vue'

const routes = [
  { path: '/vocab/:id', name: 'vocab', component: stub },
  { path: '/login', name: 'login', component: stub },
]
afterEach(() => vi.unstubAllGlobals())

describe('StudyButton', () => {
  it('sends signed-out visitors to sign in, then back to this word', async () => {
    const { wrapper } = await mountAt(StudyButton, '/vocab/9?x=1', routes, {
      vocabId: 9,
      studying: false,
    })
    const link = wrapper.find('a')
    expect(link.text()).toBe('Sign in to add to your study list')
    expect(decodeURIComponent(link.attributes('href')!)).toBe('/login?next=/vocab/9?x=1')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('adds the word and then shows it is in the list', async () => {
    const api = mockApi({
      'POST /study-list/9': () => ({ added: true, status: 'new', next_review_at: 'now' }),
    })
    const { wrapper } = await mountAt(StudyButton, '/vocab/9', routes, {
      vocabId: 9,
      studying: false,
    })
    signIn()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(api.to('POST', '/study-list/9')).toHaveLength(1)
    expect(wrapper.text()).toContain('In your study list')
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.emitted('added')).toHaveLength(1)
  })

  it('shows an already-added word as added without offering the button', async () => {
    const { wrapper } = await mountAt(StudyButton, '/vocab/9', routes, {
      vocabId: 9,
      studying: true,
    })
    expect(wrapper.text()).toContain('In your study list')
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it('reports a failure and lets the user try again', async () => {
    let attempts = 0
    mockApi({
      'POST /study-list/9': () =>
        ++attempts === 1
          ? failure(429, 'rate_limited')
          : { added: true, status: 'new', next_review_at: 'x' },
    })
    const { wrapper } = await mountAt(StudyButton, '/vocab/9', routes, {
      vocabId: 9,
      studying: false,
    })
    signIn()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('Too many attempts')
    expect(wrapper.text()).not.toContain('In your study list')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('In your study list')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('follows the word it is shown for', async () => {
    const { wrapper } = await mountAt(StudyButton, '/vocab/9', routes, {
      vocabId: 9,
      studying: true,
    })
    await wrapper.setProps({ vocabId: 10, studying: false })
    signIn()
    await flushPromises()
    expect(wrapper.find('button').exists()).toBe(true)
  })
})
