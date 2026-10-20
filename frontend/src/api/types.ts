export const LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'] as const
export type Level = (typeof LEVELS)[number]

export const UI_LANGS = ['vi', 'en'] as const
export type UiLang = (typeof UI_LANGS)[number]

export interface Me {
  id: number
  email: string
  email_verified: boolean
  username: string | null
  display_name: string | null
  avatar_url: string | null
  target_level: Level
  ui_lang: string
  timezone: string
  role: 'user' | 'admin'
  has_password: boolean
  google_linked: boolean
}

/** Omitted fields stay unchanged; only display_name, username and avatar_url accept null. */
export interface MePatch {
  display_name?: string | null
  username?: string | null
  avatar_url?: string | null
  target_level?: Level
  ui_lang?: UiLang
  timezone?: string
}

export interface RegisterBody {
  email: string
  password: string
  display_name?: string
  ui_lang?: UiLang
  target_level?: Level
}

export interface AuthConfig {
  google_client_id: string | null
}
