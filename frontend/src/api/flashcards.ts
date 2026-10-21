import { api } from './client'
import type { Level } from './types'

export type Rating = 1 | 2 | 3 | 4 // again, hard, good, easy

export interface CardExample {
  hanzi: string
  pinyin: string | null
  zhuyin: string | null
  translations: Record<string, string>
  audio_url: string | null
}

/** What answering with `rating` would do: shown on the button. */
export interface NextOption {
  rating: Rating
  interval_days: number // 0 means minutes
  due_at: string
}

export interface Card {
  vocabulary_id: number
  traditional: string
  simplified: string
  pinyin: string
  zhuyin: string | null
  part_of_speech: string | null
  level: Level
  audio_url: string | null
  meanings: Record<string, string[]>
  example: CardExample | null
  status: 'new' | 'learning' | 'review' | 'mastered'
  is_new: boolean
  interval_days: number
  repetitions: number
  next: NextOption[]
}

export interface SessionResponse {
  cards: Card[]
  due_total: number
  new_waiting: number
  new_allowance: number
  new_today: number
  daily_new_cards: number
}

export interface Stats {
  due_now: number
  new_waiting: number
  new_allowance: number
  new_available: number
  new_today: number
  daily_new_cards: number
  reviewed_today: number
  studied_today: boolean
  streak_days: number
  total_cards: number
}

export interface ReviewResult {
  vocabulary_id: number
  status: string
  interval_days: number
  repetitions: number
  lapses: number
  ease_factor: number
  next_review_at: string
}

export interface SessionParams {
  level?: Level | null
  group_id?: number | null
  limit?: number
}

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const getSession = (params: SessionParams = {}, signal?: AbortSignal) =>
  api<SessionResponse>(`/flashcards/session${query({ ...params })}`, { signal })

export const getStats = (signal?: AbortSignal) => api<Stats>('/flashcards/stats', { signal })

export const submitReview = (vocabularyId: number, rating: Rating) =>
  api<ReviewResult>('/flashcards/review', {
    method: 'POST',
    json: { vocabulary_id: vocabularyId, rating },
  })
