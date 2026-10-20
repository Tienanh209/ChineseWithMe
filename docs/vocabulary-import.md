# Vocabulary import

Loads words, meanings, example sentences and group membership from a CSV or JSON file. Safe to
run again: the same file gives "unchanged" for every row. Examples to copy:
[`examples/vocabulary.csv`](examples/vocabulary.csv), [`examples/vocabulary.json`](examples/vocabulary.json).

## Run it

```sh
cd backend
uv run python -m app.cli import-vocab ../docs/examples/vocabulary.csv --dry-run      # look first
uv run python -m app.cli import-vocab ../docs/examples/vocabulary.csv --group "TOCFL Band A"
```

| Option | Meaning |
|---|---|
| `--dry-run` | Run everything, report exactly what would happen, save nothing. |
| `--strict` | If any row is rejected, save nothing. Without it, good rows are saved and bad rows are reported. |
| `--group NAME` | Also add every word to this group. Repeat for several groups. |
| `--format csv\|json` | Default: from the file extension, else from the content. |
| `--report FILE` | Write the full report (every rejected row) as JSON. |

Exit code: `0` everything fine, `3` some rows were rejected, `2` the file could not be read.

Admins can also `POST /api/admin/vocabulary/import` with the file as the request body
(`Content-Type: text/csv` or `application/json`; query: `dry_run`, `strict`, `group`, `format`).
Limits there: 5 MB and 5000 rows. Use the command line for larger files.

## Words

A word is identified by **traditional + pinyin**, so 行 xíng and 行 háng are two entries.

| Field | Required | Rules |
|---|---|---|
| `traditional` | yes | Chinese characters, no spaces, up to 30. |
| `simplified` | no | Same as `traditional` when blank (for a new word). |
| `pinyin` | yes | **Tone marks**, not numbers: `nǐ hǎo`, not `ni3 hao3`. Write `ü`, not `v`. Stored lowercase with single spaces (capital letters are lowercased). Needs at least one tone mark, except a single neutral syllable such as `de`. |
| `zhuyin` | no | Bopomofo with `ˊ ˇ ˋ ˙`: `ㄋㄧˇ ㄏㄠˇ`. |
| `part_of_speech` | no | Free text up to 30 characters. |
| `level` | yes | `A1` `A2` `B1` `B2` `C1` `C2` (any case). |
| `audio_path` | no | Path inside the audio bucket, like `vocabulary/xuexi.mp3`. Not a URL, no leading `/`. |
| meanings | yes, at least one | See below. |
| examples | no | See below. |
| groups | no | Group names; created if they do not exist. |

`pinyin_normalized` (the toneless search column) is computed by the database and is never part of the file.

## CSV

One row per word. Header names are case-insensitive. Separator `,` or `;` (Excel in Vietnamese
and many European locales writes `;`) or tab, detected from the header. Save as **UTF-8**
(in Excel: "CSV UTF-8"). Unknown columns are an error, so a typo cannot silently drop data.

- Meanings: one column per language named by its two-letter code (`vi`, `en`, ...); several
  meanings in one cell are separated by `;`.
- Groups: `groups`, separated by `;`.
- One example per row: `example_hanzi`, `example_pinyin`, `example_zhuyin`,
  `example_audio_path`, and `example_<lang>` for its translations. For several examples use JSON.
- The row number in reports is the line number in the file (the header is line 1).

## JSON

A list of words, or `{"words": [...]}`. Each word has the fields above plus:

```json
"translations": {"vi": ["học tập", "học"], "en": ["to study"]},
"examples": [{"hanzi": "...", "pinyin": "...", "zhuyin": "...",
              "translations": {"vi": "...", "en": "..."}, "audio_path": "..."}],
"groups": ["Daily life"]
```

A single meaning can be written as plain text instead of a list. Unknown keys are an error.
The row number in reports is the position in the list (the first word is 1).

## What re-importing does

- **New word:** created. **Existing word:** changed only where the file differs.
  `level` always follows the file. `simplified`, `zhuyin`, `part_of_speech` and `audio_path` follow
  the file only when the file gives a value; leaving one blank never erases what is stored.
- **Meanings:** for each language in the file, the stored meanings become exactly the file's list,
  in its order (meanings not listed are removed). Languages not in the file are untouched.
- **Examples:** when the file lists any, the stored examples become exactly those (matched by
  sentence; others are removed). A row with no examples leaves stored examples alone.
- **Groups are additive:** words are added to the listed groups, and nothing is ever removed.
- The same word and pinyin twice in one file: the second row is rejected.

## The report

```
8 rows: 6 created, 1 updated, 0 unchanged, 1 rejected; 2 groups created
  row 6: 銀行 (yin2hang2)
      - pinyin: use tone marks (nǐ), not tone numbers (ni3)
```

A rejected row is skipped and explained; it never stops the other rows (unless `--strict`).
A file that cannot be read at all (bad JSON, missing required columns, unknown columns, not
UTF-8) imports nothing and says why.
