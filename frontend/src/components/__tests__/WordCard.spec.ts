import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { i18n } from '@/i18n'
import { usePrefsStore } from '@/stores/prefs'
import { item, makeRouter, stub } from '@/test/helpers'
import WordCard from '../WordCard.vue'

let prefs: ReturnType<typeof usePrefsStore>
const mountCard = async (overrides = {}) => {
  const router = makeRouter([
    { path: '/', component: stub },
    { path: '/vocab/:id', name: 'vocab', component: stub },
  ])
  await router.push('/')
  return mount(WordCard, {
    props: { item: item(overrides) },
    global: { plugins: [createPinia(), i18n, router] },
  })
}

beforeEach(() => {
  localStorage.clear()
  const pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'en'
  prefs = usePrefsStore()
  prefs.setLang('en')
})

describe('WordCard', () => {
  it('shows traditional characters with zhuyin by default and links to the word', async () => {
    const card = await mountCard()
    expect(card.text()).toContain('學習')
    expect(card.text()).toContain('ㄒㄩㄝˊ ㄒㄧˊ')
    expect(card.text()).not.toContain('xuéxí')
    expect(card.attributes('href')).toBe('/vocab/1')
    expect(card.text()).toContain('A2')
    expect(card.text()).toContain('verb')
  })

  it('follows the script and reading preferences', async () => {
    prefs.setScript('simplified')
    prefs.setReading('pinyin')
    const card = await mountCard()
    expect(card.text()).toContain('学习')
    expect(card.text()).not.toContain('學習')
    expect(card.text()).toContain('xuéxí')
    expect(card.find('[lang="zh-Hans"]').exists()).toBe(true)
  })

  it('falls back to pinyin for a word that has no zhuyin', async () => {
    const card = await mountCard({ zhuyin: null })
    expect(card.text()).toContain('xuéxí')
  })

  it('lists the reader’s language first and at most three meanings', async () => {
    const english = await mountCard({
      meanings: { vi: ['a'], en: ['one', 'two', 'three', 'four'] },
    })
    expect(english.text()).toContain('one; two; three')
    expect(english.text()).not.toContain('four')
    prefs.setLang('vi')
    const vietnamese = await mountCard({ meanings: { vi: ['học tập'], en: ['to study'] } })
    expect(vietnamese.text()).toContain('học tập')
    expect(vietnamese.text()).not.toContain('to study')
  })

  it('uses whatever language exists when the reader’s is missing', async () => {
    const card = await mountCard({ meanings: { fr: ['étudier'] } })
    expect(card.text()).toContain('étudier')
  })

  it('marks words already in the study list, and only those', async () => {
    expect((await mountCard({ in_study_list: true })).find('[role="img"]').exists()).toBe(true)
    expect((await mountCard({ in_study_list: false })).find('[role="img"]').exists()).toBe(false)
    expect((await mountCard({ in_study_list: null })).find('[role="img"]').exists()).toBe(false)
  })
})
