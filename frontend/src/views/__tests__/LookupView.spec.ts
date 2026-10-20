import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { deferred, failure, item, mockApi, mountAt, stub } from '@/test/helpers'
import LookupView from '../LookupView.vue'

const routes = [
  { path: '/lookup', name: 'lookup', component: LookupView },
  { path: '/vocab/:id', name: 'vocab', component: stub },
]
const levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'].map((level, i) => ({
  level,
  count: (i + 1) * 10,
}))
const groups = [
  { id: 4, name: 'Greetings', description: 'Say hello', level: 'A1', count: 5 },
  { id: 7, name: 'Daily life', description: null, level: 'A2', count: 6 },
]
const page = (items = [item()], total = items.length, pageNo = 1) => ({
  items,
  total,
  page: pageNo,
  page_size: 20,
})

function api(search: (url: URL) => unknown = () => page()) {
  return mockApi({
    'GET /vocab': (url) => search(url),
    'GET /vocab/levels': () => levels,
    'GET /vocab/groups': () => groups,
  })
}
const searches = (mock: ReturnType<typeof api>) => mock.to('GET', '/vocab')
const params = (call: { url: URL }) => Object.fromEntries(call.url.searchParams)
const last = <T>(list: T[]): T => list[list.length - 1]!

beforeEach(() => {
  localStorage.clear()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('browse', () => {
  it('shows levels with their word counts and the word lists, without searching', async () => {
    const mock = api()
    const { wrapper } = await mountAt(LookupView, '/lookup', routes)
    expect(searches(mock)).toHaveLength(0)
    const text = wrapper.text()
    for (const level of ['A1', 'A2', 'C2']) expect(text).toContain(level)
    expect(text).toContain('10 words')
    expect(text).toContain('60 words')
    expect(text).toContain('Greetings')
    expect(text).toContain('Say hello')
    expect(text).toContain('Daily life')
  })

  it('opens a level and then lists its words', async () => {
    const mock = api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup', routes)
    await wrapper
      .findAll('button')
      .find((b) => b.text().startsWith('A2'))!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ level: 'A2' })
    expect(params(searches(mock)[0]!)).toMatchObject({ level: 'A2', page: '1', page_size: '20' })
    expect(wrapper.text()).toContain('學習')
  })

  it('opens a word list', async () => {
    const mock = api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup', routes)
    await wrapper
      .findAll('button')
      .find((b) => b.text().startsWith('Daily life'))!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ group: '7' })
    expect(params(searches(mock)[0]!).group_id).toBe('7')
    expect(wrapper.text()).toContain('Daily life') // named in the result line
  })
})

describe('searching', () => {
  it('searches what the URL says and lists the words', async () => {
    const mock = api(() =>
      page([item(), item({ id: 2, traditional: '學', simplified: '学', pinyin: 'xué' })]),
    )
    const { wrapper } = await mountAt(LookupView, '/lookup?q=xue', routes)
    expect(params(searches(mock)[0]!)).toEqual({ q: 'xue', page: '1', page_size: '20' })
    expect(wrapper.findAll('a[href^="/vocab/"]').map((a) => a.attributes('href'))).toEqual([
      '/vocab/1',
      '/vocab/2',
    ])
    expect(wrapper.text()).toContain('2 results')
    expect((wrapper.find('input[type="search"]').element as HTMLInputElement).value).toBe('xue')
  })

  it('waits for a pause in typing, then searches once and puts the query in the URL', async () => {
    const mock = api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=old', routes)
    const before = searches(mock).length
    const input = wrapper.find('input[type="search"]')
    for (const value of ['n', 'ni', 'ni h', 'ni hao']) {
      await input.setValue(value)
      await vi.advanceTimersByTimeAsync(100)
    }
    expect(searches(mock)).toHaveLength(before) // still typing: nothing sent
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(searches(mock)).toHaveLength(before + 1)
    expect(params(last(searches(mock))).q).toBe('ni hao')
    expect(router.currentRoute.value.query.q).toBe('ni hao')
  })

  it('does not add a history entry per keystroke', async () => {
    api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup', routes)
    const start = window.history.length
    await wrapper.find('input[type="search"]').setValue('xue')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('xue')
    router.back()
    await flushPromises()
    expect(window.history.length).toBe(start) // replace, not push
  })

  it('returns to the browse view when the box is cleared', async () => {
    const mock = api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=xue', routes)
    await wrapper.find('input[type="search"]').setValue('')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    expect(wrapper.text()).toContain('Browse by level')
    expect(searches(mock)).toHaveLength(1)
  })

  it('shows the box content again when the URL changes underneath it (back button)', async () => {
    api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=first', routes)
    await router.push('/lookup?q=second')
    await flushPromises()
    expect((wrapper.find('input[type="search"]').element as HTMLInputElement).value).toBe('second')
  })

  it('says so when nothing matches, and how to get unstuck', async () => {
    api(() => page([], 0))
    const { wrapper } = await mountAt(LookupView, '/lookup?q=zzzz', routes)
    expect(wrapper.text()).toContain('No words found for “zzzz”.')
    expect(wrapper.text()).toContain('try pinyin without tones')
    expect(wrapper.text()).toContain('No results')
  })

  it('ignores a slow answer to an old search when a newer one has arrived', async () => {
    const slow = deferred<unknown>()
    const mock = api((url) =>
      url.searchParams.get('q') === 'old'
        ? slow.promise
        : page([item({ id: 2, traditional: '新', simplified: '新', pinyin: 'xīn' })]),
    )
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=old', routes)
    await router.push('/lookup?q=new')
    await flushPromises()
    expect(wrapper.text()).toContain('新')
    slow.resolve(page([item({ id: 9, traditional: '舊', simplified: '旧', pinyin: 'jiù' })]))
    await flushPromises()
    expect(wrapper.text()).toContain('新')
    expect(wrapper.text()).not.toContain('舊')
    expect(searches(mock)).toHaveLength(2)
  })

  it('shows a failure with a way to retry', async () => {
    let calls = 0
    api(() => (++calls === 1 ? failure(500, 'internal_error') : page()))
    const { wrapper } = await mountAt(LookupView, '/lookup?q=xue', routes)
    expect(wrapper.find('[role="alert"]').text()).toContain('Something went wrong')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Try again')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('學習')
  })

  it('shows rate limiting in the user’s words', async () => {
    api(() => failure(429, 'rate_limited'))
    const { wrapper } = await mountAt(LookupView, '/lookup?q=xue', routes)
    expect(wrapper.find('[role="alert"]').text()).toContain('Too many attempts')
  })
})

