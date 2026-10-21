import { flushPromises, type DOMWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { card, failure, mockApi, mountAt, press, sessionOf, statsOf, stub } from '@/test/helpers'
import FlashcardsView from '../FlashcardsView.vue'

const routes = [
  { path: '/flashcards', name: 'flashcards', component: FlashcardsView },
  { path: '/lookup', name: 'lookup', component: stub },
  { path: '/profile', name: 'profile', component: stub },
]
const RATINGS = new Set(['Again', 'Hard', 'Good', 'Easy'])
const groups = [{ id: 7, name: 'Daily life', description: null, level: 'A2', count: 6 }]
const a = card({
  vocabulary_id: 1,
  traditional: '學',
  simplified: '学',
  pinyin: 'xué',
  zhuyin: 'ㄒㄩㄝˊ',
})
const b = card({
  vocabulary_id: 2,
  traditional: '習',
  simplified: '习',
  pinyin: 'xí',
  zhuyin: 'ㄒㄧˊ',
})
const c = card({
  vocabulary_id: 3,
  traditional: '女',
  simplified: '女',
  pinyin: 'nǚ',
  zhuyin: 'ㄋㄩˇ',
  is_new: true,
  status: 'new',
})

type Overrides = {
  stats?: unknown
  session?: (url: URL) => unknown
  review?: (body: { vocabulary_id: number; rating: number }) => unknown
}
function api({ stats, session, review }: Overrides = {}) {
  return mockApi({
    'GET /flashcards/stats': () => stats ?? statsOf(),
    'GET /flashcards/session': (url) => (session ? session(url) : sessionOf([a, b, c])),
    'POST /flashcards/review': (_url, init) =>
      review ? review(JSON.parse(String(init?.body))) : { status: 'review', interval_days: 1 },
    'GET /vocab/groups': () => groups,
  })
}
const word = (wrapper: { find: (s: string) => { text: () => string } }) =>
  wrapper.find('[data-testid="word"]').text()
/** A button by its label. A string matches the start of the text, since rating buttons also show their interval. */
const button = (
  wrapper: { findAll: (selector: string) => DOMWrapper<Element>[] },
  text: string | RegExp,
) =>
  wrapper
    .findAll('button')
    .find((b) =>
      typeof text === 'string'
        ? b.text() === text || (RATINGS.has(text) && b.text().startsWith(text))
        : text.test(b.text()),
    )!
const reviews = (mock: ReturnType<typeof api>) =>
  mock
    .to('POST', '/flashcards/review')
    .map((call) => call.body as { vocabulary_id: number; rating: number })

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('the start screen', () => {
  it('shows what is due, what is new, today’s work and the streak', async () => {
    api()
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    const stat = (key: string) => wrapper.find(`[data-testid="stat-${key}"]`).text()
    expect([stat('due'), stat('new'), stat('today'), stat('streak')]).toEqual([
      '3',
      '5',
      '7',
      '4 days',
    ])
    expect(wrapper.text()).toContain('2 of 20 new today')
    expect(button(wrapper, 'Study 8 cards')).toBeTruthy() // due + new available
  })

  it('invites you to add words when the study list is empty', async () => {
    api({ stats: statsOf({ total_cards: 0, due_now: 0, new_available: 0, new_waiting: 0 }) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    expect(wrapper.text()).toContain('Your study list is empty')
    expect(wrapper.find('a[href="/lookup"]').exists()).toBe(true)
    expect(button(wrapper, /Start studying/).attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('Choose what to study')
  })

  it('shows a failure to load with a way to retry', async () => {
    let calls = 0
    mockApi({
      'GET /flashcards/stats': () => (++calls === 1 ? failure(500, 'internal_error') : statsOf()),
      'GET /vocab/groups': () => groups,
    })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    expect(wrapper.find('[role="alert"]').text()).toContain('Something went wrong')
    await button(wrapper, 'Try again').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="stat-due"]').text()).toBe('3')
  })

  it.each([
    [
      'the daily limit is reached',
      sessionOf([], { new_waiting: 4, new_allowance: 0 }),
      'reached today’s limit of 20 new cards',
    ],
    ['nothing is due', sessionOf([], { new_waiting: 0 }), 'Nothing is due right now'],
  ])('explains an empty session when %s', async (_name, session, message) => {
    api({ session: () => session })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain(message)
    expect(wrapper.text()).toContain('All caught up')
    expect(wrapper.find('[data-testid="word"]').exists()).toBe(false)
  })

  it('points to the profile when the limit is what stops you', async () => {
    api({ session: () => sessionOf([], { new_waiting: 4, new_allowance: 0 }) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="/profile"]').exists()).toBe(true)
  })

  it('says so when a filter leaves nothing', async () => {
    api({ session: () => sessionOf([], { new_waiting: 0 }) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, 'B1').trigger('click')
    await button(wrapper, 'Start studying').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No cards match these filters')
  })
})

describe('studying', () => {
  it('starts a session with the chosen level and word list', async () => {
    const mock = api()
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, 'A2').trigger('click')
    await wrapper.find('select').setValue('7')
    await button(wrapper, 'Start studying').trigger('click')
    await flushPromises()
    const params = Object.fromEntries(mock.to('GET', '/flashcards/session')[0]!.url.searchParams)
    expect(params).toEqual({ level: 'A2', group_id: '7' })
  })

  it('shows the front, then the answer and the four buttons', async () => {
    api()
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    expect(word(wrapper)).toBe('學')
    expect(wrapper.find('[data-testid="progress"]').text()).toBe('0 of 3')
    expect(wrapper.text()).not.toContain('Good')
    await button(wrapper, 'Show answer').trigger('click')
    expect(
      wrapper.findAll('[role="group"][aria-label="How well did you remember it?"] button'),
    ).toHaveLength(4)
  })

  it('sends each answer, moves on to the next card, and shows the summary at the end', async () => {
    const mock = api()
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    for (const [expected, rating] of [
      ['學', 'Good'],
      ['習', 'Easy'],
      ['女', 'Hard'],
    ] as const) {
      expect(word(wrapper)).toBe(expected)
      await button(wrapper, 'Show answer').trigger('click')
      await button(wrapper, rating).trigger('click')
      await flushPromises()
    }
    expect(reviews(mock)).toEqual([
      { vocabulary_id: 1, rating: 3 },
      { vocabulary_id: 2, rating: 4 },
      { vocabulary_id: 3, rating: 2 },
    ])
    expect(wrapper.text()).toContain('Session complete')
    expect(wrapper.text()).toContain('You finished 3 cards with 3 answers.')
    expect(wrapper.text()).toContain('67% remembered') // good and easy of three answers
    expect(mock.to('GET', '/flashcards/stats')).toHaveLength(2) // fresh numbers after the session
  })

  it('brings a card answered "again" back before the end', async () => {
    const mock = api({ session: () => sessionOf([a, b]) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    const order: string[] = []
    for (const rating of ['Again', 'Good', 'Good'] as const) {
      order.push(word(wrapper))
      await button(wrapper, 'Show answer').trigger('click')
      await button(wrapper, rating).trigger('click')
      await flushPromises()
    }
    expect(order).toEqual(['學', '習', '學']) // 學 returns after 習
    expect(reviews(mock).map((r) => r.vocabulary_id)).toEqual([1, 2, 1])
    expect(wrapper.text()).toContain('You finished 2 cards with 3 answers.')
    expect(wrapper.text()).toContain('Again: 1')
  })

  it('works from the keyboard', async () => {
    const mock = api({ session: () => sessionOf([a, b]) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    press('3') // not revealed yet: nothing happens
    await flushPromises()
    expect(reviews(mock)).toEqual([])
    press(' ')
    await flushPromises()
    press('3')
    await flushPromises()
    press('Enter')
    await flushPromises()
    press('4')
    await flushPromises()
    expect(reviews(mock)).toEqual([
      { vocabulary_id: 1, rating: 3 },
      { vocabulary_id: 2, rating: 4 },
    ])
  })

  it('does not send a second answer while the first is being saved', async () => {
    let release!: () => void
    const slow = new Promise<void>((r) => (release = r))
    const mock = mockApi({
      'GET /flashcards/stats': () => statsOf(),
      'GET /flashcards/session': () => sessionOf([a, b]),
      'POST /flashcards/review': async () => {
        await slow
        return { status: 'review' }
      },
      'GET /vocab/groups': () => groups,
    })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    await button(wrapper, 'Show answer').trigger('click')
    press('3')
    press('3')
    press('4')
    await flushPromises()
    expect(wrapper.text()).toContain('Saving…')
    expect(mock.to('POST', '/flashcards/review')).toHaveLength(1)
    release()
    await flushPromises()
    expect(word(wrapper)).toBe('習')
  })

  it('keeps the card on screen when saving fails, so the answer can be sent again', async () => {
    let calls = 0
    const mock = api({
      review: () => (++calls === 1 ? failure(500, 'internal_error') : { status: 'review' }),
    })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    await button(wrapper, 'Show answer').trigger('click')
    await button(wrapper, 'Good').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('Your answer could not be saved.')
    expect(word(wrapper)).toContain('學') // still this card ...
    expect(wrapper.findAll('ruby rt')).not.toHaveLength(0) // ... and still showing its answer
    expect(wrapper.find('[data-testid="progress"]').text()).toBe('0 of 3')
    await button(wrapper, 'Good').trigger('click')
    await flushPromises()
    expect(word(wrapper)).toBe('習')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(reviews(mock)).toHaveLength(2)
  })

  it.each([
    [409, 'not_due'],
    [404, 'not_in_study_list'],
  ])('moves on quietly when the server says %s %s (answered elsewhere)', async (status, code) => {
    let calls = 0
    api({ review: () => (++calls === 1 ? failure(status, code) : { status: 'review' }) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    await button(wrapper, 'Show answer').trigger('click')
    await button(wrapper, 'Good').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(word(wrapper)).toBe('習')
    expect(wrapper.find('[data-testid="progress"]').text()).toBe('1 of 3') // counted as done, not as an answer
  })

  it('stops and goes back to the start screen with fresh numbers', async () => {
    const mock = api()
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    await button(wrapper, 'Stop').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="stat-due"]').exists()).toBe(true)
    expect(mock.to('GET', '/flashcards/stats')).toHaveLength(2)
  })

  it('offers more studying after a session', async () => {
    const mock = api({ session: () => sessionOf([a]) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    await button(wrapper, 'Show answer').trigger('click')
    await button(wrapper, 'Good').trigger('click')
    await flushPromises()
    await button(wrapper, 'Study more').trigger('click')
    await flushPromises()
    expect(mock.to('GET', '/flashcards/session')).toHaveLength(2)
    expect(word(wrapper)).toBe('學')
  })

  it('shows the word in the reader’s chosen script and reading', async () => {
    localStorage.setItem('prefs.v1', JSON.stringify({ script: 'simplified', reading: 'pinyin' }))
    api({ session: () => sessionOf([a]) })
    const { wrapper } = await mountAt(FlashcardsView, '/flashcards', routes)
    await button(wrapper, /Study/).trigger('click')
    await flushPromises()
    expect(word(wrapper)).toBe('学')
    await button(wrapper, 'Show answer').trigger('click')
    expect(wrapper.findAll('ruby rt').map((r) => r.text())).toEqual(['xué'])
  })
})
