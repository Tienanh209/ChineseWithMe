import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { usePrefsStore } from '../prefs'

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('script and reading preferences', () => {
  it('start as Traditional with zhuyin', () => {
    const prefs = usePrefsStore()
    expect([prefs.script, prefs.reading]).toEqual(['traditional', 'zhuyin'])
  })

  it('are remembered on this device', async () => {
    const prefs = usePrefsStore()
    prefs.setScript('simplified')
    prefs.setReading('pinyin')
    await nextTick()
    expect(JSON.parse(localStorage.getItem('prefs.v1')!)).toMatchObject({
      script: 'simplified',
      reading: 'pinyin',
    })

    setActivePinia(createPinia())
    const again = usePrefsStore()
    expect([again.script, again.reading]).toEqual(['simplified', 'pinyin'])
  })

  it('ignore values that are not one of the options', () => {
    localStorage.setItem('prefs.v1', '{"script":"cursive","reading":"ruby"}')
    const prefs = usePrefsStore()
    expect([prefs.script, prefs.reading]).toEqual(['traditional', 'zhuyin'])
  })
})
