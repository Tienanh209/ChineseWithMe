/**
 * The queue of one flashcard session, as pure functions. A card answered "again" goes to the back, so it
 * comes round again before the session ends; any other answer finishes the card.
 */
import type { Card, Rating } from '@/api/flashcards'

export interface Queue {
  /** Cards still to answer; the first is on screen. */
  waiting: Card[]
  /** Cards finished: answered hard, good or easy (each counts once, however many tries it took). */
  finished: number
  total: number
  /** Every answer given, "again" included. */
  answers: number
  again: number
  /** Answers that were good or easy. */
  remembered: number
}

export const startQueue = (cards: Card[]): Queue => ({
  waiting: [...cards],
  finished: 0,
  total: cards.length,
  answers: 0,
  again: 0,
  remembered: 0,
})

export const current = (queue: Queue): Card | null => queue.waiting[0] ?? null
export const isDone = (queue: Queue): boolean => queue.waiting.length === 0

/** The queue after the first card has been answered. */
export function answer(queue: Queue, rating: Rating): Queue {
  const [first, ...rest] = queue.waiting
  if (!first) return queue
  const again = rating === 1
  return {
    ...queue,
    waiting: again ? [...rest, first] : rest,
    finished: queue.finished + (again ? 0 : 1),
    answers: queue.answers + 1,
    again: queue.again + (again ? 1 : 0),
    remembered: queue.remembered + (rating >= 3 ? 1 : 0),
  }
}

/** The card is already done elsewhere (another tab answered it): drop it without counting an answer. */
export function skip(queue: Queue): Queue {
  const [first, ...rest] = queue.waiting
  if (!first) return queue
  return { ...queue, waiting: rest, finished: queue.finished + 1 }
}

/** Percentage of answers that were good or easy; null before any answer. */
export const recall = (queue: Queue): number | null =>
  queue.answers === 0 ? null : Math.round((queue.remembered / queue.answers) * 100)

export type IntervalLabel =
  { unit: 'minutes'; n: number } | { unit: 'days' | 'months' | 'years'; n: number }

/** "10 min", "1 day", "3 months": the interval a button promises. */
export function intervalLabel(intervalDays: number, dueAt: string, now: Date): IntervalLabel {
  if (intervalDays === 0) {
    const minutes = Math.max(1, Math.round((new Date(dueAt).getTime() - now.getTime()) / 60000))
    return { unit: 'minutes', n: minutes }
  }
  if (intervalDays < 30) return { unit: 'days', n: intervalDays }
  if (intervalDays < 365) return { unit: 'months', n: Math.round(intervalDays / 30) }
  return { unit: 'years', n: Math.round((intervalDays / 365) * 10) / 10 }
}
