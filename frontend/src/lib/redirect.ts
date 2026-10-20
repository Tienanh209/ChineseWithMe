/** A post-login redirect target taken from ?next=. Only same-site paths pass, so a crafted
 *  link cannot send someone to another origin after they sign in. */
export function safeNext(value: unknown): string | null {
  if (typeof value !== 'string') return null
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null
  return value
}
