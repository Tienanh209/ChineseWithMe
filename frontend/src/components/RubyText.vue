<script setup lang="ts">
/**
 * Chinese text with per-word annotations (pinyin or zhuyin) in <ruby>.
 * When a reading has one space-separated syllable per character (always true for zhuyin,
 * and for pinyin like "nǐ hǎo"), each character gets its own annotation so a wide reading
 * does not push the characters apart. Otherwise ("měitiān") the whole word is annotated.
 * Parts without a reading (punctuation, words not in the dictionary) render plain.
 */
import { computed } from 'vue'

export interface RubyPart {
  text: string
  pinyin?: string | null
  zhuyin?: string | null
}

interface Cell {
  base: string
  rt: string | null
}

const props = withDefaults(
  defineProps<{
    parts: RubyPart[]
    annotation?: 'pinyin' | 'zhuyin' | 'none'
  }>(),
  { annotation: 'pinyin' },
)

const rtLang = computed(() => (props.annotation === 'zhuyin' ? 'zh-Bopo' : 'zh-Latn-pinyin'))

function cells(part: RubyPart): Cell[] {
  const reading =
    props.annotation === 'none' ? null : props.annotation === 'pinyin' ? part.pinyin : part.zhuyin
  if (!reading) return [{ base: part.text, rt: null }]
  const chars = [...part.text] // code points, not UTF-16 units
  const syllables = reading.trim().split(/\s+/)
  if (chars.length > 1 && syllables.length === chars.length) {
    return chars.map((base, i) => ({ base, rt: syllables[i]! }))
  }
  return [{ base: part.text, rt: reading }]
}

// One entry per word, so a line never breaks inside a word.
const words = computed(() => props.parts.map(cells))
</script>

<template>
  <span lang="zh-Hant">
    <span v-for="(word, w) in words" :key="w" class="whitespace-nowrap">
      <template v-for="(cell, i) in word" :key="i">
        <ruby v-if="cell.rt" class="annotated"
          >{{ cell.base }}<rp>(</rp><rt :lang="rtLang">{{ cell.rt }}</rt
          ><rp>)</rp></ruby
        >
        <template v-else>{{ cell.base }}</template>
      </template>
    </span>
  </span>
</template>
