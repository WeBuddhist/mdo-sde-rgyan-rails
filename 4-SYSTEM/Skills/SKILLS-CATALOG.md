# Skills Catalog

Every skill installed in this vault, grouped by the stage of the pipeline it belongs to. Each entry states what the skill does, what it needs, and what it produces, and links to the `SKILL.md` that operationalises it.

**Read this file before starting any task.** If a skill covers what you are about to do, open its `SKILL.md` and follow it exactly. A task done without its skill must be redone — the skills exist so that citation format, file locations and frontmatter come out the same every time, whoever or whatever does the work.

Most of these skills are installed copies from a shared skill library. Fix a skill there and re-sync rather than patching the copy here; see [`../Guidelines/skills-system.md`](../Guidelines/skills-system.md). Skills marked **[vault-local]** belong to this text alone and are never synced away.

The pipeline reads top to bottom.

```
intake ─→ format ─→ structure ─→ segment & ID ─→ metadata
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            ▼                       ▼                       ▼
                      section rails            verse rails            terminology
                            │                       │                       │
                            └───────────┬───────────┴───────────┬───────────┘
                                        ▼                       ▼
                                  claims & wiki           transformations
                                                                │
                                                          QA and checking
```

---

## 1. Intake — raw material into `1-SOURCES/`

### `epub-to-markdown`
Converts an EPUB into structured markdown, inspecting the book's own internal structure first and then either reusing a publisher-specific converter or writing one for it. Converters live in `epub-to-markdown/converters/`.
→ [`epub-to-markdown/SKILL.md`](epub-to-markdown/SKILL.md)

### `json-to-source-text`
Converts JSON exports of root texts (canonical-text databases, scraped corpora) into formatted source-text markdown. New source schemas get their own converter under `json-to-source-text/converters/`.
→ [`json-to-source-text/SKILL.md`](json-to-source-text/SKILL.md)

### `json-to-commentary`
The same for commentary exports, handling the heading and verse-key structure commentaries carry.
→ [`json-to-commentary/SKILL.md`](json-to-commentary/SKILL.md)

### `raw-to-sources`
Brings one raw OCR or segmentation file into `1-SOURCES/` as a cleaned, frontmattered root text or commentary — the first step of the ingest chain.
→ [`raw-to-sources/SKILL.md`](raw-to-sources/SKILL.md)

### `clean-raw-text`
Inspects a raw text for **mechanical** damage — page markers, running headers, OCR index numbers, stray spacing, encoding artefacts — profiles what it finds, and applies a reviewed cleanup. Never touches wording.
→ [`clean-raw-text/SKILL.md`](clean-raw-text/SKILL.md)

### `tibetan-ocr-quality`
Scores a Tibetan OCR file's perplexity against a language model, so a bad scan is caught before anyone spends time formatting it.
→ [`tibetan-ocr-quality/SKILL.md`](tibetan-ocr-quality/SKILL.md)

---

## 2. Formatting

**OCR repair happens in `format-commentary`, and nowhere else.** The segmentation and block-ID skills are bound by a no-loss rule and cannot fix a character.

### `format-root-text`
Formats and normalises a root-text file that is not Tibetan or Sanskrit: frontmatter, heading structure with `^N-0` anchors, block IDs, verse layout, chapter 0.
→ [`format-root-text/SKILL.md`](format-root-text/SKILL.md)

### `format-tibetan-root-text`
The Tibetan path: clean verse with `^chapter-verse` IDs, chapter headings with anchors, one stanza per block, shad-based line splitting.
→ [`format-tibetan-root-text/SKILL.md`](format-tibetan-root-text/SKILL.md)

### `format-sanskrit-root-text`
The Sanskrit path, using the four-zone scheme (pre-title, front matter, chapter verses, colophons) described in [`../Guidelines/annotation-conventions.md`](../Guidelines/annotation-conventions.md) §1b.
→ [`format-sanskrit-root-text/SKILL.md`](format-sanskrit-root-text/SKILL.md)

