# English-Arabic-English Dictionary Collection

A comprehensive collection of bilingual English-Arabic dictionaries extracted from StarDict/Flexidict format and converted to CSV.

## Dictionaries

| File | Description | Direction | Entries |
|------|-------------|-----------|---------|
| `Babylon_English_Arabic.csv` | Babylon English-Arabic Dictionary | ENG → ARA | 51,362 |
| `Babylon_Arabic_English.csv` | Babylon Arabic-English Dictionary | ARA → ENG | 67,011 |
| `English_Arabic.csv` | English-Arabic Dictionary | ENG → ARA | 65,110 |
| `English_Arabic_Glossary.csv` | English-Arabic Glossary | ENG → ARA | 66,884 |
| `Medicine_English_Arabic.csv` | Medical English-Arabic Dictionary | ENG → ARA | 65,595 |
| `Concise_English_Arabic.csv` | A Concise English-Arabic Dictionary | ENG → ARA | 22,284 |
| `Arabic_Dictionary.csv` | Arabic Dictionary (English-Arabic) | ENG → ARA | 149,082 |
| `eng_ara_eng_combined.csv` | **Combined** — all dictionaries merged | Both | 487,328 |

## CSV Format

### Individual dictionaries
- **Babylon_English_Arabic.csv**: `english, arabic, definition_raw, source`
- **Babylon_Arabic_English.csv**: `arabic, english, definition_raw, source`
- **Others**: `english, arabic, definition_raw, source` (or `arabic, english` for ARA→ENG)

### Combined file
- **eng_ara_eng_combined.csv**: `english, arabic, source`

## Source

Extracted from StarDict/Flexidict format (`eng - ara - eng.zip`) containing:
- Babylon English-Arabic & Arabic-English dictionaries
- English-Arabic dictionary, glossary, and medical dictionary
- A Concise English-Arabic Dictionary (by Dr. Mohammad Moslem Mohammad)
- ArabEyes/FreeDict Arabic dictionary

## License

The original dictionaries retain their respective licenses. The Babylon dictionaries are © Babylon Ltd. The Concise dictionary is by Dr. Mohammad Moslem Mohammad. The Arabic dictionary is from ArabEyes under GPL.
