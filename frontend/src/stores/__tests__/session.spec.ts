import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '../session'

const me = {
  id: 1,
  email: 'a@example.com',
  email_verified: false,
  username: null,
  display_name: null,
  avatar_url: null,
  target_level: 'A1',
  ui_lang: 'vi',
  timezone: 'Asia/Ho_Chi_Minh',
  role: 'user',
  has_password: true,
  google_linked: false,
}

function respond(status: number, body: unknown) {
  return new Response(body === null ? null : JSON.stringify(body), { status })
}

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>

beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn<typeof fetch>()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

const lastCall = () => {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]!
  return { url, method: init?.method, body: init?.body && JSON.parse(String(init.body)) }
}

describe('session store', () => {
  it('treats 401 from /me as signed out but rethrows other failures', async () => {
    const session = useSessionStore()
    fetchMock.mockResolvedValueOnce(respond(401, { error: { code: 'not_authenticated' } }))
    await session.load()
    expect(session.me).toBeNull()
    expect(session.loaded).toBe(true)

    fetchMock.mockResolvedValueOnce(respond(500, { error: { code: 'internal_error' } }))
    await expect(session.load()).rejects.toMatchObject({ status: 500 })
  })

  it('ensureLoaded shares one request between callers', async () => {
    const session = useSessionStore()
    fetchMock.mockResolvedValue(respond(200, me))
    await Promise.all([session.ensureLoaded(), session.ensureLoaded()])
    await session.ensureLoaded()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(session.me?.email).toBe('a@example.com')
  })

  it('login and register post credentials and keep the returned user', async () => {
    const session = useSessionStore()
    fetchMock.mockResolvedValueOnce(respond(200, me))
    await session.login('a@example.com', 'secret-pass')
    expect(lastCall()).toMatchObject({
      url: '/api/auth/login',
      method: 'POST',
      body: { email: 'a@example.com', password: 'secret-pass' },
    })
    expect(session.me?.id).toBe(1)

    fetchMock.mockResolvedValueOnce(respond(201, me))
    await session.register({
      email: 'a@example.com',
      password: 'secret-pass',
      ui_lang: 'en',
      target_level: 'B1',
    })
    expect(lastCall().body).toMatchObject({ ui_lang: 'en', target_level: 'B1' })
  })

  it('a failed login leaves the user signed out and surfaces the error code', async () => {
    const session = useSessionStore()
    fetchMock.mockResolvedValueOnce(
      respond(401, { error: { code: 'invalid_credentials', message: 'x' } }),
    )
    await expect(session.login('a@example.com', 'nope-nope')).rejects.toMatchObject({
      code: 'invalid_credentials',
    })
    expect(session.me).toBeNull()
  })

  it('logout, google login and delete use the right endpoints', async () => {
    const session = useSessionStore()
    fetchMock.mockResolvedValueOnce(
      respond(200, { ...me, google_linked: true, has_password: false }),
    )
    await session.loginWithGoogle('jwt')
    expect(lastCall()).toMatchObject({ url: '/api/auth/google', body: { credential: 'jwt' } })

    fetchMock.mockResolvedValueOnce(respond(204, null))
    await session.deleteAccount({ credential: 'jwt2' })
    expect(lastCall()).toMatchObject({
      url: '/api/me',
      method: 'DELETE',
      body: { credential: 'jwt2' },
    })
    expect(session.me).toBeNull()

    session.me = me as never
    fetchMock.mockResolvedValueOnce(respond(204, null))
    await session.logout()
    expect(lastCall()).toMatchObject({ url: '/api/auth/logout', method: 'POST' })
    expect(session.me).toBeNull()
  })

  it('loadConfig falls back to no Google when the request fails', async () => {
    const session = useSessionStore()
    fetchMock.mockRejectedValueOnce(new TypeError('offline'))
    await session.loadConfig()
    expect(session.googleClientId).toBe('')
  })
})
