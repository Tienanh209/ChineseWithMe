import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { vi } from 'vitest'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Me } from '@/api/types'
import type { VocabDetail, VocabItem } from '@/api/vocab'
import { i18n } from '@/i18n'
import { useSessionStore } from '@/stores/session'

export const stub = { template: '<div />' }

export function makeRouter(routes: Parameters<typeof createRouter>[0]['routes']) {
  return createRouter({ history: createMemoryHistory(), routes })
}

/** Mount with a fresh Pinia, English UI and the given router already at `path`. */
export async function mountAt(
  component: Component,
  path: string,
  routes: Parameters<typeof createRouter>[0]['routes'],
  props: Record<string, unknown> = {},
): Promise<{ wrapper: VueWrapper; router: ReturnType<typeof makeRouter> }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  i18n.global.locale.value = 'en'
  const router = makeRouter(routes)
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, { props, global: { plugins: [pinia, i18n, router] } })
  await flushPromises()
  return { wrapper, router }
}

export const signedInUser: Me = {
  id: 1,
  email: 'a@example.com',
  email_verified: true,
  username: null,
  display_name: null,
  avatar_url: null,
  target_level: 'A1',
  ui_lang: 'en',
  timezone: 'Asia/Ho_Chi_Minh',
  role: 'user',
  has_password: true,
  google_linked: false,
}

export function signIn() {
  useSessionStore().me = signedInUser
}

export type Handler = (
  url: URL,
  init?: RequestInit,
) => unknown | Response | Promise<unknown | Response>

/** Replace fetch: handlers are looked up by "METHOD /path" (query string ignored).
 *  Returned values become JSON 200 responses unless they already are a Response. */
export function mockApi(handlers: Record<string, Handler>) {
  const calls: { method: string; path: string; url: URL; body: unknown }[] = []
  const fn = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    const method = (init?.method ?? 'GET').toUpperCase()
    const path = url.pathname.replace(/^\/api/, '')
    calls.push({ method, path, url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    const handler = handlers[`${method} ${path}`]
    if (!handler)
      return new Response(JSON.stringify({ error: { code: 'not_found' } }), { status: 404 })
    const out = await handler(url, init)
    return out instanceof Response ? out : new Response(JSON.stringify(out), { status: 200 })
  })
  vi.stubGlobal('fetch', fn)
  return {
    calls,
    fn,
    to: (method: string, path: string) =>
      calls.filter((c) => c.method === method && c.path === path),
  }
}

export const failure = (status: number, code: string) =>
  new Response(
    JSON.stringify({ error: { code, message: code, details: null, request_id: null } }),
    { status },
  )

export function item(overrides: Partial<VocabItem> = {}): VocabItem {
  return {
    id: 1,
    traditional: '學習',
    simplified: '学习',
    pinyin: 'xuéxí',
    zhuyin: 'ㄒㄩㄝˊ ㄒㄧˊ',
    part_of_speech: 'verb',
    level: 'A2',
    audio_url: null,
    meanings: { vi: ['học tập'], en: ['to study', 'to learn'] },
    in_study_list: null,
    ...overrides,
  }
}

export function detail(overrides: Partial<VocabDetail> = {}): VocabDetail {
  return {
    id: 1,
    traditional: '學習',
    simplified: '学习',
    pinyin: 'xuéxí',
    zhuyin: 'ㄒㄩㄝˊ ㄒㄧˊ',
    part_of_speech: 'verb',
    level: 'A2',
    audio_url: null,
    translations: [
      { lang: 'en', meanings: ['to study', 'to learn'] },
      { lang: 'vi', meanings: ['học tập'] },
    ],
    examples: [],
    readings: [
      {
        id: 1,
        pinyin: 'xuéxí',
        zhuyin: 'ㄒㄩㄝˊ ㄒㄧˊ',
        part_of_speech: 'verb',
        level: 'A2',
        meaning: 'to study',
        current: true,
      },
    ],
    groups: [],
    study: null,
    ...overrides,
  }
}

/** A promise you resolve by hand, to control the order in which responses arrive. */
export function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}
