# Lucid's original power system

This is Lucid's own system. Dragon Ball-style ki and Naruto-style chakra informed the earlier reference charts; those franchises do not dictate this universe's rules.

## Rules carried forward

- Lucid combines ki and chakra. Combat and training can strengthen him and his jutsu together.
- Ki supports his physical power, aura, energy attacks and limit breaking. Chakra supports techniques and elemental expression.
- Explosive transformations can open all registered power types temporarily. Access is separate from control and mastery.
- A permanent breakthrough must be recorded explicitly. Transformation access alone does not permanently awaken or master anything.
- His sage pact and Super Sage remain undecided; an all-types transformation does not silently grant sage mastery.
- Lucid has not yet reached god-tier power. No Ancient's own power imprint or new lineage is implied by this tracker.

## Editable registry

`progression/rules.json` holds growth tracks, type names, starting permanent unlocks and the all-types transformation registry. Tracks include ki, chakra, control, body, spirit, ninja and ascension. Body Gifts or additional subclasses can be added once their specific rules are defined.

The initial type registry covers fire, wind, lightning, earth, water, ice, wood, lava, boil, storm, scorch, magnet, explosion, dust, yin, yang and yin-yang. These are reference names, not a restriction on future original types. The earlier reference combinations can inspire techniques, but this implementation does not impose anime bloodline restrictions or grant every possible technique automatically.

Starting elemental affinities are unspecified. Initial XP is zero **newly recorded growth**, not zero pre-existing strength. No level ceiling, arbitrary level-up thresholds, or quantified baseline is invented.

## Event contract

`progression/events.json` is the source of truth, replayed in file order (story order). The timestamp records when the event was logged or occurred; it is not used to rearrange flashbacks. Use `story_ref` for narrative chronology. Keep IDs stable and unique.

Every event requires `id`, `kind`, an ISO `occurred_at` timestamp with timezone, and `summary`. Allowed kinds: `mission`, `training`, `fight`, `breakthrough`, `discovery`, `recovery`, `transformation_start`, `transformation_end`.

Optional event fields:

| Field | Effect |
| --- | --- |
| `gains` | Adds explicit nonnegative integer XP to registered growth tracks. |
| `type_gains` | Adds explicit XP to types currently available through a permanent unlock or active transformation. |
| `unlocks` | Permanently awakens listed types. |
| `mastered` | Marks explicitly mastered types; requires a permanent unlock, which may happen in this same event. |
| `story_ref` | Links the change to a mission, episode or scene. |
| `form` | Transformation name; only valid for `transformation_start`. |
| `all_types` | Boolean; `true` gives temporary access to the configured transformation registry. |
| `types` | Explicit temporary access list instead of `all_types`. |

Transformation example, not an established story event:

```json
{
  "id": "example-eruption-start",
  "kind": "transformation_start",
  "occurred_at": "2026-10-10T22:40:00-04:00",
  "summary": "Describe the actual transformation scene.",
  "form": "Name the form when established",
  "all_types": true
}
```

Use a later `transformation_end` event with its own ID, timestamp and summary to close the active form. Temporary access disappears; earned XP and explicit permanent unlocks persist. If a type had temporary training but no permanent awakening, the graph calls it dormant. Nested forms and an end without a start are rejected.

## Automatic updates and history

Recording locally regenerates `state.json`, `graph.svg`, and the progression history immediately. A GitHub Actions workflow does the same for ledger/rules changes on `main`, or for manually submitted event JSON. Inputs are passed as environment data, never evaluated as shell code. Repeat submission of the identical event is idempotent; a conflicting duplicate ID is rejected.

All inputs validate before any tracked files change. GitHub records every ledger revision. To correct an earlier event, edit that event deliberately and rebuild; Git history retains the previous version. Do not edit generated state or graph files directly. Changing registry/rules replays the full ledger, so removing a referenced type fails validation until explicitly reconciled.

This is a repository-based tracker, not a connection to an existing game engine. A future engine or story tool can emit this same event contract and call `build(root, event)` or the CLI. Until then, events must be recorded here (directly or by the assistant when asked).
