/**
 * Target level, UI language and theme. Signed in: the server (users.target_level,
 * users.ui_lang) is the source of truth and changes are saved there. Signed out: kept
 * in localStorage. On sign-in the account's values replace the local ones. The theme
 * is per device and never leaves localStorage.
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { LEVELS, UI_LANGS, type Level, type UiLang } from '@/api/types'
import { useSessionStore } from './session'

export type Theme = 'system' | 'light' | 'dark'
const STORAGE_KEY = 'prefs.v1'

interface Stored {
  level?: string
  lang?: string
  theme?: string
}

function readStored(): Stored {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Stored
  } catch {
    return {}
  }
}

function writeStored(value: Stored) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Private mode or storage disabled: preferences last for this tab only.
  }
}

function browserLang(): UiLang {
  return navigator.language?.toLowerCase().startsWith('en') ? 'en' : 'vi'
}

const isLevel = (v: unknown): v is Level => LEVELS.includes(v as Level)
const isLang = (v: unknown): v is UiLang => UI_LANGS.includes(v as UiLang)
const isTheme = (v: unknown): v is Theme => v === 'system' || v === 'light' || v === 'dark'

export const usePrefsStore = defineStore('prefs', () => {
  const session = useSessionStore()
  const stored = readStored()

  const level = ref<Level>(isLevel(stored.level) ? stored.level : 'A1')
  const lang = ref<UiLang>(isLang(stored.lang) ? stored.lang : browserLang())
  const theme = ref<Theme>(isTheme(stored.theme) ? stored.theme : 'system')

  // Adopt the account's settings whenever someone signs in.
  watch(
    () => session.me,
    (me) => {
      if (!me) return
      level.value = me.target_level
      if (isLang(me.ui_lang)) lang.value = me.ui_lang
    },
    { immediate: true },
  )

  watch([level, lang, theme], () =>
    writeStored({ level: level.value, lang: lang.value, theme: theme.value }),
  )

  async function setLevel(value: Level) {
    level.value = value
    if (session.me && session.me.target_level !== value)
      await session.update({ target_level: value })
  }

  async function setLang(value: UiLang) {
    lang.value = value
    if (session.me && session.me.ui_lang !== value) await session.update({ ui_lang: value })
  }

  function setTheme(value: Theme) {
    theme.value = value
  }

  const signedIn = computed(() => session.me !== null)

  return { level, lang, theme, signedIn, setLevel, setLang, setTheme }
})
