/** The look-up page the reader was last on (with its query, filters and page), so a word's
 *  "Back to search" returns there even after they moved between readings of the same characters. */
let path: string | null = null

export const rememberLookup = (fullPath: string) => {
  path = fullPath
}
export const forgetLookup = () => {
  path = null
}
export const lastLookup = () => path ?? '/lookup'
