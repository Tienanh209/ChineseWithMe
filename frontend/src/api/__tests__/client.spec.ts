import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../client'

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fn = vi
    .fn<typeof fetch>()
    .mockResolvedValue(
      new Response(body === null ? null : JSON.stringify(body), { status, headers }),
    )
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

describe('api', () => {
  it('sends the CSRF cookie as a header on unsafe requests only', async () => {
    document.cookie = 'csrf_token=abc123'
    const fetch = mockFetch(200, { ok: true })

    await api('/me', { method: 'PATCH', json: { target_level: 'B1' } })
    const [url, patch] = fetch.mock.calls[0]!
    expect(url).toBe('/api/me')
    expect(new Headers(patch?.headers).get('X-CSRF-Token')).toBe('abc123')
    expect(patch?.body).toBe('{"target_level":"B1"}')
    expect(patch?.credentials).toBe('same-origin')

    await api('/me')
    const [, get] = fetch.mock.calls[1]!
    expect(get?.method).toBe('GET')
    expect(new Headers(get?.headers).has('X-CSRF-Token')).toBe(false)
  })

  it('turns the error envelope into ApiError', async () => {
    mockFetch(422, {
      error: {
        code: 'validation_error',
        message: 'bad',
        details: [{ loc: ['body'] }],
        request_id: 'r1',
      },
    })
    const error = await api('/me', { method: 'PATCH', json: {} }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 422, code: 'validation_error', requestId: 'r1' })
  })

  it('reports network failures with a stable code', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new TypeError('offline')))
    await expect(api('/health')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })

  it('returns undefined for 204', async () => {
    mockFetch(204, null)
    await expect(api('/dev/logout', { method: 'POST' })).resolves.toBeUndefined()
  })
})