describe('filters', () => {
  it('filters by level, marking the active one, and keeps the query', async () => {
    const mock = api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=xue', routes)
    const b1 = () => wrapper.findAll('button').find((b) => b.text() === 'B1')!
    await b1().trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'xue', level: 'B1' })
    expect(params(last(searches(mock)))).toMatchObject({ q: 'xue', level: 'B1' })
    expect(b1().attributes('aria-pressed')).toBe('true')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'All')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'xue' })
  })

  it('filters by word list from the drop-down', async () => {
    const mock = api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=xue', routes)
    await wrapper.find('select').setValue('4')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'xue', group: '4' })
    expect(params(last(searches(mock))).group_id).toBe('4')
    await wrapper.find('select').setValue('')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'xue' })
  })

  it('clears everything at once', async () => {
    api()
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=xue&level=A1&group=4', routes)
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Clear filters')!
      .trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    expect((wrapper.find('input[type="search"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('Browse by level')
  })

  it('ignores nonsense in the URL instead of sending it', async () => {
    const mock = api()
    await mountAt(LookupView, '/lookup?q=xue&level=Z9&group=abc&page=-3', routes)
    expect(params(searches(mock)[0]!)).toEqual({ q: 'xue', page: '1', page_size: '20' })
  })
})

describe('pages', () => {
  const many = (url: URL) =>
    page(
      [item({ id: Number(url.searchParams.get('page')) })],
      45,
      Number(url.searchParams.get('page')),
    )

  it('pages through the results using the URL', async () => {
    const mock = api(many)
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=xue', routes)
    const button = (label: string) => wrapper.findAll('nav button').find((b) => b.text() === label)!
    expect(wrapper.text()).toContain('Page 1 of 3')
    expect(button('Previous').attributes('disabled')).toBeDefined()
    await button('Next').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'xue', page: '2' })
    expect(params(last(searches(mock))).page).toBe('2')
    expect(wrapper.text()).toContain('Page 2 of 3')
    await button('Next').trigger('click')
    await flushPromises()
    expect(button('Next').attributes('disabled')).toBeDefined()
    await button('Previous').trigger('click')
    await flushPromises()
    await button('Previous').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'xue' }) // page 1 is the default, not in the URL
  })

  it('goes back to page 1 when the search changes', async () => {
    api(many)
    const { wrapper, router } = await mountAt(LookupView, '/lookup?q=xue&page=3', routes)
    await wrapper.find('input[type="search"]').setValue('ni')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: 'ni' })
  })

  it('shows no pager when everything fits on one page', async () => {
    api()
    const { wrapper } = await mountAt(LookupView, '/lookup?q=xue', routes)
    expect(wrapper.find('nav').exists()).toBe(false)
  })
})