### `format-commentary`
Formats a commentary: repairs OCR damage, structures the headings, normalises spacing and punctuation, and applies block IDs.
→ [`format-commentary/SKILL.md`](format-commentary/SKILL.md)

---

## 3. Structure and table of contents

### `toc-generate`
Builds a text's structural outline end to end where the commentary announces its own divisions inline (the Tibetan *sa bcad* case): scan for candidates, copy the division announcements verbatim, reconcile them into one nested decimal tree, verify that tree against the source with two deterministic checkers, and ingest it back into the text as headings with block IDs. Phases are separately addressable.
→ [`toc-generate/SKILL.md`](toc-generate/SKILL.md)

### `structural-outline-ingest`
The alternative route for a text whose structure is stated rather than announced: extract the outline and write it to `2-RAILS/Sections/Raw/outline/`. Run this before verse packages — macro structure shapes how every verse under it is read.
→ [`structural-outline-ingest/SKILL.md`](structural-outline-ingest/SKILL.md)

### `outline-extract`
Extracts an outline a commentary already states explicitly and emits it as a standalone nested file.
→ [`outline-extract/SKILL.md`](outline-extract/SKILL.md)

### `add-toc`
Generates a nested, decimal-numbered table of contents from a flat draft list at the top of a document. The `^toc-X-Y-Z` IDs it writes are a **separate namespace** from heading anchors.
→ [`add-toc/SKILL.md`](add-toc/SKILL.md)

### `tag-inline-toc`
Finds the inline structural-announcement phrases in a formatted text, wraps the announced terms in wikilinks pointing at the headings they introduce, and inserts the standalone outline block. Optional — only for texts that actually contain such announcements.
→ [`tag-inline-toc/SKILL.md`](tag-inline-toc/SKILL.md)

### `spine-map`
Builds one commentary's routing index from its own outline nodes onto the canonical spine slots of the root text. Once per commentary, then reused by every claims run.
→ [`spine-map/SKILL.md`](spine-map/SKILL.md)

---

## 4. Segmentation, block IDs, transclusion

**Block IDs are citations.** Once anything cites a file, re-segmenting it breaks those citations silently. If you must, re-run every downstream rail.

**Segmentation** of root texts and commentaries: the §4a workflows (`root-text-pipeline`, `commentary-pipeline`).

### `segment-commentary`
Breaks a commentary into short, individually referenceable blocks — prose paragraphs, verse stanzas, quotations — so that every claim can later cite one.
→ [`segment-commentary/SKILL.md`](segment-commentary/SKILL.md)

### `add-block-ids`
Adds block IDs so every verse, prose block and heading can be cited and transcluded. Modes for commentaries, root texts, and texts with no internal numbering.
→ [`add-block-ids/SKILL.md`](add-block-ids/SKILL.md)

### `transclusion`
Inserts root-verse transclusion links into a commentary or a second version of the root text, placing each one where the verse becomes relevant.
→ [`transclusion/SKILL.md`](transclusion/SKILL.md)

---

## 4a. Segmentation and TOC workflows — root texts and commentaries

One skill per step, separate for root texts and commentaries, and one pipeline skill each that runs the whole workflow. Shared scripts and TOC prompts: `4-SYSTEM/Skills/seg-toc-lib/`.

*Ported from Nalanda-texts-rails at commit `fd801eb3` (2026-10-15). The optional benchmark harness those skills mention (`4-SYSTEM/scripts/seg-toc-benchmark/`) was not ported.*

#### Root texts

### `root-text-pipeline` **[exists]**
**Runs the whole root-text workflow** on one root text (treatise, praise, ritual, sādhana, prayer, letter — not a commentary): classify → segment → TOC extract (if the text announces parts) → TOC ingest → group → block IDs, with the checks between steps. Verse as one pāda per line and one stanza per block; prose as paragraphs with its verse passages as stanzas; frame headings for front matter and colophons; the text's own top-level parts as headings; block IDs. The printed edition's paragraph breaks are kept.
→ [`root-text-pipeline/SKILL.md`](root-text-pipeline/SKILL.md)

