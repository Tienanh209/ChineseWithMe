import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import { i18n } from '@/i18n'
import en from '@/i18n/en'
import vi from '@/i18n/vi'
import { errorText } from '../errors'

describe('errorText', () => {
  it('translates known API error codes and never shows server messages', () => {
    i18n.global.locale.value = 'en'
    const error = new ApiError(409, 'email_taken', 'server english text')
    expect(errorText(error)).toBe(en.errors.email_taken)
    i18n.global.locale.value = 'vi'
    expect(errorText(error)).toBe(vi.errors.email_taken)
  })

  it('falls back to the generic message for unknown codes and other errors', () => {
    i18n.global.locale.value = 'en'
    expect(errorText(new ApiError(500, 'internal_error', 'boom'))).toBe(en.errors.generic)
    expect(errorText(new TypeError('x'))).toBe(en.errors.generic)
  })

  it('has a translation for every error code the backend can return to the UI', () => {
    const codes = [
      'invalid_credentials',
      'email_taken',
      'rate_limited',
      'validation_error',
      'invalid_token',
      'username_taken',
      'last_login_method',
      'google_account_conflict',
      'google_email_unverified',
      'google_account_in_use',
      'google_already_linked',
      'invalid_google_token',
      'google_not_configured',
      'not_authenticated',
      'csrf_failed',
      'reauth_required',
      'already_verified',
    ]
    for (const code of codes) {
      expect(en.errors).toHaveProperty(code)
      expect(vi.errors).toHaveProperty(code)
    }
  })
})
