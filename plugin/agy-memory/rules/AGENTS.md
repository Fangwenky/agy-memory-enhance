# agy-memory protocol

This workspace has an independent memory ledger that survives context compaction and sessions. The CLI path is given in `[agy-memory]` system messages. It is usually `<workspace>/.agy-memory/bin/mem`.

- **Record as you go** with `mem add <type> "<one fact>"`. Types are `constraint`, `decision`, `progress`, `fact`, and `open`. Record a constraint when the user states a rule or restriction. Record a decision once one is made, with the reason. Record progress when you finish a milestone. Record a fact for an exact identifier, and add `--source <conv>#<step>` or `--source file:<path>`.
- **On an `[agy-memory]` "compaction detected" message**, or on any "Resuming from a compaction" summary, load the `agy-memory` skill and run its alignment procedure before your next edit.
- **On a context-pressure message**, save what is not yet in the ledger, then continue.
- **Exact paths, IDs, names and numbers** come from the source, meaning a file, a tool output or `mem show <conv>#<step>`. Never take them from a summary.
- **When memory conflicts with what you observe now**, trust the observation. Then fix the ledger with `mem supersede <id> "..."`.
