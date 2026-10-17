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
}

export type MePatch = Partial<Pick<Me, 'target_level' | 'timezone'> & { ui_lang: UiLang }>
