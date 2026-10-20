/**
 * Target level, UI language and theme. Signed in: the server (users.target_level,
 * users.ui_lang) is the source of truth and changes are saved there. Signed out: kept
 * in localStorage. On sign-in the account's values replace the local ones. The theme
 * is per device and never leaves localStorage, like the script and reading used to show Chinese.
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { LEVELS, UI_LANGS, type Level, type UiLang } from '@/api/types'
import { useSessionStore } from './session'

export type Theme = 'system' | 'light' | 'dark'
/** How Chinese words are shown everywhere: which characters, and which reading goes with them. */
export type Script = 'traditional' | 'simplified'
export type Reading = 'zhuyin' | 'pinyin'
const STORAGE_KEY = 'prefs.v1'

interface Stored {
  level?: string
  lang?: string
  theme?: string
  script?: string
  reading?: string
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
const isScript = (v: unknown): v is Script => v === 'traditional' || v === 'simplified'
const isReading = (v: unknown): v is Reading => v === 'zhuyin' || v === 'pinyin'

export const usePrefsStore = defineStore('prefs', () => {
  const session = useSessionStore()
  const stored = readStored()

  const level = ref<Level>(isLevel(stored.level) ? stored.level : 'A1')
  const lang = ref<UiLang>(isLang(stored.lang) ? stored.lang : browserLang())
  const theme = ref<Theme>(isTheme(stored.theme) ? stored.theme : 'system')
  // The product's two pairings are Traditional + zhuyin and Simplified + pinyin; start with the first.
  const script = ref<Script>(isScript(stored.script) ? stored.script : 'traditional')
  const reading = ref<Reading>(isReading(stored.reading) ? stored.reading : 'zhuyin')

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

  watch([level, lang, theme, script, reading], () =>
    writeStored({
      level: level.value,
      lang: lang.value,
      theme: theme.value,
      script: script.value,
      reading: reading.value,
    }),
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

  function setScript(value: Script) {
    script.value = value
  }

  function setReading(value: Reading) {
    reading.value = value
  }

  return {
    level,
    lang,
    theme,
    script,
    reading,
    signedIn,
    setLevel,
    setLang,
    setTheme,
    setScript,
    setReading,
  }
})
