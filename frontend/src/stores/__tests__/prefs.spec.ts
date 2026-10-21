import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import type { Me } from '@/api/types'
import { usePrefsStore } from '../prefs'
import { useSessionStore } from '../session'

const me: Me = {
  id: 1,
  email: 'test@example.com',
  email_verified: true,
  username: 'tester',
  display_name: 'Test User',
  avatar_url: null,
  target_level: 'B2',
  ui_lang: 'en',
  timezone: 'Asia/Ho_Chi_Minh',
  role: 'user',
  daily_new_cards: 20,
  has_password: true,
  google_linked: false,
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('prefs store', () => {
  it('keeps choices in localStorage when signed out, without calling the API', async () => {
    const prefs = usePrefsStore()
    const update = vi.spyOn(useSessionStore(), 'update')
    await prefs.setLevel('B1')
    prefs.setTheme('dark')
    await nextTick()
    expect(update).not.toHaveBeenCalled()
    expect(JSON.parse(localStorage.getItem('prefs.v1')!)).toMatchObject({
      level: 'B1',
      theme: 'dark',
    })

    setActivePinia(createPinia())
    expect(usePrefsStore().level).toBe('B1')
  })

  it('ignores corrupt stored values', () => {
    localStorage.setItem('prefs.v1', '{"level":"Z9","lang":"fr","theme":"neon"}')
    const prefs = usePrefsStore()
    expect(prefs.level).toBe('A1')
    expect(['vi', 'en']).toContain(prefs.lang)
    expect(prefs.theme).toBe('system')
  })

  it("adopts the account's level and language on sign-in and saves changes to it", async () => {
    const session = useSessionStore()
    const prefs = usePrefsStore()
    const update = vi.spyOn(session, 'update').mockResolvedValue()

    session.me = me
    await nextTick()
    expect(prefs.level).toBe('B2')
    expect(prefs.lang).toBe('en')

    await prefs.setLevel('C1')
    expect(update).toHaveBeenCalledWith({ target_level: 'C1' })
    await prefs.setLang('vi')
    expect(update).toHaveBeenCalledWith({ ui_lang: 'vi' })
  })
})
