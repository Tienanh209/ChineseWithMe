/**
 * Fetch wrapper for /api. Same-origin cookies carry the session; unsafe requests echo
 * the csrf_token cookie in X-CSRF-Token. Non-2xx responses become ApiError, built
 * from the backend's error envelope {error: {code, message, details, request_id}}.
 */

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown = null,
    readonly requestId: string | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export function readCookie(name: string): string | null {
  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const item = part.trim()
    if (item.startsWith(prefix)) return decodeURIComponent(item.slice(prefix.length))
  }
  return null
}

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...rest } = init
  const method = (rest.method ?? (json === undefined ? 'GET' : 'POST')).toUpperCase()
  const headers = new Headers(rest.headers)
  headers.set('Accept', 'application/json')
  if (json !== undefined) headers.set('Content-Type', 'application/json')
  if (UNSAFE.has(method)) {
    const csrf = readCookie('csrf_token')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...rest,
      method,
      headers,
      credentials: 'same-origin',
      body: json === undefined ? rest.body : JSON.stringify(json),
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Network request failed.')
  }

  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const error = body?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? response.statusText,
      error?.details ?? null,
      error?.request_id ?? response.headers.get('X-Request-ID'),
    )
  }
  return body as T
}
