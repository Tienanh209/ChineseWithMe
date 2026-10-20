import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { forgetLookup, rememberLookup } from '@/lib/lastLookup'
import { usePrefsStore } from '@/stores/prefs'
import { detail, failure, mockApi, mountAt, signIn, stub } from '@/test/helpers'
import VocabDetailView from '../VocabDetailView.vue'

const routes = [
  { path: '/lookup', name: 'lookup', component: stub },
  { path: '/login', name: 'login', component: stub },
  {
    path: '/vocab/:id',
    name: 'vocab',
    component: VocabDetailView,
    props: (route: { params: Record<string, string> }) => ({ id: Number(route.params.id) }),
  },
]

const xing = detail({
  id: 5,
  traditional: '行',
  simplified: '行',
  pinyin: 'xíng',
  zhuyin: 'ㄒㄧㄥˊ',
  translations: [
    { lang: 'en', meanings: ['OK', 'to walk'] },
    { lang: 'vi', meanings: ['được', 'ổn'] },
  ],
  readings: [
    {
      id: 5,
      pinyin: 'xíng',
      zhuyin: 'ㄒㄧㄥˊ',
      part_of_speech: 'verb',
      level: 'A2',
      meaning: 'OK',
      current: true,
    },
    {
      id: 6,
      pinyin: 'háng',
      zhuyin: 'ㄏㄤˊ',
      part_of_speech: 'noun',
      level: 'B1',
      meaning: 'row; line of business',
      current: false,
    },
  ],
})

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

const mountWord = (path = '/vocab/1', api = mockApi({ 'GET /vocab/1': () => detail() })) =>
  mountAt(VocabDetailView, path, routes, { id: Number(path.split('/')[2]) }).then((result) => ({
    ...result,
    api,
  }))

describe('the word', () => {
  it('shows the word with its reading over each character, level and meanings', async () => {
    const { wrapper } = await mountWord()
    expect(wrapper.find('h1').text()).toContain('學')
    expect(wrapper.findAll('ruby rt').map((r) => r.text())).toEqual(['ㄒㄩㄝˊ', 'ㄒㄧˊ']) // zhuyin by default
    expect(wrapper.text()).toContain('A2')
    expect(wrapper.text()).toContain('verb')
    expect(wrapper.text()).toContain('Simplified: 学习')
    const meanings = wrapper.find('section[aria-labelledby="h-meanings"]')
    expect(meanings.findAll('h3').map((h) => h.text().toLowerCase())).toEqual([
      'english',
      'tiếng việt',
    ])
    expect(meanings.findAll('li').map((li) => li.text())).toEqual([
      'to study',
      'to learn',
      'học tập',
    ])
  })

  it('asks the server for the reader’s language', async () => {
    localStorage.setItem('prefs.v1', JSON.stringify({ lang: 'vi' }))
    const api = mockApi({ 'GET /vocab/1': () => detail() })
    await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    expect(api.calls[0]!.url.searchParams.get('lang')).toBe('vi')
  })

  it('reloads in the new language when the reader switches', async () => {
    localStorage.setItem('prefs.v1', JSON.stringify({ lang: 'vi' }))
    const api = mockApi({ 'GET /vocab/1': () => detail() })
    await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    usePrefsStore().setLang('en')
    await flushPromises()
    expect(api.to('GET', '/vocab/1').map((c) => c.url.searchParams.get('lang'))).toEqual([
      'vi',
      'en',
    ])
  })

  it('switches to pinyin and to simplified characters, and says what the other form is', async () => {
    const { wrapper } = await mountWord()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Pinyin')!
      .trigger('click')
    expect(wrapper.findAll('ruby rt').map((r) => r.text())).toEqual(['xuéxí']) // joined pinyin sits over the whole word
    await wrapper.find('button[aria-label="Simplified"]').trigger('click')
    expect(wrapper.find('h1').text()).toContain('学')
    expect(wrapper.find('h1').text()).not.toContain('學')
    expect(wrapper.text()).toContain('Traditional: 學習')
    expect(wrapper.text()).not.toContain('Simplified: 学习')
    // and the choice is remembered for the next page
    expect(JSON.parse(localStorage.getItem('prefs.v1')!)).toMatchObject({
      script: 'simplified',
      reading: 'pinyin',
    })
  })

  it('does not mention a second form when the two are the same', async () => {
    mockApi({ 'GET /vocab/5': () => xing })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/5', routes, { id: 5 })
    expect(wrapper.text()).not.toContain('Simplified:')
    expect(wrapper.text()).not.toContain('Traditional:')
  })
})

