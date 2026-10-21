import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { signedInUser, mockApi, mountAt, signIn, stub } from '@/test/helpers'
import ProfileView from '../ProfileView.vue'

const routes = [
  { path: '/profile', name: 'profile', component: ProfileView },
  { path: '/', name: 'home', component: stub },
]

function setup(me = signedInUser) {
  return mockApi({
    'GET /auth/config': () => ({ google_client_id: null }),
    'GET /vocab/levels': () => [],
    'PATCH /me': (_url, init) => ({ ...me, ...JSON.parse(String(init?.body)) }),
  })
}

async function open() {
  const result = await mountAt(ProfileView, '/profile', routes)
  signIn()
  await flushPromises()
  return result
}
const field = (wrapper: Awaited<ReturnType<typeof open>>['wrapper']) =>
  wrapper.find('input[type="number"]')

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('new cards per day, in the profile', () => {
  it('shows the saved value and saves a new one', async () => {
    const mock = setup()
    const { wrapper } = await open()
    expect((field(wrapper).element as HTMLInputElement).value).toBe('20')
    await field(wrapper).setValue('5')
    await wrapper.find('form:has(input[type="number"])').trigger('submit')
    await flushPromises()
    expect(mock.to('PATCH', '/me').map((c) => c.body)).toEqual([{ daily_new_cards: 5 }])
    expect(wrapper.text()).toContain('Saved.')
    expect((field(wrapper).element as HTMLInputElement).value).toBe('5')
  })

  it('accepts zero, which means reviews only', async () => {
    const mock = setup()
    const { wrapper } = await open()
    await field(wrapper).setValue('0')
    await wrapper.find('form:has(input[type="number"])').trigger('submit')
    await flushPromises()
    expect(mock.to('PATCH', '/me').map((c) => c.body)).toEqual([{ daily_new_cards: 0 }])
  })

  it.each(['-1', '201', '2.5', '', 'abc'])('does not send %j', async (value) => {
    const mock = setup()
    const { wrapper } = await open()
    await field(wrapper).setValue(value)
    await wrapper.find('form:has(input[type="number"])').trigger('submit')
    await flushPromises()
    expect(mock.to('PATCH', '/me')).toHaveLength(0)
    expect(wrapper.find('[role="alert"]').text()).toContain('Something went wrong')
  })
})
