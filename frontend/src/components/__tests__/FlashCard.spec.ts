import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { i18n } from '@/i18n'
import { usePrefsStore } from '@/stores/prefs'
import { card, press } from '@/test/helpers'
import FlashCard from '../FlashCard.vue'

const now = new Date()
let pinia = createPinia()
const mountCard = (props: Record<string, unknown> = {}) =>
  mount(FlashCard, {
    props: { card: card(), revealed: false, busy: false, now, ...props },
    global: { plugins: [pinia, i18n] },
    attachTo: document.body,
  })

let wrapper: ReturnType<typeof mountCard> | null = null
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia) // the component and the test must share one store
  i18n.global.locale.value = 'en'
  usePrefsStore().setLang('en')
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('the front', () => {
  it('shows only the word and a button to reveal the answer', () => {
    wrapper = mountCard()
    expect(wrapper.find('[data-testid="word"]').text()).toBe('學習')
    expect(wrapper.find('ruby').exists()).toBe(false) // no reading yet
    expect(wrapper.text()).not.toContain('to study')
    expect(wrapper.text()).toContain('Show answer')
    expect(wrapper.findAll('button').some((b) => b.text() === 'Good')).toBe(false)
  })

  it('shows the word in simplified characters when chosen, and marks new cards', () => {
    usePrefsStore().setScript('simplified')
    wrapper = mountCard({ card: card({ is_new: true, status: 'new' }) })
    expect(wrapper.find('[data-testid="word"]').text()).toBe('学习')
    expect(wrapper.text()).toContain('New')
    expect(wrapper.text()).toContain('A2')
  })

  it('reveals on the button', async () => {
    wrapper = mountCard()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Show answer')!
      .trigger('click')
    expect(wrapper.emitted('reveal')).toHaveLength(1)
  })
})

describe('the back', () => {
  it('shows the reading over the word, both readings, meanings with the reader’s language first, and the example', () => {
    wrapper = mountCard({
      revealed: true,
      card: card({
        example: {
          hanzi: '我每天學習。',
          pinyin: 'wǒ měitiān xuéxí.',
          zhuyin: 'ㄨㄛˇ ㄇㄟˇ ㄊㄧㄢ。',
          translations: { vi: 'Mỗi ngày tôi học.', en: 'I study every day.' },
          audio_url: '/audio/e.mp3',
        },
      }),
    })
    expect(wrapper.findAll('ruby rt').map((r) => r.text())).toEqual(['ㄒㄩㄝˊ', 'ㄒㄧˊ']) // zhuyin by default
    expect(wrapper.text()).toContain('xuéxí · ㄒㄩㄝˊ ㄒㄧˊ')
    const lines = wrapper.findAll('li').map((li) => li.text())
    expect(lines[0]).toContain('to study; to learn') // English first for an English reader
    expect(lines[1]).toContain('học tập')
    expect(wrapper.text()).toContain('我每天學習。')
    expect(wrapper.text()).toContain('ㄨㄛˇ ㄇㄟˇ ㄊㄧㄢ。')
    expect(wrapper.text()).toContain('I study every day.')
    expect(wrapper.find('button[aria-label="Play audio"]').exists()).toBe(true) // the example's audio
    expect(wrapper.text()).not.toContain('Show answer')
  })

  it('uses pinyin when chosen, and falls back to pinyin for an example without zhuyin', () => {
    usePrefsStore().setReading('pinyin')
    wrapper = mountCard({
      revealed: true,
      card: card({
        example: { hanzi: '好。', pinyin: 'hǎo.', zhuyin: null, translations: {}, audio_url: null },
      }),
    })
    expect(wrapper.findAll('ruby rt').map((r) => r.text())).toEqual(['xuéxí'])
    expect(wrapper.text()).toContain('hǎo.')
  })

  it('puts Vietnamese first for a Vietnamese reader', () => {
    usePrefsStore().setLang('vi')
    wrapper = mountCard({ revealed: true })
    expect(wrapper.findAll('li')[0]!.text()).toContain('học tập')
  })

  it('offers the four answers, each with what it would schedule', () => {
    wrapper = mountCard({ revealed: true })
    const buttons = wrapper
      .findAll('[role="group"] button')
      .map((b) => b.findAll('span').map((span) => span.text()))
    expect(buttons).toEqual([
      ['Again', '10 min'],
      ['Hard', '7 days'],
      ['Good', '15 days'],
      ['Easy', '2 months'],
    ])
  })

  it('answers with the rating of the button pressed', async () => {
    wrapper = mountCard({ revealed: true })
    const buttons = wrapper.findAll('[role="group"] button')
    for (const button of buttons) await button.trigger('click')
    expect(wrapper.emitted('rate')!.map((e) => e[0])).toEqual([1, 2, 3, 4])
  })

  it('disables the answers while one is being saved', () => {
    wrapper = mountCard({ revealed: true, busy: true })
    expect(
      wrapper.findAll('[role="group"] button').every((b) => b.attributes('disabled') !== undefined),
    ).toBe(true)
  })

  it('wraps a minutes label singularly and in Vietnamese', () => {
    usePrefsStore().setLang('vi')
    i18n.global.locale.value = 'vi'
    wrapper = mountCard({ revealed: true })
    expect(wrapper.findAll('[role="group"] button')[0]!.text()).toContain('10 phút')
    expect(wrapper.findAll('[role="group"] button')[1]!.text()).toContain('7 ngày')
  })
})

describe('the keyboard', () => {
  it('Space and Enter reveal the answer', () => {
    wrapper = mountCard()
    press(' ')
    press('Enter')
    expect(wrapper.emitted('reveal')).toHaveLength(2)
    expect(wrapper.emitted('rate')).toBeUndefined()
  })

  it('keys 1 to 4 answer once the answer is showing, and do nothing before', () => {
    wrapper = mountCard()
    press('3')
    expect(wrapper.emitted('rate')).toBeUndefined()
    wrapper.unmount()
    wrapper = mountCard({ revealed: true })
    for (const key of ['1', '2', '3', '4']) press(key)
    expect(wrapper.emitted('rate')!.map((e) => e[0])).toEqual([1, 2, 3, 4])
  })

  it('ignores other keys, modifier combinations and keys typed into form fields', () => {
    wrapper = mountCard({ revealed: true })
    press('5')
    press('0')
    press('a')
    press('3', { ctrlKey: true })
    press('3', { metaKey: true })
    press('3', { altKey: true })
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.dispatchEvent(new KeyboardEvent('keydown', { key: '3', bubbles: true }))
    input.remove()
    expect(wrapper.emitted('rate')).toBeUndefined()
  })

  it('ignores the keyboard while an answer is being saved', () => {
    wrapper = mountCard({ revealed: true, busy: true })
    press('3')
    expect(wrapper.emitted('rate')).toBeUndefined()
  })

  it('stops listening when the card goes away', () => {
    wrapper = mountCard({ revealed: true })
    const mounted = wrapper
    wrapper.unmount()
    wrapper = null
    press('3')
    expect(mounted.emitted('rate')).toBeUndefined()
  })
})