### `root-text-classify` **[exists]**
Step 1 — verse / prose / mixed, or a commentary (stop). Content first, title second. Deterministic.
→ [`root-text-classify/SKILL.md`](root-text-classify/SKILL.md)

### `root-text-segment` **[exists]**
Step 2 — units (pādas, or sentences with verse lines), raw paragraph breaks kept (mid-sentence ones flagged), front matter `ཀླད་ཀྱི་དོན།` and colophons `མཇུག་བྱང།` by pattern; writes the grouping input. Deterministic.
→ [`root-text-segment/SKILL.md`](root-text-segment/SKILL.md)

### `root-text-toc-extract` **[exists]**
Step 3 — heading tree of the text's announced parts in isolated passes (candidates with Type D, enumerations, tree, QC, anchors, QC against the text); no frame nodes; no tree when nothing is announced. Claude subagents.
→ [`root-text-toc-extract/SKILL.md`](root-text-toc-extract/SKILL.md)

### `root-text-toc-ingest` **[exists]**
Step 4 — the tree's top-level parts as `##` headings, the author's opening verses kept with part 1; rewrites the grouping input. Deterministic.
→ [`root-text-toc-ingest/SKILL.md`](root-text-toc-ingest/SKILL.md)

### `root-text-group` **[exists]**
Step 5 — stanzas (verse, by sense, no fixed length) / paragraphs and stanzas (prose), never across a heading or a printed paragraph break; long texts split into parallel parts. Claude subagents (`prompts/stanza-grouping.md`, `prompts/prose-grouping.md`).
→ [`root-text-group/SKILL.md`](root-text-group/SKILL.md)

### `root-text-block-ids` **[exists]**
Step 6 — build the final file, refuse a bad grouping, stamp IDs, verify the text. Deterministic.
→ [`root-text-block-ids/SKILL.md`](root-text-block-ids/SKILL.md)

#### Commentaries

### `commentary-pipeline` **[exists]**
**Runs the whole commentary workflow** on one commentary: pre-clean → segment into functional units → TOC tree (mode `sabcad` / `verses` / `top` / `labels`) → TOC ingest → meaning-based re-segmentation + QC → body block IDs, with the checks between steps.
→ [`commentary-pipeline/SKILL.md`](commentary-pipeline/SKILL.md)

### `commentary-preclean` **[exists]**
Step 1 (optional) — strip earlier scaffolding (index numbers, IDs, heading markers, per-line breaks) back to continuous prose; footnotes kept. Deterministic.
→ [`commentary-preclean/SKILL.md`](commentary-preclean/SKILL.md)

### `commentary-segment` **[exists]**
Step 2 — deterministic segmentation; `--units --root <root text>` gives the vault's human layout (opener / quoted root verse / whole explanation / frame); `--max-syllables 40` citation-granular. Source spacing preserved; no-loss assertion. Flags `--enum-chain broad`, `--quotes`, `--colophon-guard`, `--stanza-breaks`.
→ [`commentary-segment/SKILL.md`](commentary-segment/SKILL.md)

### `commentary-toc-extract` **[exists]**
Step 3 — full nested decimal sa bcad tree in isolated passes (candidates → verbatim enumerations → tree → QC repair → anchors with frame nodes → QC against the text), then published to `2-RAILS/Sections/Raw/toc-tree/<registered-id>.md` for `section-summary`, `commentary-claims` and `spine-map`; modes `sabcad` / `verses` / `top` / `labels`. Gemini pipeline in `4-SYSTEM/Skills/seg-toc-lib/toc_tree_extractor/` by default, Claude subagents on request.
→ [`commentary-toc-extract/SKILL.md`](commentary-toc-extract/SKILL.md)

### `commentary-toc-ingest` **[exists]**
Step 4 — anchored tree into the segmented commentary as headings with block IDs, the way the human-edited files carry them (stacked parent/first-child headings, frame headings, siblings in text order); text verified unchanged. Deterministic.
→ [`commentary-toc-ingest/SKILL.md`](commentary-toc-ingest/SKILL.md)

