import { afterEach, describe, expect, it, vi } from 'vitest'
import { addToStudyList, getVocab, queryString, searchVocab } from '../vocab'
import { mockApi } from '@/test/helpers'

afterEach(() => vi.unstubAllGlobals())

describe('queryString', () => {
  it('leaves out null, undefined and empty values and encodes the rest', () => {
    expect(queryString({ q: 'nǐ hǎo', level: null, page: undefined, group_id: '' })).toBe(
      '?q=n%C7%90+h%C7%8Eo',
    )
    expect(queryString({ q: '', level: null })).toBe('')
    expect(queryString({ page: 2, level: 'A1' })).toBe('?page=2&level=A1')
    expect(queryString({ q: '100% & more=less' })).toBe('?q=100%25+%26+more%3Dless')
  })
})

describe('vocab api', () => {
  it('searches with the filters it was given', async () => {
    const api = mockApi({ 'GET /vocab': () => ({ items: [], total: 0, page: 1, page_size: 20 }) })
    await searchVocab({ q: '學', level: 'A2', group_id: 3, page: 2, page_size: 20 })
    const [call] = api.calls
    expect(call!.url.searchParams.get('q')).toBe('學')
    expect(Object.fromEntries(call!.url.searchParams)).toEqual({
      q: '學',
      level: 'A2',
      group_id: '3',
      page: '2',
      page_size: '20',
    })
    await searchVocab({})
    expect(api.calls[1]!.url.search).toBe('')
  })

  it('passes the abort signal through', async () => {
    mockApi({ 'GET /vocab': () => ({}) })
    const controller = new AbortController()
    await searchVocab({ q: 'a' }, controller.signal)
    expect(vi.mocked(fetch).mock.calls[0]![1]!.signal).toBe(controller.signal)
  })

  it('asks for the detail in the reader’s language', async () => {
    const api = mockApi({ 'GET /vocab/7': () => ({}) })
    await getVocab(7, 'en')
    expect(api.calls[0]!.url.search).toBe('?lang=en')
  })

  it('adds to the study list with a POST', async () => {
    const api = mockApi({
      'POST /study-list/7': () => ({ added: true, status: 'new', next_review_at: 'x' }),
    })
    const result = await addToStudyList(7)
    expect(result.added).toBe(true)
    expect(api.calls[0]!.method).toBe('POST')
  })
})
