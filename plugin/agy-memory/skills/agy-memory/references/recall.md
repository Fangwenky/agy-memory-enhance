# Recall and long-term traceability

Everything is kept locally in `.agy-memory/`. Use the cheapest tool that answers the question.

| Question | Command |
| :-- | :-- |
| What should I know right now? | `mem brief` |
| What sessions worked on this project? | `mem session`, then `mem session <conv>` for one session's index (first request, files edited, entries) |
| What did the user say about X? | `mem search X --type user_input --where events` |
| Why was this decided? | `mem search X --where ledger`, then `mem show <id>` for the full version history |
| Why does `path/to/file` look like this? | `mem timeline --file path/to/file`. It lists edits, commands and related ledger entries in order. Then use `mem show <conv>#<step>` on the interesting steps. |
| What did the native compaction summary say back then? | `mem search <word> --type compaction --where events` |
| Exact original tool output or message | `mem show <conv>#<step>`. It reads the live transcript, or the archive if the transcript is gone. |
| Anything in old conversations | `mem search <words> --where archive --since 30d` |

Tips:
- Search terms are ANDed and case-insensitive. Use distinctive words, such as identifiers, file names or error strings.
- Hits list a pointer (`<conv>#<step>`). Pass it to `mem show` for the full text, and use it as `--source` when recording a fact.
- Archived transcripts can be large. Narrow the search with `--since` and with specific terms.
- If you are resuming someone else's or an older session's work, read that session's index first. Then copy its relevant open `progress` items into your own session with `mem add progress ...`.
