import { api } from './client'
import type { Level } from './types'

export interface VocabItem {
  id: number
  traditional: string
  simplified: string
  pinyin: string
  zhuyin: string | null
  part_of_speech: string | null
  level: Level
  audio_url: string | null
  /** language -> meanings, in order */
  meanings: Record<string, string[]>
  /** null when signed out */
  in_study_list: boolean | null
}

export interface SearchResponse {
  items: VocabItem[]
  total: number
  page: number
  page_size: number
}

export interface LevelCount {
  level: Level
  count: number
}

export interface VocabGroup {
  id: number
  name: string
  description: string | null
  level: Level | null
  count: number
}

export interface Translation {
  lang: string
  meanings: string[]
}

export interface Example {
  id: number
  hanzi: string
  pinyin: string | null
  zhuyin: string | null
  translations: Record<string, string>
  audio_url: string | null
}

export interface Reading {
  id: number
  pinyin: string
  zhuyin: string | null
  part_of_speech: string | null
  level: Level
  meaning: string | null
  current: boolean
}

export interface StudyState {
  status: string
  next_review_at: string
}

export interface VocabDetail {
  id: number
  traditional: string
  simplified: string
  pinyin: string
  zhuyin: string | null
  part_of_speech: string | null
  level: Level
  audio_url: string | null
  translations: Translation[]
  examples: Example[]
  readings: Reading[]
  groups: { id: number; name: string; level: Level | null }[]
  study: StudyState | null
}

export interface SearchParams {
  q?: string
  level?: Level | null
  group_id?: number | null
  page?: number
  page_size?: number
}

/** ?a=1&b=x from a params object, leaving out null, undefined and empty values. */
export function queryString(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const searchVocab = (params: SearchParams, signal?: AbortSignal) =>
  api<SearchResponse>(`/vocab${queryString({ ...params })}`, { signal })

export const getVocab = (id: number, lang: string, signal?: AbortSignal) =>
  api<VocabDetail>(`/vocab/${id}${queryString({ lang })}`, { signal })

export const getLevels = (signal?: AbortSignal) => api<LevelCount[]>('/vocab/levels', { signal })

export const getGroups = (signal?: AbortSignal) => api<VocabGroup[]>('/vocab/groups', { signal })

export const addToStudyList = (id: number) =>
  api<StudyState & { added: boolean }>(`/study-list/${id}`, { method: 'POST' })
