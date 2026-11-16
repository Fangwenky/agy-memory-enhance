# Writing to the ledger

The ledger is what survives compaction. Keep it **small, true and specific**. The brief has a token cap, so noise pushes out signal.

## What to record

| Type | Record when | Good | Bad |
| :-- | :-- | :-- | :-- |
| `constraint` | The user, or the project's docs, state a rule, restriction or preference | `never edit generated files under api/gen/` | `be careful` |
| `decision` | You or the user choose between options. Include the reason. | `pagination via cursor, not offset: tables > 10M rows` | `decided on pagination` |
| `progress` | A milestone is finished, or the plan changes | `parser rewritten + tests green; next: wire into CLI` | `working on stuff` |
| `fact` | An exact identifier is needed later. Always add `--source`. | `prod DB env var is PG_URL_PRIMARY` with `--source file:deploy/env.md` | facts you can trivially re-read |
| `open` | A question is unresolved, or is waiting on the user | `does a member who joins mid-round get a vote?` | |

Rules:
- **One fact per entry.** Write it as a full sentence that can be understood without context.
- **Quote the user's own words** for constraints when wording matters.
- **Sources**: use `--source <conv>#<step>` for something seen in this conversation. The step index appears in transcript pointers and in `mem search` hits. Use `--source file:<path>` for something read from a file.
- **Don't duplicate.** Run `mem show <type>` first, and `mem supersede` to refine an existing entry.
- **Close the loop.** Use `mem done <id>` for completed progress or answered questions, and `mem drop <id>` for anything no longer true.

## When to write

- **Right away:** whenever the user states a constraint or makes a decision.
- **At milestones:** one `progress` entry, and mark the previous one done.
- **On a context-pressure nudge:** save anything important that is not in the ledger yet. Usually this means 1–4 entries, so do not dump everything.
- **At the end of a turn, when asked by the Stop nudge:** record new decisions or progress, or skip if nothing is worth keeping.

Writing costs one short command. Missing an entry can cost hours after compaction.