### `commentary-resegment` **[exists]**
Step 5 — meaning-based merge/split of blocks after the headings are in (mostly merging an explanation cut at a sentence end): the model flags operations per window, a script applies them, protects verse blocks, verifies integrity; QC pass. Gemini 3.8 Flash (high) by default, Claude on request.
→ [`commentary-resegment/SKILL.md`](commentary-resegment/SKILL.md)

### `commentary-block-ids` **[exists]**
Step 6 — derived body block IDs (`^N-n` by top-level section, frame from its own label), after the `##` labels are confirmed. Deterministic.
→ [`commentary-block-ids/SKILL.md`](commentary-block-ids/SKILL.md)

#### Shared

### `seg-toc-lib` **[exists]**
Support library, not run on its own: the scripts and TOC prompts both workflows share — root-text build library, tree ingest, chunking, the two tree checkers, the Gemini TOC pipeline, the strict text gate `verify_text.py`. Its `SKILL.md` holds the model rule (Gemini API by default, agents only when asked) and each step's text check.
→ [`seg-toc-lib/SKILL.md`](seg-toc-lib/SKILL.md)

---

## 5. Metadata and frontmatter

### `frontmatter`
Populates the complete YAML frontmatter for any source file — root text, commentary, translation or reference — extracting what can be extracted from the title, colophon and opening content. One variant per file type; the commentary variant also assigns `registered_id`, `root_text` and `covers_verses`.

*Replaces the four separate `root-text-frontmatter` / `commentary-frontmatter` / `translation-frontmatter` / `reference-frontmatter` skills, which were the same procedure four times.*
→ [`frontmatter/SKILL.md`](frontmatter/SKILL.md)

### `extract-source-metadata`
Pulls a text's own metadata — title, author, translator, publication details, scribe, patron, place, date — out of its first and last folios.
→ [`extract-source-metadata/SKILL.md`](extract-source-metadata/SKILL.md)

### `author-metadata-sync`
Propagates human-curated author metadata from the commentary frontmatter in `1-SOURCES/` out to the derived files that carry an author field, so one correction does not have to be made in a dozen places.
→ [`author-metadata-sync/SKILL.md`](author-metadata-sync/SKILL.md)

---

## 6. Section rails

### `section-summary`
Summarises one node of the structural outline: first once per commentary in that commentary's own language and terminology (`Sections/Raw/<commentary-id>/<node-id>.md`), then as one combined file with an English translation underneath (`Sections/<node-id>.md`).
**Never translate in the per-commentary phase** — its original-language terminology is the evidence the glossary and term skills read.
→ [`section-summary/SKILL.md`](section-summary/SKILL.md)

---

## 7. Verse rails

### `verse-context`
Builds the context package for a verse at `2-RAILS/Verses/<verse-id>.md`: transcludes the root verse and the relevant commentary passages, paraphrases how each commentator reads it, synthesises an overview, and produces the **disambiguated restatement** that every transformation skill works from. Modes for one verse, a chapter batch, a verse group's structural position, and regenerating the overview alone.
→ [`verse-context/SKILL.md`](verse-context/SKILL.md)

### `local-wiki-article`
Creates or updates the article for one key term in `2-RAILS/Local-Wiki/`, holding the commentary attestations and a contextual definition drawn from them.
→ [`local-wiki-article/SKILL.md`](local-wiki-article/SKILL.md)

---

## 8. Terminology and glossaries

### `interlinear-gloss`
For one root text plus one translation, builds a token-aligned gloss file under `2-RAILS/Bilingual-Glossaries/Raw/`. Token-level alignment happens here once, so every downstream glossary step reads from one place.
→ [`interlinear-gloss/SKILL.md`](interlinear-gloss/SKILL.md)

### `bilingual-glossary`
Builds and maintains the glossary chain end to end: extract every source keyword and its attested renderings from each gloss file, combine them per language pair, surface the contested ones, and select the per-track termbase.
→ [`bilingual-glossary/SKILL.md`](bilingual-glossary/SKILL.md)

