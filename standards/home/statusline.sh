#!/bin/bash
# dotai — Claude Code status line
# 2-line display: [model] folder branch | context bar + cost + duration
# Installed by dotai. Re-run install.py to update.

input=$(cat)

# Force C locale for numeric formatting (decimal point, not comma)
export LC_NUMERIC=C

# --- Extract fields ---
MODEL=$(echo "$input" | jq -r '.model.display_name // "?"')
DIR=$(echo "$input" | jq -r '.workspace.current_dir // "?"')
COST=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
DURATION_MS=$(echo "$input" | jq -r '.cost.total_duration_ms // 0')

# --- Colors ---
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

# --- Line 1: [model] + folder + git branch ---
FOLDER="${DIR##*/}"

BRANCH=""
if git rev-parse --git-dir > /dev/null 2>&1; then
    BRANCH_NAME=$(git branch --show-current 2>/dev/null)
    if [ -n "$BRANCH_NAME" ]; then
        # Pick icon based on branch naming convention
        case "$BRANCH_NAME" in
            feature/*|feat/*) BRANCH_ICON="✨" ;;
            bugfix/*|fix/*)   BRANCH_ICON="🐛" ;;
            hotfix/*)         BRANCH_ICON="🔥" ;;
            release/*)        BRANCH_ICON="📦" ;;
            chore/*)          BRANCH_ICON="🔧" ;;
            main|master)      BRANCH_ICON="🏠" ;;
            develop|dev)      BRANCH_ICON="🔀" ;;
            *)                BRANCH_ICON="🌿" ;;
        esac

        STAGED=$(git diff --cached --numstat 2>/dev/null | wc -l | tr -d ' ')
        MODIFIED=$(git diff --numstat 2>/dev/null | wc -l | tr -d ' ')
        GIT_INDICATORS=""
        [ "$STAGED" -gt 0 ] && GIT_INDICATORS="${GREEN}+${STAGED}${RESET}"
        [ "$MODIFIED" -gt 0 ] && GIT_INDICATORS="${GIT_INDICATORS}${YELLOW}~${MODIFIED}${RESET}"
        [ -n "$GIT_INDICATORS" ] && GIT_INDICATORS=" $GIT_INDICATORS"
        BRANCH=" ${DIM}|${RESET} ${BRANCH_ICON} ${CYAN}${BRANCH_NAME}${RESET}${GIT_INDICATORS}"
    fi
fi

printf '%b%s%b%s%b\n' "${DIM}[${RESET}${BOLD}${CYAN}" "${MODEL}" "${RESET}${DIM}]${RESET} 📂 ${DIM}" "${FOLDER}" "${RESET}${BRANCH}"

# --- Line 2: context bar + cost + duration ---
# Color the bar by usage threshold
if [ "$PCT" -ge 90 ]; then BAR_COLOR="$RED"
elif [ "$PCT" -ge 70 ]; then BAR_COLOR="$YELLOW"
else BAR_COLOR="$GREEN"; fi

# Build 20-char progress bar
BAR_WIDTH=20
FILLED=$((PCT * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))
BAR=""
[ "$FILLED" -gt 0 ] && BAR=$(printf "%${FILLED}s" | tr ' ' '▓')
[ "$EMPTY" -gt 0 ] && BAR="${BAR}$(printf "%${EMPTY}s" | tr ' ' '░')"

# Format cost
COST_FMT=$(printf '$%.2f' "$COST")

# Format duration as Xm Ys
TOTAL_SECS=$((DURATION_MS / 1000))
MINS=$((TOTAL_SECS / 60))
SECS=$((TOTAL_SECS % 60))

printf '%b\n' "🧠 ${BAR_COLOR}${BAR}${RESET} ${PCT}% ${DIM}|${RESET} 💰 ${YELLOW}${COST_FMT}${RESET} ${DIM}|${RESET} ⏱️  ${DIM}${MINS}m ${SECS}s${RESET}"
