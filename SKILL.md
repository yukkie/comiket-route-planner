---
name: comiket-route-planner
description: Build and update a Comiket circle visit, purchase, cash-budget, and route plan from a previous event list, an X/Twitter following or post export, catalog or menu images, and an official venue-map PDF. Use when Codex or Claude Code needs to identify likely participating circles, preserve user-assigned priorities and genres, extract circle names/items/prices, classify wall or island placement, calculate minimum and maximum spending, export an event-day view, or merge refreshed source data without overwriting purchase status and other manual edits.
---

# Comiket Route Planner

## Goal

Create a traceable event-day plan that answers four questions: where to go, in what priority order, what to buy, and how much cash to bring. Keep uncertain AI extraction separate from confirmed user decisions.

## Read the references

- Read [references/project-overview.md](references/project-overview.md) before scoping or handing off the project.
- Read [references/design.md](references/design.md) before implementing scripts, schemas, merge logic, or exports.
- Treat both files as the current draft specification. Record unresolved product decisions instead of silently inventing permanent behavior.

## Run the local MVP

Use `uv` with Python 3.10 or later. Run it from this skill folder; `uv` installs the locked runtime dependencies, creates the environment, and exposes the `comiket-plan` command:

```powershell
uv sync
uv run comiket-plan init C110-day2 --name "Comic Market 110" --day 2 --output data/events/C110-day2.json
uv run comiket-plan import-previous data/events/C110-day2.json previous.csv
uv run comiket-plan build-next C109 --follow follow-a.json --follow follow-b.json --previous previous.json --profile-pattern C108 --include-previous-only --carry-previous-placement --hall-index references/c108-hall-index.json --output data/derived/C109.json --report data/derived/C109-report.json
uv run comiket-plan validate data/events/C110-day2.json --report data/derived/review.json
uv run comiket-plan export data/events/C110-day2.json --format html --output data/derived/C110-day2.html
```

Run the standard-library test suite with `uv run python -m unittest discover -s tests -v`.

Open the exported HTML directly in a browser, or serve it locally when the browser blocks `file:` URLs:

```powershell
uv run python -m http.server 8000 --directory data/derived
```

Then open `http://127.0.0.1:8000/C110-day2.html`. Stop the server with `Ctrl+C`.

Accept a previous-list `.csv` or `.json`. Canonical English headers and the Japanese headers `サークル名 / 作家名 / 配置 / 優先度 / 一言ジャンル / 訪問状態 / 購入予定 / 価格 / 購入状態 / メモ` are supported. Use `reconcile PLAN INCOMING` to merge another normalized EventPlan. Export `json`, `csv`, or an offline mobile HTML view; the HTML stores visit-status taps locally in the browser.

Use `build-next` for the current MVP input flow. Repeat `--follow` for exports from separate X accounts. Merge profile exports by case-insensitive X handle and preserve every source filename. Preserve separate visit rows when the same account has different event days or spaces. `--profile-pattern` filters the display name plus bio, removes the event-announcement suffix from the creator-name candidate, and conservatively extracts event day, hall, and space. For a virtual C109 rehearsal, use `C108`. `--include-previous-only` forms a union with the previous route list. Normally carry forward only `priority` and `genre_short`; reset placement, visit state, and purchase state. Use `--carry-previous-placement` only for an explicit rehearsal that treats the previous event as the next event. Pass the matching event-specific map index with `--hall-index`; resolve exact halls from map evidence and retain `東（番号不明）` only when the index cannot decide. A follow-profile display name is a creator-name candidate, not a confirmed circle name. Match a handleless previous row by creator name only when there is exactly one exact-name candidate; never fuzzy-match names.

For Notion table views, use a select property for hall, keep visit status as the first operational column, and do not add a redundant purchased checkbox when visit status already represents purchased/sold-out/skipped state. Keep source/provenance fields to the right of event-day operational fields.

Treat menu-image extraction, creating a new event's index from official-PDF geometry, and direct X acquisition as assisted input preparation for now: inspect user-provided sources with the available document/image tools and record evidence. Applying an existing event-specific hall index during `build-next` is deterministic and implemented; do not claim PDF-to-index generation itself is automated yet.

## Workflow

1. Identify the event edition, day, source files, desired output, and whether this is a new event or a refresh of the same event.
2. Inspect the previous list first. Preserve user-authored priority, one-line genre, notes, item choices, and status as authoritative fields.
3. Import X/Twitter data only from sources the user can lawfully access. Find participation and menu posts; prefer an explicit menu image over inference from general posts.
4. Parse the official venue-map PDF once per event into a reusable placement index. Until a deterministic map adapter is available, inspect the user-provided PDF once, preserve page/region evidence in normalized JSON, and resolve each space code from that index.
5. Extract circle name, space, items, prices, age rating, and evidence from relevant posts or menu images. Mark missing or ambiguous values as unknown; never fabricate them.
6. Reconcile records using stable source identifiers and aliases. Present low-confidence matches and conflicts for review.
7. Calculate `planned_total` from items marked `buy` and `max_total` from items marked `buy` or `candidate`. Do not count unknown prices as zero; report them separately.
8. Produce a mobile-friendly event-day view with priority, placement, circle/creator name, one-line genre, chosen items, subtotal, and visit status.
9. Validate totals, duplicate records, unresolved placements, unknown prices, and preservation of manual fields before export.

## Non-negotiable merge rules

- On a new event, initialize visit and purchase progress to the configured default.
- On a refresh of the same event, never reset manual priority, genre, item selection, notes, or visit status unless the user explicitly requests it.
- Let explicit user edits outrank previous-list values; let previous-list values outrank AI inference.
- Store source provenance and confidence beside inferred values.
- Keep extracted facts and user decisions as separate fields.
- Never raise or lower priority solely from follower count or presumed popularity.

## Content handling

Public adult-oriented posts may be classified only as needed for planning. Reduce them to neutral metadata such as `成人向けオリジナル`, `百合`, or `全年齢`; do not preserve or reproduce unnecessary explicit text or imagery. Respect platform access controls, API terms, local law, and the user's authorization. If a source cannot be accessed, accept a user-provided export or file instead of bypassing controls.

## Expected outputs

At minimum, emit:

- a normalized machine-readable event plan;
- a human-review report listing conflicts and unknowns;
- a mobile-friendly event-day view;
- cash totals for confirmed purchases and candidate-inclusive maximums.

When implementation scripts exist, prefer running them over recreating transformation logic ad hoc. Keep script interfaces and acceptance criteria aligned with [references/design.md](references/design.md).

## Completion checks

Confirm all of the following:

- Manual fields survived a same-event refresh.
- Each inferred placement, circle name, item, and price has evidence or is marked unknown.
- `planned_total` and `max_total` reconcile with item-level states.
- Bundles and individual items are not double-counted.
- Unknown-price selections are clearly visible.
- The event-day view supports `未訪問`, `購入済`, `売切れ`, and `見送り`.
