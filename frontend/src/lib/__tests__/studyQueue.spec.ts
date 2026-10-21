import { describe, expect, it } from 'vitest'
import { card } from '@/test/helpers'
import { answer, current, intervalLabel, isDone, recall, skip, startQueue } from '../studyQueue'

const a = card({ vocabulary_id: 1 })
const b = card({ vocabulary_id: 2 })
const c = card({ vocabulary_id: 3 })
const ids = (q: ReturnType<typeof startQueue>) => q.waiting.map((x) => x.vocabulary_id)

describe('the study queue', () => {
  it('starts with every card waiting and nothing counted', () => {
    const q = startQueue([a, b, c])
    expect(ids(q)).toEqual([1, 2, 3])
    expect(current(q)).toBe(a)
    expect([q.finished, q.total, q.answers, q.again, q.remembered]).toEqual([0, 3, 0, 0, 0])
    expect(isDone(q)).toBe(false)
  })

  it('an empty queue is done and has no current card', () => {
    const q = startQueue([])
    expect(isDone(q)).toBe(true)
    expect(current(q)).toBeNull()
    expect(answer(q, 3)).toBe(q) // nothing to answer: unchanged
  })

  it('finishes a card answered hard, good or easy', () => {
    for (const rating of [2, 3, 4] as const) {
      const q = answer(startQueue([a, b]), rating)
      expect(ids(q)).toEqual([2])
      expect(q.finished).toBe(1)
      expect(q.answers).toBe(1)
    }
  })

  it('sends a card answered again to the back, without finishing it', () => {
    const q = answer(startQueue([a, b, c]), 1)
    expect(ids(q)).toEqual([2, 3, 1])
    expect([q.finished, q.total, q.answers, q.again]).toEqual([0, 3, 1, 1])
    // and it can come round again and again
    const later = answer(answer(answer(q, 3), 3), 1)
    expect(ids(later)).toEqual([1])
    expect([later.finished, later.again]).toEqual([2, 2])
  })

  it('a lone card answered again comes straight back', () => {
    const q = answer(startQueue([a]), 1)
    expect(ids(q)).toEqual([1])
    expect(isDone(q)).toBe(false)
  })

  it('a card counts as finished once, however many tries it took', () => {
    let q = startQueue([a])
    q = answer(q, 1)
    q = answer(q, 1)
    q = answer(q, 2)
    expect(isDone(q)).toBe(true)
    expect([q.finished, q.total, q.answers, q.again]).toEqual([1, 1, 3, 2])
  })

  it('counts good and easy as remembered, hard and again as not', () => {
    let q = startQueue([a, b, c, card({ vocabulary_id: 4 })])
    for (const rating of [4, 3, 2, 1] as const) q = answer(q, rating)
    expect([q.remembered, q.answers]).toEqual([2, 4])
    expect(recall(q)).toBe(50)
  })

  it('has no recall figure before the first answer, and rounds', () => {
    expect(recall(startQueue([a]))).toBeNull()
    let q = startQueue([a, b, c])
    q = answer(answer(answer(q, 3), 3), 2)
    expect(recall(q)).toBe(67)
  })

  it('skips a card answered elsewhere without counting an answer', () => {
    const q = skip(startQueue([a, b]))
    expect(ids(q)).toEqual([2])
    expect([q.finished, q.answers, q.remembered]).toEqual([1, 0, 0])
    expect(skip(startQueue([]))).toEqual(startQueue([]))
  })

  it('does not change the queue it was given', () => {
    const q = startQueue([a, b])
    answer(q, 1)
    skip(q)
    expect(ids(q)).toEqual([1, 2])
    expect(q.answers).toBe(0)
  })
})

describe('intervalLabel', () => {
  const now = new Date('2026-10-21T03:00:00Z')

  it('shows minutes for an again answer, at least one', () => {
    expect(intervalLabel(0, '2026-10-21T03:10:00Z', now)).toEqual({ unit: 'minutes', n: 10 })
    expect(intervalLabel(0, '2026-10-21T03:04:40Z', now)).toEqual({ unit: 'minutes', n: 5 })
    expect(intervalLabel(0, '2026-10-21T03:00:10Z', now)).toEqual({ unit: 'minutes', n: 1 })
  })

  it('shows days, then months, then years', () => {
    expect(intervalLabel(1, 'x', now)).toEqual({ unit: 'days', n: 1 })
    expect(intervalLabel(29, 'x', now)).toEqual({ unit: 'days', n: 29 })
    expect(intervalLabel(30, 'x', now)).toEqual({ unit: 'months', n: 1 })
    expect(intervalLabel(95, 'x', now)).toEqual({ unit: 'months', n: 3 })
    expect(intervalLabel(364, 'x', now)).toEqual({ unit: 'months', n: 12 })
    expect(intervalLabel(365, 'x', now)).toEqual({ unit: 'years', n: 1 })
    expect(intervalLabel(900, 'x', now)).toEqual({ unit: 'years', n: 2.5 })
  })
})