describe('readings of the same characters', () => {
  it('lists the other reading as a link and marks the current one', async () => {
    mockApi({ 'GET /vocab/5': () => xing })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/5', routes, { id: 5 })
    const section = wrapper.find('section[aria-labelledby="h-readings"]')
    expect(section.find('[aria-current]').text()).toContain('ㄒㄧㄥˊ')
    const links = section.findAll('a')
    expect(links).toHaveLength(1)
    expect(links[0]!.attributes('href')).toBe('/vocab/6')
    expect(links[0]!.text()).toContain('ㄏㄤˊ')
    expect(links[0]!.text()).toContain('row; line of business')
    expect(links[0]!.text()).toContain('B1')
  })

  it('shows no readings section for a word with one reading', async () => {
    const { wrapper } = await mountWord()
    expect(wrapper.find('section[aria-labelledby="h-readings"]').exists()).toBe(false)
  })

  it('loads the other reading when its link is followed', async () => {
    const api = mockApi({
      'GET /vocab/5': () => xing,
      'GET /vocab/6': () => detail({ id: 6, traditional: '行', pinyin: 'háng', zhuyin: 'ㄏㄤˊ' }),
    })
    const { wrapper, router } = await mountAt(VocabDetailView, '/vocab/5', routes, { id: 5 })
    await wrapper.find('section[aria-labelledby="h-readings"] a').trigger('click')
    await flushPromises()
    await wrapper.setProps({ id: 6 }) // the router would do this for the real route
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/vocab/6')
    expect(api.to('GET', '/vocab/6')).toHaveLength(1)
    expect(wrapper.text()).toContain('háng')
  })
})

describe('examples, audio and lists', () => {
  const withExamples = detail({
    audio_url: '/audio/v/xuexi.mp3',
    examples: [
      {
        id: 1,
        hanzi: '我每天學習中文。',
        pinyin: 'wǒ měitiān xuéxí Zhōngwén.',
        zhuyin: 'ㄨㄛˇ ㄇㄟˇ ㄊㄧㄢ。',
        translations: { en: 'I study Chinese every day.', vi: 'Mỗi ngày tôi học tiếng Trung.' },
        audio_url: '/audio/v/e1.mp3',
      },
      {
        id: 2,
        hanzi: '學習需要耐心。',
        pinyin: 'xuéxí xūyào nàixīn.',
        zhuyin: null,
        translations: {},
        audio_url: null,
      },
    ],
    groups: [{ id: 7, name: 'Daily life', level: 'A2' }],
  })

  it('shows examples with the reading the reader chose and their translations, reader’s language first', async () => {
    mockApi({ 'GET /vocab/1': () => withExamples })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    usePrefsStore().setLang('en')
    await flushPromises()
    const [first, second] = wrapper.findAll('section[aria-labelledby="h-examples"] li')
    expect(first!.text()).toContain('我每天學習中文。')
    expect(first!.text()).toContain('ㄨㄛˇ ㄇㄟˇ ㄊㄧㄢ。') // zhuyin by default
    const lines = first!.findAll('p').map((p) => p.text())
    expect(lines.findIndex((l) => l.includes('I study'))).toBeLessThan(
      lines.findIndex((l) => l.includes('Mỗi ngày')),
    )
    expect(second!.text()).toContain('xuéxí xūyào nàixīn.') // no zhuyin for this one: falls back to pinyin
  })

  it('plays audio only where there is some', async () => {
    mockApi({ 'GET /vocab/1': () => withExamples })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    expect(wrapper.findAll('button[aria-label="Play audio"]')).toHaveLength(2) // the word and the first example
  })

  it('links each word list to the look-up filtered by it', async () => {
    mockApi({ 'GET /vocab/1': () => withExamples })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    expect(wrapper.find('section[aria-labelledby="h-groups"] a').attributes('href')).toBe(
      '/lookup?group=7',
    )
  })

  it('leaves out sections it has nothing for', async () => {
    const { wrapper } = await mountWord()
    expect(wrapper.find('section[aria-labelledby="h-examples"]').exists()).toBe(false)
    expect(wrapper.find('section[aria-labelledby="h-groups"]').exists()).toBe(false)
  })
})