### `keyword-extract`
Extracts ranked, domain-specific keywords, maps each occurrence back to its source-language term, and builds the **source-term registry** — one canonical lemma per concept with every variant grouped under it. This is the vocabulary-standardisation step every consistent termbase depends on.
→ [`keyword-extract/SKILL.md`](keyword-extract/SKILL.md)

### `term-definition`
Extracts verbatim definitions of key terms from the commentaries, using each source language's own definitional markers.
→ [`term-definition/SKILL.md`](term-definition/SKILL.md)

### `term-localization`
Fills the target-language columns of the term table, deriving each rendering from the commentary-sourced meaning rather than from a dictionary.
→ [`term-localization/SKILL.md`](term-localization/SKILL.md)

### `pali-biterm-extraction`
For a block-aligned Pāli source and an English translation, extracts every attested English rendering for each Pāli token's morphological family. Install it in Pāli vaults only.
→ [`pali-biterm-extraction/SKILL.md`](pali-biterm-extraction/SKILL.md)

---

## 9. Claims and article production

*Optional — for vaults that compare what many commentaries assert. See [`../../2-RAILS/About Rails.md`](../../2-RAILS/About%20Rails.md) §6b.*

### `commentary-claims`
Extracts every distinct claim one commentary makes into one claims file, in the commentary's own language, each cited to a block ID, from that commentary read in isolation.
→ [`commentary-claims/SKILL.md`](commentary-claims/SKILL.md)

### `claims-consolidate`
Consolidates one topic's claims across every commentary into a question-driven topic page: consensus, ⚑ divergences, unique claims. Includes the adversarial audit phase.
→ [`claims-consolidate/SKILL.md`](claims-consolidate/SKILL.md)

### `article-subject-filter` · `wiki-article-inventory` · `wiki-article-from-claims` · `gemini-article-polish`
The article pipeline: classify each queued term as a standalone subject, section material or glossary-only; check what already exists upstream; draft a cited article from one consolidated topic page; and re-compose its prose without changing a fact.
→ [`article-subject-filter/SKILL.md`](article-subject-filter/SKILL.md) · [`wiki-article-inventory/SKILL.md`](wiki-article-inventory/SKILL.md) · [`wiki-article-from-claims/SKILL.md`](wiki-article-from-claims/SKILL.md) · [`gemini-article-polish/SKILL.md`](gemini-article-polish/SKILL.md)

---

## 10. Transformations — translation

**Lock the vocabulary before translating anything that will be published.** A machine or zero-shot output is a first look, not a release candidate.

### `machine-translate`
Produces a machine baseline of a block-ID'd source by calling a translation API on small batches. A baseline, never a governed track.
→ [`machine-translate/SKILL.md`](machine-translate/SKILL.md)

### `zeroshot-translate`
Translates a block-ID'd source in one pass, with the degree of terminology control the job needs. Also produces the block-ID-preserving draft that `keyword-extract` consumes.
→ [`zeroshot-translate/SKILL.md`](zeroshot-translate/SKILL.md)

### `graded-translate`
The production path: builds the per-grade termbase, translates with it locked, then checks for drift.
→ [`graded-translate/SKILL.md`](graded-translate/SKILL.md)

### `verse-translate`
Metrical or rhymed verse translation, working from the verse packages rather than the raw root.
→ [`verse-translate/SKILL.md`](verse-translate/SKILL.md)

### `translate-commentary`
Translates a commentary into the target language against the track's requirements and termbase, preserving every block ID so the output stays aligned.
→ [`translate-commentary/SKILL.md`](translate-commentary/SKILL.md)

---

## 11. Transformations — adaptation and plans

### `multilevel-summary`
An audience-calibrated summary of a verse or chapter, grounded in the rails, with per-audience priorities and word budgets.
→ [`multilevel-summary/SKILL.md`](multilevel-summary/SKILL.md)

### `plan-scaffold`
Creates a plan's folder set from a session-shape declaration and a verse-distribution rule.
→ [`plan-scaffold/SKILL.md`](plan-scaffold/SKILL.md)

