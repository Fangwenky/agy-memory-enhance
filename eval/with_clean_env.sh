#!/bin/sh
# Temporarily hide global memory skills (obelisk) while running eval, and
# always restore them on exit (normal exit, error, INT, TERM).
set -eu

BK="$HOME/.gemini/.eval-disabled-skills"
mkdir -p "$BK"

restore() {
  if [ -L "$BK/skills-obelisk" ] || [ -e "$BK/skills-obelisk" ]; then
    mv "$BK/skills-obelisk" "$HOME/.gemini/skills/obelisk" 2>/dev/null || true
  fi
  if [ -L "$BK/config-skills-obelisk" ] || [ -e "$BK/config-skills-obelisk" ]; then
    mv "$BK/config-skills-obelisk" "$HOME/.gemini/config/skills/obelisk" 2>/dev/null || true
  fi
}
trap restore EXIT INT TERM

if [ -L "$HOME/.gemini/skills/obelisk" ] || [ -e "$HOME/.gemini/skills/obelisk" ]; then
  mv "$HOME/.gemini/skills/obelisk" "$BK/skills-obelisk"
fi
if [ -L "$HOME/.gemini/config/skills/obelisk" ] || [ -e "$HOME/.gemini/config/skills/obelisk" ]; then
  mv "$HOME/.gemini/config/skills/obelisk" "$BK/config-skills-obelisk"
fi

"$@"
