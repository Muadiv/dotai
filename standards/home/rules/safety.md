# Safety Rules

## File Deletion Policy

NEVER delete any file without explicit user approval.

Before deleting ANY file:
1. STOP and clearly warn the user
2. LIST exactly which files will be deleted
3. EXPLAIN why the deletion is necessary
4. WAIT for explicit confirmation

No exceptions — not for temp files, cache files, duplicates, or "obviously wrong" files.

## Git Configuration Protection

NEVER modify git configuration (`.gitconfig`, `.gitconfig.local`, git credential settings, or any `git config` command).

Modifying git config can break authentication, commit signing, and remote access.

Before any git operation:
1. NEVER run `git config` to set or unset any value
2. NEVER modify `.gitconfig`, `.gitconfig.local`, or `.git/config` files
3. If a git operation fails due to auth or config issues, **report the error** — do not attempt to fix the config

## General Safety

- Always show file paths before modifying them
- Confirm destructive git operations (reset --hard, force push, rebase, branch -D)
- Warn about operations that can't be easily undone
- Preserve user data at all costs
- When in doubt, ask
