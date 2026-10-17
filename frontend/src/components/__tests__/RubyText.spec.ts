import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import RubyText from '../RubyText.vue'

const parts = [{ text: '學習', pinyin: 'xuéxí', zhuyin: 'ㄒㄩㄝˊ ㄒㄧˊ' }, { text: '。' }]

describe('RubyText', () => {
  it('annotates words with pinyin and leaves unannotated parts plain', () => {
    const wrapper = mount(RubyText, { props: { parts, annotation: 'pinyin' } })
    const rubies = wrapper.findAll('ruby')
    expect(rubies).toHaveLength(1)
    expect(rubies[0]!.find('rt').text()).toBe('xuéxí')
    expect(wrapper.text()).toContain('。')
    expect(wrapper.attributes('lang')).toBe('zh-Hant')
  })

  it('annotates zhuyin per character when there is one syllable per character', () => {
    const wrapper = mount(RubyText, { props: { parts, annotation: 'zhuyin' } })
    const rubies = wrapper.findAll('ruby')
    expect(rubies.map((r) => r.find('rt').text())).toEqual(['ㄒㄩㄝˊ', 'ㄒㄧˊ'])
    expect(rubies.map((r) => r.text().slice(0, 1))).toEqual(['學', '習'])
    expect(rubies[0]!.find('rt').attributes('lang')).toBe('zh-Bopo')
  })

  it('splits spaced pinyin per character but keeps joined pinyin on the word', () => {
    const wrapper = mount(RubyText, {
      props: {
        parts: [
          { text: '你好', pinyin: 'nǐ hǎo' },
          { text: '每天', pinyin: 'měitiān' },
        ],
      },
    })
    expect(wrapper.findAll('rt').map((r) => r.text())).toEqual(['nǐ', 'hǎo', 'měitiān'])
  })

  it('counts characters outside the BMP as one', () => {
    const wrapper = mount(RubyText, {
      props: { parts: [{ text: '𠮷野', zhuyin: 'ㄐㄧˊ ㄧㄝˇ' }], annotation: 'zhuyin' },
    })
    expect(wrapper.findAll('ruby')).toHaveLength(2)
  })

  it('renders plain text when annotation is off', () => {
    const wrapper = mount(RubyText, { props: { parts, annotation: 'none' } })
    expect(wrapper.find('ruby').exists()).toBe(false)
    expect(wrapper.text()).toBe('學習。')
  })

  it('keeps each word on one line', () => {
    const wrapper = mount(RubyText, { props: { parts, annotation: 'zhuyin' } })
    const words = wrapper.findAll('span.whitespace-nowrap')
    expect(words.map((w) => w.findAll('ruby').length)).toEqual([2, 0])
  })
})
