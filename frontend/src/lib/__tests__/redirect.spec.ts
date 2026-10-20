import { describe, expect, it } from 'vitest'
import { safeNext } from '../redirect'

describe('safeNext', () => {
  it('accepts same-site paths with query and hash', () => {
    expect(safeNext('/profile')).toBe('/profile')
    expect(safeNext('/lessons?level=B1#top')).toBe('/lessons?level=B1#top')
  })

  it('rejects anything that could leave the site', () => {
    for (const value of [
      'https://evil.example.com',
      '//evil.example.com',
      '/\\evil.example.com',
      'javascript:alert(1)',
      'profile',
      '',
      null,
      undefined,
      ['/a'],
    ]) {
      expect(safeNext(value)).toBeNull()
    }
  })
})
