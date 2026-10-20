import { ApiError } from '@/api/client'
import { i18n } from '@/i18n'

/** User-facing text for any thrown value: the translated message for the API error code,
 *  or the generic one. Never shows server messages (English, for developers). */
export function errorText(error: unknown): string {
  const { t, te } = i18n.global
  if (error instanceof ApiError && te(`errors.${error.code}`)) return t(`errors.${error.code}`)
  return t('errors.generic')
}