### `plan-schedule`
Builds, audits and adjusts the day-to-verse distribution table, renaming the affected day files when a verse moves.
→ [`plan-schedule/SKILL.md`](plan-schedule/SKILL.md)

### `plan-day-generate`
Authors one or more day files in the plan's authoring stream from the rails, section by section, with mechanical verification of every ceiling and formula.
→ [`plan-day-generate/SKILL.md`](plan-day-generate/SKILL.md)

### `plan-day-translate`
Produces another language stream's day file by translating the authoring stream's, with verses retrieved by block ID from that stream's designated translation track.
→ [`plan-day-translate/SKILL.md`](plan-day-translate/SKILL.md)

### `plan-day-package`
Builds the machine-anchored per-day dossier an app consumes, then validates and guards it.
→ [`plan-day-package/SKILL.md`](plan-day-package/SKILL.md)

---

## 12. QA and checking

### `translation-qa`
MQM-based quality check of a translation against the source, the rails and the track's requirements. Appends a dated run to the track's `qa-report.md`. A section is not `complete` until it passes with no critical or major errors.
→ [`translation-qa/SKILL.md`](translation-qa/SKILL.md)

### `commentary-fact-check`
Checks a translation verse by verse against the commentary tradition that grounds it, grading every departure.
→ [`commentary-fact-check/SKILL.md`](commentary-fact-check/SKILL.md)

### `translation-alignment-check`
Verifies that a translation is structurally parallel to the root: same block IDs in the same order, same segment types, headings and transclusions intact.
→ [`translation-alignment-check/SKILL.md`](translation-alignment-check/SKILL.md)

### `plan-day-qa`
Grades one plan day file against the plan's declared session shape, its grounding in the rails, and its stream's style contract, with a computed score and a hard gate.
→ [`plan-day-qa/SKILL.md`](plan-day-qa/SKILL.md)

---

## 13. Publishing

### `translation-upload`
Uploads a finished translation to the library backend: lint, parse, then create the text, edition, alignment and table of contents. Dry-run by default; `--execute` needs explicit human confirmation every time.
→ [`translation-upload/SKILL.md`](translation-upload/SKILL.md)

---

## 14. System and maintenance

### `create-skill`
Scaffolds a new skill completely: the `SKILL.md`, the catalog entry, the slash-command file, and the `CLAUDE.md` §12 row if it will be used often. All four must stay in sync.
→ [`create-skill/SKILL.md`](create-skill/SKILL.md)

### `vault-audit`
Read-only weekly audit in eight checks: skill registration and frontmatter, rail and output frontmatter completeness, citation-chain integrity, status consistency, stale inbox files, dead wiki links, file placement, and unfilled template placeholders. Produces a dated report in `0-INBOX/`; it never fixes anything.
→ [`vault-audit/SKILL.md`](vault-audit/SKILL.md)

### `property-creator`
Adds standard properties to a file by extracting details from its title and colophon. Largely superseded by the frontmatter skills and `extract-source-metadata`.
→ [`property-creator/SKILL.md`](property-creator/SKILL.md)

---

## Retired skills

These skills existed here before the shared library merged each family into one.
The name is kept in this table so that a reader who looks for it is told where
the job went, rather than concluding it was dropped.

| Retired | Now done by |
|---|---|
| `commentary-frontmatter` | `frontmatter` |
| `glossary-combine` | `bilingual-glossary` |
| `glossary-extract-raw` | `bilingual-glossary` |
| `glossary-select` | `bilingual-glossary` |
| `reference-frontmatter` | `frontmatter` |
| `root-text-frontmatter` | `frontmatter` |
| `section-summary-combined` | `section-summary` |
| `section-summary-raw` | `section-summary` |
| `source-property-extractor` | `extract-source-metadata` |
| `translation-frontmatter` | `frontmatter` |

---

## Adding a skill

Four places must change together, or the skill is invisible to somebody: the skill folder, this catalog, the slash-command stub, and — if it will be used often — the quick-reference table in [`../CLAUDE.md`](../CLAUDE.md) §12. The `create-skill` skill does all four. `vault-audit` check 1 catches it when they drift apart.