describe('study list', () => {
  it('offers sign-in when signed out', async () => {
    const { wrapper } = await mountWord()
    expect(wrapper.text()).toContain('Sign in to add to your study list')
  })

  it('adds the word and keeps the button gone afterwards', async () => {
    const api = mockApi({
      'GET /vocab/1': () => detail(),
      'POST /study-list/1': () => ({ added: true, status: 'new', next_review_at: 'now' }),
    })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    signIn()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Add to study list')!
      .trigger('click')
    await flushPromises()
    expect(api.to('POST', '/study-list/1')).toHaveLength(1)
    expect(wrapper.text()).toContain('In your study list')
    expect(wrapper.findAll('button').some((b) => b.text() === 'Add to study list')).toBe(false)
  })

  it('shows a word that is already there as added', async () => {
    mockApi({ 'GET /vocab/1': () => detail({ study: { status: 'review', next_review_at: 'x' } }) })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    expect(wrapper.text()).toContain('In your study list')
  })
})

describe('problems', () => {
  it('says so when the word does not exist', async () => {
    mockApi({ 'GET /vocab/404': () => failure(404, 'not_found') })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/404', routes, { id: 404 })
    expect(wrapper.find('[role="alert"]').text()).toBe('This word does not exist.')
    expect(wrapper.find('h1').exists()).toBe(false)
  })

  it('offers a retry after a server error', async () => {
    let calls = 0
    mockApi({ 'GET /vocab/1': () => (++calls === 1 ? failure(500, 'internal_error') : detail()) })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/1', routes, { id: 1 })
    expect(wrapper.find('[role="alert"]').text()).toContain('Could not load this word.')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Try again')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.find('h1').exists()).toBe(true)
  })

  it('links back to the search the reader was on, not to the previous word', async () => {
    forgetLookup()
    mockApi({ 'GET /vocab/5': () => xing, 'GET /vocab/6': () => detail({ id: 6 }) })
    const { wrapper } = await mountAt(VocabDetailView, '/vocab/5', routes, { id: 5 })
    const back = () => wrapper.findAll('a').find((a) => a.text().includes('Back to search'))!
    expect(back().attributes('href')).toBe('/lookup') // nothing remembered: a fresh search
    rememberLookup('/lookup?q=%E8%A1%8C&level=A2&page=2')
    const again = await mountAt(VocabDetailView, '/vocab/5', routes, { id: 5 })
    const link = again.wrapper.findAll('a').find((a) => a.text().includes('Back to search'))!
    expect(link.attributes('href')).toBe('/lookup?q=%E8%A1%8C&level=A2&page=2')
    // moving to the other reading changes nothing about where "back" leads
    await again.wrapper.find('section[aria-labelledby="h-readings"] a').trigger('click')
    await flushPromises()
    await again.wrapper.setProps({ id: 6 })
    await flushPromises()
    expect(
      again.wrapper
        .findAll('a')
        .find((a) => a.text().includes('Back to search'))!
        .attributes('href'),
    ).toBe('/lookup?q=%E8%A1%8C&level=A2&page=2')
    forgetLookup()
  })
})
