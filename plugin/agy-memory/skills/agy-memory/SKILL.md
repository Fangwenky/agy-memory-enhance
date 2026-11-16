---
name: agy-memory
description: >-
  Compaction-proof project memory for Antigravity. Use when an [agy-memory]
  system message reports context compaction or context pressure, when a
  "Resuming from a compaction" summary appears, when resuming a long task in a
  new session, or when you need to look up past decisions, constraints, user
  instructions, or why a file changed (long-term traceability).
---

# agy-memory

agy-memory keeps an append-only memory store in `<workspace>/.agy-memory/`. It sits outside the model context, so compaction cannot erase it.

- **Hooks record automatically:**
  - user messages, verbatim;
  - file edits and commands;
  - every compaction, including agy's own summary text;
  - a per-session index;
  - an archive of the transcript.
- **You curate the ledger:** short entries of type `constraint`, `decision`, `progress`, `fact` and `open`.
  - `constraint`, `decision` and `fact` are project-wide.
  - `progress` and `open` belong to the current session.

Run everything through the CLI. Its path is in the `[agy-memory]` system message, usually `<workspace>/.agy-memory/bin/mem`. Below, `mem` means that path.

## Which procedure

| Situation | Read |
| :-- | :-- |
| Compaction detected, or "Resuming from a compaction" | **Alignment**, below. Always do it before the next edit. |
| Context-pressure nudge, a milestone, or a new user rule | [references/write.md](references/write.md) |
| "Why did we…", "what did the user say about…", resuming old work | [references/recall.md](references/recall.md) |

## Alignment procedure (after compaction)

The native summary paraphrases. Its resume rules say not to re-verify it. Your job is to catch what it dropped or bent, and to do so cheaply.

1. **Load memory.** Run `mem brief`. It is already included in the alignment message, so skip this step if you can see it.
2. **Check constraints.** Compare each active constraint against the summary's "Commitments & Constraints" and your plan.
   - If a constraint is missing from the summary, it still applies.
   - If the summary states a rule that is not in the ledger, add it with `mem add constraint` and cite its source.
3. **Check user instructions given mid-task.** Run `mem search --type user_input --where events <keyword>`, or `mem timeline --conv-only --limit 30`. Look for corrections or restrictions the user gave after the first request. Summaries often flatten these.
4. **Re-ground exact facts before using them.** List the identifiers your next step needs: paths, symbols, keys, numbers, command flags. Do not use them from memory or from the summary. Get each one from its source:
   - `mem show fact` lists known facts with source pointers;
   - `mem show <conv>#<step>` prints an original transcript step;
   - otherwise, read the file itself, only the lines you need.
5. **Reconcile.** If memory and the present state disagree, trust what you observe now. Then run `mem supersede <id> "corrected text"`.
6. **Mark alignment done.** Run `mem add progress "aligned after compaction #N: <one line on where things stand>"`.
7. **Continue the task.** Keep alignment to a few tool calls. Do not re-read the whole project.

## Quick reference

```sh
mem brief                                  # constraints, decisions, this session's progress, facts
mem add constraint "do not modify src/legacy/"
mem add decision "use SQLite, not Postgres: zero-dependency requirement"
mem add fact "config key is memory.softLimitRatio" --source file:lib/config.py
mem add progress "M2 done; next: e2e test"
mem done <id>            mem supersede <id> "new text"            mem drop <id>
mem show constraint|decision|progress|fact|open|all|<id>|<conv>#<step>
mem search <words...> [--where ledger|events|archive] [--type user_input] [--since 3d]
mem timeline [--file path] [--conv-only] [--since 2026-11-01]
mem session [<conv>]     mem doctor
```
