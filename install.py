#!/usr/bin/env python3
"""
dotai — TUI + CLI Installer

Full-screen terminal application and non-interactive CLI for installing
standardized Claude Code configuration. No arguments launches the TUI.
Any flags run non-interactively for scripting and CI use.

Requirements: Python 3.8+, textual (pip install textual) for TUI mode
Platforms: macOS, Linux, Windows
"""

import json
import re
import sys
import shutil
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check (deferred — only needed for TUI mode)
# ---------------------------------------------------------------------------

try:
    from textual.app import App, ComposeResult
    from textual.screen import Screen
    from textual.widgets import (
        Static, Button, SelectionList,
        RadioSet, RadioButton, Checkbox,
        Rule, Footer, Header,
    )
    from textual.containers import Container, Horizontal, VerticalScroll
    from textual.binding import Binding
    from textual.widgets.selection_list import Selection
    from textual import on
    from rich.text import Text
    _TEXTUAL_AVAILABLE = True
except ImportError:
    _TEXTUAL_AVAILABLE = False
    # Stubs so TUI class definitions don't crash at import time.
    # These classes are never instantiated — CLI mode doesn't use them.
    class _StubMeta(type):
        def __getattr__(cls, name): return cls
    class _Stub(metaclass=_StubMeta):
        pass
    App = Screen = _Stub
    ComposeResult = None
    def Binding(*a, **kw): return None
    def Selection(*a, **kw): return None
    Static = Button = SelectionList = RadioSet = RadioButton = Checkbox = _Stub
    Rule = Footer = Header = _Stub
    Container = Horizontal = VerticalScroll = _Stub
    def on(*a, **kw):
        return lambda f: f
    class Text:
        def __init__(self, *a, **kw): pass
        def append(self, *a, **kw): pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
HOME_DIR = SCRIPT_DIR / "standards" / "home"
HOME_CLAUDE_MD = HOME_DIR / "CLAUDE.md"
HOME_RULES_DIR = HOME_DIR / "rules"
AGENTS_DIR = SCRIPT_DIR / "standards" / "agents"
TASKS_DIR = SCRIPT_DIR / "standards" / "tasks"

CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_MD = CLAUDE_HOME / "CLAUDE.md"
CLAUDE_RULES = CLAUDE_HOME / "rules"
CLAUDE_AGENTS = CLAUDE_HOME / "agents"
BACKUPS_DIR = CLAUDE_HOME / "backups"

MANDATORY_RULES = {"security.md"}
MANDATORY_AGENTS = {"security-auditor.md", "compliance-reviewer.md"}

HOME_SETTINGS_JSON = HOME_DIR / "settings.json"
HOME_STATUSLINE = HOME_DIR / "statusline.sh"
CLAUDE_SETTINGS = CLAUDE_HOME / "settings.json"
CLAUDE_STATUSLINE = CLAUDE_HOME / "statusline.sh"

MODEL_CHOICES = {
    "sonnet": "us.anthropic.claude-sonnet-4-6",
    "opus": "us.anthropic.claude-opus-4-6-v1",
    "haiku": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "none": None,
}

AUTO_READ_PERMISSIONS = {
    "permissions": {
        "allow": [
            "Read",
            "Glob",
            "Grep",
            "Bash(ls:*)",
            "Bash(git diff:*)",
            "Bash(git log:*)",
            "Bash(git status:*)",
        ]
    }
}

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def discover_files(directory: Path) -> list:
    if not directory.exists():
        return []
    return sorted(
        [(f.name, f) for f in directory.iterdir()
         if f.suffix == ".md" and f.is_file() and not f.is_symlink()],
        key=lambda x: x[0],
    )


def is_git_repo(path: Path) -> bool:
    current = path.resolve()
    while True:
        if (current / ".git").exists():
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def get_repo_name(path: Path) -> str:
    current = path.resolve()
    while True:
        if (current / ".git").exists():
            return current.name
        parent = current.parent
        if parent == current:
            return path.name
        current = parent


def file_has_content(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8").strip()
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    return len(lines) > 0


def get_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def get_frontmatter_field(path: Path, field: str) -> str:
    """Extract a field from YAML frontmatter (between --- delimiters)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith(f"{field}:"):
            return line.split(":", 1)[1].strip()
    return ""


def get_description(path: Path) -> str:
    return get_frontmatter_field(path, "description")


def get_model(path: Path) -> str:
    return get_frontmatter_field(path, "model")


def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.parent / f"{path.name}.bak.{ts}"
    shutil.copy2(path, backup)
    return backup


def create_snapshot():
    """Snapshot managed files under ~/.claude/ before installing.

    Only snapshots files we manage: CLAUDE.md, rules/, agents/, tasks/.
    Returns the snapshot directory, or None if nothing to snapshot.
    """
    if not CLAUDE_HOME.exists():
        return None

    # Collect only files we manage
    files_to_snap = []
    claude_md = CLAUDE_HOME / "CLAUDE.md"
    if claude_md.exists():
        files_to_snap.append(claude_md)
    settings_json = CLAUDE_HOME / "settings.json"
    if settings_json.exists():
        files_to_snap.append(settings_json)
    statusline_sh = CLAUDE_HOME / "statusline.sh"
    if statusline_sh.exists():
        files_to_snap.append(statusline_sh)
    for subdir in ("rules", "agents", "tasks"):
        d = CLAUDE_HOME / subdir
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and not f.is_symlink():
                    files_to_snap.append(f)

    if not files_to_snap:
        return None

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap_dir = BACKUPS_DIR / ts
    snap_dir.mkdir(parents=True, exist_ok=True)

    for f in files_to_snap:
        rel = f.relative_to(CLAUDE_HOME)
        dest = snap_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)

    return snap_dir


def discover_snapshots() -> list:
    """Return list of (timestamp_str, path) for existing snapshots, newest first."""
    if not BACKUPS_DIR.exists():
        return []
    snaps = []
    for d in BACKUPS_DIR.iterdir():
        if d.is_dir() and re.match(r'^\d{8}-\d{6}$', d.name):
            snaps.append((d.name, d))
    return sorted(snaps, key=lambda x: x[0], reverse=True)


def restore_snapshot(snap_dir: Path) -> list:
    """Restore files from a snapshot directory back to ~/.claude/.

    Returns log entries.
    """
    log = []
    resolved_home = CLAUDE_HOME.resolve()
    for item in snap_dir.rglob("*"):
        if not item.is_file() or item.is_symlink():
            continue
        rel = item.relative_to(snap_dir)
        dest = CLAUDE_HOME / rel
        # Verify destination stays under ~/.claude/
        try:
            dest.resolve().relative_to(resolved_home)
        except ValueError:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if dest.read_bytes() == item.read_bytes():
                log.append(("current", f"~/.claude/{rel}"))
                continue
            backup_file(dest)
        shutil.copy2(item, dest)
        log.append(("restored", f"~/.claude/{rel}"))
    return log


# ---------------------------------------------------------------------------
# Status detection — compare source vs installed
# ---------------------------------------------------------------------------

def file_status(src: Path, dest: Path) -> str:
    """Compare source file with installed file.

    Returns: 'new', 'installed', or 'update'
      - new:       source exists, not installed yet
      - installed: installed and matches source (up to date)
      - update:    installed but differs from source (update available)
    """
    if not dest.exists():
        return "new"
    src_bytes = src.read_bytes()
    dest_bytes = dest.read_bytes()
    return "installed" if src_bytes == dest_bytes else "update"


def is_fresh_install() -> bool:
    """True if no global CLAUDE.md exists yet (first-time install)."""
    return not CLAUDE_MD.exists()


def build_file_info(source_files: list, install_dir: Path, mandatory: set) -> list:
    """Build a list of dicts with name, source, status, mandatory for each file.

    Returns list of:
      {name, src, heading, status, mandatory, description, model}
    """
    items = []
    for name, src in source_files:
        dest = install_dir / name
        status = file_status(src, dest)
        items.append({
            "name": name,
            "src": src,
            "status": status,
            "mandatory": name in mandatory,
            "heading": get_heading(src),
            "description": get_description(src),
            "model": get_model(src),
        })
    return items


STATUS_BADGE = {
    "new":       "NEW",
    "installed": "UP TO DATE",
    "update":    "UPDATE",
}

STATUS_STYLE = {
    "new":       "cyan bold",
    "installed": "green",
    "update":    "yellow bold",
}


def make_selection_label(item: dict, show_model: bool = False):
    """Build a Rich Text label with status badge for a SelectionList item."""
    label = Text()
    label.append(f"{item['heading']} ", style="bold")
    label.append(f"({item['name']})", style="dim")
    if show_model and item.get("model"):
        label.append(f" [{item['model']}]", style="dim yellow")
    if item["mandatory"]:
        label.append(" MANDATORY", style="red bold")
    badge = STATUS_BADGE[item["status"]]
    style = STATUS_STYLE[item["status"]]
    label.append(f"  {badge}", style=style)
    return label


# ---------------------------------------------------------------------------
# Smart install — install, update, remove, skip
# ---------------------------------------------------------------------------

def smart_install(src: Path, dest: Path, label: str, log: list) -> None:
    """Install or update a file, skipping if already up to date."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(src, dest)
        log.append(("installed", label))
    elif src.read_bytes() != dest.read_bytes():
        bak = backup_file(dest)
        shutil.copy2(src, dest)
        log.append(("updated", f"{label} (backed up -> {bak.name})"))
    else:
        log.append(("current", label))


def remove_with_log(dest: Path, label: str, log: list) -> None:
    """Remove an installed file, backing up first."""
    if dest.exists():
        bak = backup_file(dest)
        dest.unlink()
        log.append(("removed", f"{label} (backed up -> {bak.name})"))


def install_auto_read(cwd: Path, log: list) -> None:
    """Create .claude/settings.json with auto-approve read permissions."""
    settings_dir = cwd / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"

    if settings_file.exists():
        # Merge into existing settings
        try:
            existing = json.loads(settings_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        perms = existing.setdefault("permissions", {})
        allow = perms.setdefault("allow", [])
        added = []
        for tool in AUTO_READ_PERMISSIONS["permissions"]["allow"]:
            if tool not in allow:
                allow.append(tool)
                added.append(tool)
        if added:
            settings_file.write_text(
                json.dumps(existing, indent=2) + "\n", encoding="utf-8"
            )
            log.append(("installed", f".claude/settings.json (added {len(added)} permissions)"))
        else:
            log.append(("current", ".claude/settings.json (permissions already present)"))
    else:
        settings_file.write_text(
            json.dumps(AUTO_READ_PERMISSIONS, indent=2) + "\n", encoding="utf-8"
        )
        log.append(("installed", ".claude/settings.json (auto-approve read)"))


def deep_merge_settings(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base. Lists append without dupes, scalars overlay wins."""
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_settings(merged[key], value)
        elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
            for item in value:
                if item not in merged[key]:
                    merged[key].append(item)
        else:
            merged[key] = value
    return merged


def check_aws_profile(name: str) -> bool:
    """Check if an AWS profile exists in ~/.aws/config."""
    aws_config = Path.home() / ".aws" / "config"
    if not aws_config.exists():
        return False
    try:
        text = aws_config.read_text(encoding="utf-8")
        return f"[profile {name}]" in text
    except OSError:
        return False


def install_global_settings(default_model: str, log: list) -> None:
    """Install global ~/.claude/settings.json from template, merging with existing."""
    CLAUDE_HOME.mkdir(parents=True, exist_ok=True)

    # Load template
    try:
        template = json.loads(HOME_SETTINGS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.append(("warning", f"~/.claude/settings.json (failed to read template: {e})"))
        return

    # Inject model if selected
    if default_model != "none" and MODEL_CHOICES.get(default_model):
        template["model"] = MODEL_CHOICES[default_model]

    # Load existing settings
    existing = {}
    if CLAUDE_SETTINGS.exists():
        try:
            existing = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            bak = backup_file(CLAUDE_SETTINGS)
            log.append(("warning", f"~/.claude/settings.json (malformed JSON, backed up -> {bak})"))
            existing = {}

    # Merge: template is the base, existing user customizations preserved on top
    merged = deep_merge_settings(template, existing)

    # But always update env vars and permissions from template (template wins for these)
    if "env" in template:
        merged["env"] = deep_merge_settings(
            merged.get("env", {}), template["env"]
        )
    if "permissions" in template:
        for perm_key in ("allow", "deny", "ask"):
            if perm_key in template["permissions"]:
                base_list = merged.setdefault("permissions", {}).setdefault(perm_key, [])
                for item in template["permissions"][perm_key]:
                    if item not in base_list:
                        base_list.append(item)
        # Scalars from template permissions
        for scalar_key in ("defaultMode", "disableBypassPermissionsMode"):
            if scalar_key in template.get("permissions", {}):
                merged.setdefault("permissions", {})[scalar_key] = template["permissions"][scalar_key]

    # Override model from template if user selected one
    if default_model != "none" and MODEL_CHOICES.get(default_model):
        merged["model"] = MODEL_CHOICES[default_model]

    # Compare with existing to detect changes
    if existing == merged:
        log.append(("current", "~/.claude/settings.json"))
    else:
        if CLAUDE_SETTINGS.exists() and existing:
            bak = backup_file(CLAUDE_SETTINGS)
            CLAUDE_SETTINGS.write_text(
                json.dumps(merged, indent=2) + "\n", encoding="utf-8"
            )
            log.append(("updated", f"~/.claude/settings.json (backed up -> {bak})"))
        else:
            CLAUDE_SETTINGS.write_text(
                json.dumps(merged, indent=2) + "\n", encoding="utf-8"
            )
            log.append(("installed", "~/.claude/settings.json"))

    # Warn if AWS profile not found
    aws_profile = template.get("env", {}).get("AWS_PROFILE", "default")
    if not check_aws_profile(aws_profile):
        log.append(("warning",
            f"AWS profile '{aws_profile}' not found in ~/.aws/config — "
            f"run: aws configure sso --profile {aws_profile}"))

    # Install statusline script
    if HOME_STATUSLINE.exists():
        smart_install(HOME_STATUSLINE, CLAUDE_STATUSLINE, "~/.claude/statusline.sh", log)
        # Ensure executable
        import stat
        CLAUDE_STATUSLINE.chmod(CLAUDE_STATUSLINE.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_install(app) -> list:
    """Execute install based on app state. Returns log entries."""
    log = []

    # Snapshot existing files before making changes
    if app.scope in ("global", "both"):
        snap = create_snapshot()
        if snap:
            log.append(("snapshot", f"Backed up to {snap}"))

    if app.scope in ("global", "both"):
        # CLAUDE.md — always install/update
        smart_install(HOME_CLAUDE_MD, CLAUDE_MD, "~/.claude/CLAUDE.md", log)

        # Rules — install selected, remove deselected
        CLAUDE_RULES.mkdir(parents=True, exist_ok=True)
        for item in app.rule_info:
            name = item["name"]
            dest = CLAUDE_RULES / name
            if name in app.selected_rules:
                smart_install(item["src"], dest, f"~/.claude/rules/{name}", log)
            else:
                remove_with_log(dest, f"~/.claude/rules/{name}", log)

        # Agents — install selected, remove deselected
        CLAUDE_AGENTS.mkdir(parents=True, exist_ok=True)
        for item in app.agent_info:
            name = item["name"]
            dest = CLAUDE_AGENTS / name
            if name in app.selected_agents:
                smart_install(item["src"], dest, f"~/.claude/agents/{name}", log)
            else:
                remove_with_log(dest, f"~/.claude/agents/{name}", log)

        # Tasks
        if app.create_global_tasks:
            tasks_dir = CLAUDE_HOME / "tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            for tpl in ["lessons.md", "todo.md"]:
                src = TASKS_DIR / tpl
                dest = tasks_dir / tpl
                if dest.exists() and file_has_content(dest):
                    log.append(("skipped", f"~/.claude/tasks/{tpl} (has content)"))
                else:
                    shutil.copy2(src, dest)
                    log.append(("installed", f"~/.claude/tasks/{tpl}"))

        # Global settings.json (Bedrock config + permissions)
        install_global_settings(app.selected_model, log)

    if app.scope in ("project", "both"):
        cwd = app.cwd
        if is_git_repo(cwd):
            if app.create_project_tasks:
                tasks_dir = cwd / "tasks"
                tasks_dir.mkdir(parents=True, exist_ok=True)
                for tpl in ["lessons.md", "todo.md"]:
                    src = TASKS_DIR / tpl
                    dest = tasks_dir / tpl
                    if dest.exists() and file_has_content(dest):
                        log.append(("skipped", f"tasks/{tpl} (has content)"))
                    else:
                        shutil.copy2(src, dest)
                        log.append(("installed", f"tasks/{tpl}"))

            if app.auto_read:
                install_auto_read(cwd, log)
        else:
            log.append(("skipped", "Project install (not in a git repo)"))

    return log


# ---------------------------------------------------------------------------
# Textual CSS
# ---------------------------------------------------------------------------

INSTALLER_CSS = """
Screen {
    align: center middle;
}

.wizard {
    width: 90%;
    max-width: 100;
    height: auto;
    max-height: 95%;
    border: double $accent;
    padding: 1 2;
    background: $surface;
}

.title {
    width: 100%;
    text-align: center;
    text-style: bold;
    background: $accent;
    color: $text;
    padding: 0 2;
}

.subtitle {
    text-align: center;
    color: $text-muted;
    margin: 1 0;
}

.info {
    color: $text-muted;
}

.mandatory-note {
    color: $error;
    text-style: italic;
    margin: 0 0 0 2;
}

.legend {
    color: $text-muted;
    margin: 0 0 0 2;
}

SelectionList {
    height: auto;
    max-height: 18;
    margin: 1 0;
    border: solid $primary;

    & > .selection-list--button {
        color: $panel;
        background: $panel;
    }
    & > .selection-list--button-highlighted {
        color: $panel;
        background: $panel;
    }
    & > .selection-list--button-selected {
        color: $success;
        background: $panel;
        text-style: bold;
    }
    & > .selection-list--button-selected-highlighted {
        color: $success;
        background: $panel;
        text-style: bold;
    }
}

.help-text {
    color: $text-muted;
    text-style: italic;
    margin: 0 0 0 2;
}

RadioSet {
    width: 100%;
    margin: 1 0;
}

Checkbox {
    margin: 1 2;
}

.buttons {
    width: 100%;
    height: auto;
    align: center middle;
    margin-top: 1;
}

.buttons Button {
    margin: 0 1;
}

.log-box {
    width: 100%;
    height: auto;
    max-height: 20;
    border: solid $success;
    padding: 1 2;
    margin: 1 0;
}

.summary-box {
    width: 100%;
    height: auto;
    border: double $success;
    padding: 1 2;
    margin: 1 0;
}
"""


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

class ScopeScreen(Screen):
    BINDINGS = [
        Binding("enter", "next", "Next", priority=True),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        cwd = self.app.cwd
        in_repo = self.app.in_repo
        repo_info = f"  (repo: {get_repo_name(cwd)})" if in_repo else ""
        fresh = self.app.fresh_install

        with Container(classes="wizard"):
            yield Static("AI Coding Standards", classes="title")
            yield Static(
                "Standardized Claude Code configuration for your team",
                classes="subtitle",
            )
            yield Rule()
            yield Static(f"  {cwd}{repo_info}", classes="info")
            if not fresh:
                yield Static(
                    "  Existing installation detected — select items to add, update, or remove",
                    classes="info",
                )
            yield Static("")
            with RadioSet(id="scope-radio"):
                yield RadioButton(
                    "Global — CLAUDE.md + rules + agents to ~/.claude/",
                    value=True,
                )
                yield RadioButton(
                    f"Project — tasks + settings in current repo"
                    f"{'' if in_repo else '  (no repo detected)'}",
                )
                yield RadioButton("Both — global + project")
                yield RadioButton("Restore — restore from a previous backup")
            with Horizontal(classes="buttons"):
                yield Button("Next", variant="primary", id="btn-next")
                yield Button("Quit", variant="error", id="btn-quit")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.action_next()
        elif event.button.id == "btn-quit":
            self.action_quit()

    def action_next(self) -> None:
        radio = self.query_one("#scope-radio", RadioSet)
        idx = radio.pressed_index if radio.pressed_index >= 0 else 0
        self.app.scope = {0: "global", 1: "project", 2: "both", 3: "restore"}[idx]

        if self.app.scope == "restore":
            self.app.push_screen(RestoreScreen())
        elif self.app.scope in ("global", "both"):
            self.app.push_screen(RulesScreen())
        else:
            self.app.push_screen(ProjectScreen())

    def action_quit(self) -> None:
        self.app.exit()


class RulesScreen(Screen):
    BINDINGS = [
        Binding("enter", "next", "Next", priority=True),
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        fresh = self.app.fresh_install
        selections = []
        for item in self.app.rule_info:
            label = make_selection_label(item)
            # Pre-select: fresh = all, re-install = only installed/update + mandatory
            checked = fresh or item["status"] != "new" or item["mandatory"]
            selections.append(Selection(label, item["name"], checked))

        with Container(classes="wizard"):
            yield Static("Select Rules", classes="title")
            yield Static(
                "Auto-loaded from ~/.claude/rules/ every session",
                classes="subtitle",
            )
            yield Static("MANDATORY rules cannot be deselected", classes="mandatory-note")
            yield Static("  Space = toggle selection  |  Arrow keys = navigate  |  Enter = next", classes="help-text")
            legend = Text()
            legend.append("  NEW", style="cyan bold")
            legend.append(" = not yet installed   ", style="dim")
            legend.append("UP TO DATE", style="green")
            legend.append(" = current   ", style="dim")
            legend.append("UPDATE", style="yellow bold")
            legend.append(" = new version available", style="dim")
            yield Static(legend, classes="legend")
            yield SelectionList(*selections, id="rules-list")
            with Horizontal(classes="buttons"):
                yield Button("Back", id="btn-back")
                yield Button("Next", variant="primary", id="btn-next")
        yield Footer()

    @on(SelectionList.SelectionToggled, "#rules-list")
    def enforce_mandatory(self) -> None:
        sl = self.query_one("#rules-list", SelectionList)
        for name in MANDATORY_RULES:
            if name not in sl.selected:
                sl.select(name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.action_next()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_next(self) -> None:
        sl = self.query_one("#rules-list", SelectionList)
        self.app.selected_rules = set(sl.selected)
        self.app.push_screen(AgentsScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class AgentsScreen(Screen):
    BINDINGS = [
        Binding("enter", "next", "Next", priority=True),
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        fresh = self.app.fresh_install
        selections = []
        for item in self.app.agent_info:
            label = make_selection_label(item, show_model=True)
            checked = fresh or item["status"] != "new" or item["mandatory"]
            selections.append(Selection(label, item["name"], checked))

        with Container(classes="wizard"):
            yield Static("Select Agents", classes="title")
            yield Static(
                "Invoked via /agent-name in Claude Code",
                classes="subtitle",
            )
            yield Static("MANDATORY agents cannot be deselected", classes="mandatory-note")
            yield Static("  Space = toggle selection  |  Arrow keys = navigate  |  Enter = next", classes="help-text")
            legend = Text()
            legend.append("  NEW", style="cyan bold")
            legend.append(" = not yet installed   ", style="dim")
            legend.append("UP TO DATE", style="green")
            legend.append(" = current   ", style="dim")
            legend.append("UPDATE", style="yellow bold")
            legend.append(" = new version available", style="dim")
            yield Static(legend, classes="legend")
            yield SelectionList(*selections, id="agents-list")
            with Horizontal(classes="buttons"):
                yield Button("Back", id="btn-back")
                yield Button("Next", variant="primary", id="btn-next")
        yield Footer()

    @on(SelectionList.SelectionToggled, "#agents-list")
    def enforce_mandatory(self) -> None:
        sl = self.query_one("#agents-list", SelectionList)
        for name in MANDATORY_AGENTS:
            if name not in sl.selected:
                sl.select(name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.action_next()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_next(self) -> None:
        sl = self.query_one("#agents-list", SelectionList)
        self.app.selected_agents = set(sl.selected)
        self.app.push_screen(ModelScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class ModelScreen(Screen):
    BINDINGS = [
        Binding("enter", "next", "Next", priority=True),
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Container(classes="wizard"):
            yield Static("Default Model", classes="title")
            yield Static(
                "Choose your default Claude model for Bedrock",
                classes="subtitle",
            )
            yield Rule()
            yield Static(
                "  This sets the model Claude Code uses when you type 'claude'.",
                classes="info",
            )
            yield Static(
                "  You can always override per-session with --model.",
                classes="info",
            )
            yield Static("")
            with RadioSet(id="model-radio"):
                yield RadioButton(
                    "Sonnet — Balanced: good for most tasks, cost-effective",
                    value=True,
                )
                yield RadioButton(
                    "Opus — Maximum capability: complex architecture, deep reasoning",
                )
                yield RadioButton(
                    "Haiku — Fast and light: quick edits, simple questions",
                )
                yield RadioButton(
                    "No default — Don't set a default model",
                )
            with Horizontal(classes="buttons"):
                yield Button("Back", id="btn-back")
                yield Button("Next", variant="primary", id="btn-next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.action_next()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_next(self) -> None:
        radio = self.query_one("#model-radio", RadioSet)
        idx = radio.pressed_index if radio.pressed_index >= 0 else 0
        self.app.selected_model = {0: "sonnet", 1: "opus", 2: "haiku", 3: "none"}[idx]
        self.app.push_screen(OptionsScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class OptionsScreen(Screen):
    BINDINGS = [
        Binding("enter", "install", "Install", priority=True),
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        show_project = self.app.scope in ("project", "both")
        in_repo = self.app.in_repo

        with Container(classes="wizard"):
            yield Static("Options", classes="title")
            yield Static("Final settings before installation", classes="subtitle")
            yield Rule()

            if self.app.scope in ("global", "both"):
                yield Static("  Global:", classes="info")
                yield Checkbox(
                    "Create ~/.claude/tasks/ (lessons + todo)",
                    True,
                    id="global-tasks",
                )

            if show_project and in_repo:
                yield Static("")
                yield Static(
                    f"  Project: {get_repo_name(self.app.cwd)}",
                    classes="info",
                )
                yield Checkbox(
                    "Create ./tasks/ (lessons + todo)",
                    True,
                    id="project-tasks",
                )
                yield Checkbox(
                    "Auto-approve read operations for agents (creates .claude/settings.json)",
                    True,
                    id="auto-read",
                )
                yield Static(
                    "  Tip: Use /init inside Claude Code to generate a project CLAUDE.md",
                    classes="help-text",
                )
            elif show_project and not in_repo:
                yield Static("")
                yield Static(
                    "  Project install will be skipped — not in a git repo",
                    classes="mandatory-note",
                )

            yield Static("")
            with Horizontal(classes="buttons"):
                yield Button("Back", id="btn-back")
                yield Button("Install", variant="success", id="btn-install")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-install":
            self.action_install()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_install(self) -> None:
        try:
            self.app.create_global_tasks = self.query_one(
                "#global-tasks", Checkbox
            ).value
        except Exception:
            self.app.create_global_tasks = False
        try:
            self.app.create_project_tasks = self.query_one(
                "#project-tasks", Checkbox
            ).value
        except Exception:
            self.app.create_project_tasks = False
        try:
            self.app.auto_read = self.query_one(
                "#auto-read", Checkbox
            ).value
        except Exception:
            self.app.auto_read = False
        self.app.push_screen(ResultScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class ProjectScreen(Screen):
    BINDINGS = [
        Binding("enter", "install", "Install", priority=True),
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        in_repo = self.app.in_repo

        with Container(classes="wizard"):
            yield Static("Project Setup", classes="title")
            yield Static(
                "Configure tasks and settings for your repository",
                classes="subtitle",
            )
            yield Rule()

            if in_repo:
                yield Static(
                    f"  Detected repo: {get_repo_name(self.app.cwd)}",
                    classes="info",
                )
                yield Static("")
                yield Checkbox(
                    "Create ./tasks/ (lessons + todo)",
                    True,
                    id="project-tasks",
                )
                yield Checkbox(
                    "Auto-approve read operations for agents (creates .claude/settings.json)",
                    True,
                    id="auto-read",
                )
                yield Static(
                    "  Tip: Use /init inside Claude Code to generate a project CLAUDE.md",
                    classes="help-text",
                )
                yield Static("")
                with Horizontal(classes="buttons"):
                    yield Button("Back", id="btn-back")
                    yield Button("Install", variant="success", id="btn-install")
            else:
                yield Static(
                    "  Not inside a git repository",
                    classes="mandatory-note",
                )
                yield Static(f"  {self.app.cwd}", classes="info")
                yield Static("")
                yield Static("  Project install requires a git repo.", classes="info")
                yield Static("")
                with Horizontal(classes="buttons"):
                    yield Button("Back", id="btn-back")
                    yield Button("Quit", variant="error", id="btn-quit")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-install":
            self.action_install()
        elif event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-quit":
            self.app.exit()

    def action_install(self) -> None:
        try:
            self.app.create_project_tasks = self.query_one(
                "#project-tasks", Checkbox
            ).value
        except Exception:
            self.app.create_project_tasks = False
        try:
            self.app.auto_read = self.query_one(
                "#auto-read", Checkbox
            ).value
        except Exception:
            self.app.auto_read = False
        self.app.push_screen(ResultScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class ResultScreen(Screen):
    BINDINGS = [
        Binding("enter", "done", "Exit", priority=True),
        Binding("q", "done", "Exit"),
    ]

    def compose(self) -> ComposeResult:
        log = run_install(self.app)

        log_lines = []
        for status, label in log:
            if status == "installed":
                log_lines.append(f"[green]  +  INSTALLED  {label}[/green]")
            elif status == "updated":
                log_lines.append(f"[yellow]  ~  UPDATED    {label}[/yellow]")
            elif status == "removed":
                log_lines.append(f"[red]  -  REMOVED    {label}[/red]")
            elif status == "current":
                log_lines.append(f"[dim]  =  CURRENT    {label}[/dim]")
            elif status == "skipped":
                log_lines.append(f"[dim]  .  SKIPPED    {label}[/dim]")
            elif status == "snapshot":
                log_lines.append(f"[cyan]  ◆  SNAPSHOT   {label}[/cyan]")
            elif status == "restored":
                log_lines.append(f"[green]  ↩  RESTORED   {label}[/green]")
            elif status == "warning":
                log_lines.append(f"[yellow]  ⚠  WARNING    {label}[/yellow]")
        log_text = "\n".join(log_lines) if log_lines else "  Nothing to install."

        # Count actions
        counts = {}
        for status, _ in log:
            counts[status] = counts.get(status, 0) + 1
        summary_parts = []
        if counts.get("installed", 0):
            summary_parts.append(f"[green]{counts['installed']} installed[/green]")
        if counts.get("updated", 0):
            summary_parts.append(f"[yellow]{counts['updated']} updated[/yellow]")
        if counts.get("removed", 0):
            summary_parts.append(f"[red]{counts['removed']} removed[/red]")
        if counts.get("current", 0):
            summary_parts.append(f"[dim]{counts['current']} unchanged[/dim]")
        if counts.get("warning", 0):
            summary_parts.append(f"[yellow]{counts['warning']} warnings[/yellow]")
        count_line = "  " + "  |  ".join(summary_parts) if summary_parts else ""

        path_lines = []
        if self.app.scope in ("global", "both"):
            path_lines.append(f"  CLAUDE.md   {CLAUDE_MD}")
            path_lines.append(f"  Rules       {CLAUDE_RULES}/")
            path_lines.append(f"  Agents      {CLAUDE_AGENTS}/")
        if self.app.scope in ("project", "both") and self.app.in_repo:
            path_lines.append(f"  Project     {self.app.cwd}")
        path_text = "\n".join(path_lines)

        with Container(classes="wizard"):
            yield Static("Installation Complete", classes="title")
            yield Static("")
            if count_line:
                yield Static(count_line)
                yield Static("")
            yield Static(log_text, classes="log-box")
            if path_text:
                yield Static("")
                yield Static(path_text, classes="summary-box")
            yield Static("")
            yield Static(
                "  Re-run this script anytime to add, update, or remove items.",
                classes="info",
            )
            yield Static("")
            with Horizontal(classes="buttons"):
                yield Button("Done", variant="success", id="btn-done")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-done":
            self.action_done()

    def action_done(self) -> None:
        self.app.exit()


class RestoreScreen(Screen):
    BINDINGS = [
        Binding("enter", "restore", "Restore", priority=True),
        Binding("escape", "back", "Back"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        snapshots = discover_snapshots()

        with Container(classes="wizard"):
            yield Static("Restore from Backup", classes="title")
            yield Static(
                "Select a snapshot to restore your ~/.claude/ files",
                classes="subtitle",
            )
            yield Rule()

            if snapshots:
                with RadioSet(id="snap-radio"):
                    for i, (ts, path) in enumerate(snapshots):
                        # Count files in snapshot
                        count = sum(1 for _ in path.rglob("*") if _.is_file())
                        label = f"{ts[:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}  ({count} files)"
                        yield RadioButton(label, value=(i == 0))
                self._snapshots = snapshots
                yield Static("")
                with Horizontal(classes="buttons"):
                    yield Button("Back", id="btn-back")
                    yield Button("Restore", variant="warning", id="btn-restore")
            else:
                yield Static(
                    "  No backups found in ~/.claude/backups/",
                    classes="mandatory-note",
                )
                self._snapshots = []
                yield Static("")
                with Horizontal(classes="buttons"):
                    yield Button("Back", id="btn-back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-restore":
            self.action_restore()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_restore(self) -> None:
        if not self._snapshots:
            return
        radio = self.query_one("#snap-radio", RadioSet)
        idx = radio.pressed_index if radio.pressed_index >= 0 else 0
        _, snap_path = self._snapshots[idx]
        log = restore_snapshot(snap_path)
        self.app.restore_log = log
        self.app.restore_snap = snap_path.name
        self.app.push_screen(RestoreResultScreen())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


class RestoreResultScreen(Screen):
    BINDINGS = [
        Binding("enter", "done", "Exit", priority=True),
        Binding("q", "done", "Exit"),
    ]

    def compose(self) -> ComposeResult:
        log = self.app.restore_log

        log_lines = []
        for status, label in log:
            if status == "restored":
                log_lines.append(f"[green]  ↩  RESTORED   {label}[/green]")
            elif status == "current":
                log_lines.append(f"[dim]  =  CURRENT    {label}[/dim]")
        log_text = "\n".join(log_lines) if log_lines else "  Nothing to restore."

        restored_count = sum(1 for s, _ in log if s == "restored")
        current_count = sum(1 for s, _ in log if s == "current")

        with Container(classes="wizard"):
            yield Static("Restore Complete", classes="title")
            yield Static(f"  From snapshot: {self.app.restore_snap}", classes="info")
            yield Static("")
            parts = []
            if restored_count:
                parts.append(f"[green]{restored_count} restored[/green]")
            if current_count:
                parts.append(f"[dim]{current_count} unchanged[/dim]")
            if parts:
                yield Static("  " + "  |  ".join(parts))
                yield Static("")
            yield Static(log_text, classes="log-box")
            yield Static("")
            with Horizontal(classes="buttons"):
                yield Button("Done", variant="success", id="btn-done")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-done":
            self.action_done()

    def action_done(self) -> None:
        self.app.exit()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class InstallerApp(App):
    CSS = INSTALLER_CSS
    TITLE = "AI Coding Standards"
    SUB_TITLE = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scope = "global"
        self.selected_rules = set()
        self.selected_agents = set()
        self.create_global_tasks = True
        self.create_project_tasks = True
        self.auto_read = False
        self.selected_model = "sonnet"
        self.restore_log = []
        self.restore_snap = ""
        self.cwd = Path.cwd()
        self.in_repo = is_git_repo(self.cwd)
        self.fresh_install = is_fresh_install()

        # Discover source files + compare with installed
        self.rules = discover_files(HOME_RULES_DIR)
        self.agents = discover_files(AGENTS_DIR)
        self.rule_info = build_file_info(self.rules, CLAUDE_RULES, MANDATORY_RULES)
        self.agent_info = build_file_info(self.agents, CLAUDE_AGENTS, MANDATORY_AGENTS)

    def on_mount(self) -> None:
        self.push_screen(ScopeScreen())


# ---------------------------------------------------------------------------
# Non-interactive CLI helpers
# ---------------------------------------------------------------------------

def run_update() -> None:
    """Pull latest standards from git."""
    import subprocess
    print("Updating standards from git...")
    result = subprocess.run(
        ["git", "-C", str(SCRIPT_DIR), "pull"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        output = result.stdout.strip()
        if "Already up to date" in output:
            print("  Already up to date.")
        else:
            print(f"  Updated: {output}")
    else:
        print(f"  Error: {result.stderr.strip()}")


def run_cli(args) -> None:
    """Non-interactive install using existing helpers."""
    cwd = Path.cwd()
    in_repo = is_git_repo(cwd)

    # Determine scope
    if args.both:
        scope = "both"
    elif args.scope_project:
        scope = "project"
    else:
        scope = "global"

    # Snapshot existing files before making changes
    if scope in ("global", "both"):
        snap = create_snapshot()
        if snap:
            print(f"  Backed up existing files to {snap}")

    # Discover source files and build info
    rules = discover_files(HOME_RULES_DIR)
    agents = discover_files(AGENTS_DIR)
    rule_info = build_file_info(rules, CLAUDE_RULES, MANDATORY_RULES)
    agent_info = build_file_info(agents, CLAUDE_AGENTS, MANDATORY_AGENTS)

    log = []

    # --- Global install ---
    if scope in ("global", "both"):
        # CLAUDE.md
        smart_install(HOME_CLAUDE_MD, CLAUDE_MD, "~/.claude/CLAUDE.md", log)

        # All rules (non-interactive = install everything)
        CLAUDE_RULES.mkdir(parents=True, exist_ok=True)
        for item in rule_info:
            dest = CLAUDE_RULES / item["name"]
            smart_install(item["src"], dest, f"~/.claude/rules/{item['name']}", log)

        # All agents
        CLAUDE_AGENTS.mkdir(parents=True, exist_ok=True)
        for item in agent_info:
            dest = CLAUDE_AGENTS / item["name"]
            smart_install(item["src"], dest, f"~/.claude/agents/{item['name']}", log)

        # Tasks (unless --no-tasks)
        if not args.no_tasks:
            tasks_dir = CLAUDE_HOME / "tasks"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            for tpl in ["lessons.md", "todo.md"]:
                src = TASKS_DIR / tpl
                dest = tasks_dir / tpl
                if dest.exists() and file_has_content(dest):
                    log.append(("skipped", f"~/.claude/tasks/{tpl} (has content)"))
                else:
                    shutil.copy2(src, dest)
                    log.append(("installed", f"~/.claude/tasks/{tpl}"))

        # Global settings.json (Bedrock config + permissions)
        install_global_settings(args.model, log)

    # --- Project install ---
    if scope in ("project", "both"):
        if in_repo:
            if not args.no_tasks:
                tasks_dir = cwd / "tasks"
                tasks_dir.mkdir(parents=True, exist_ok=True)
                for tpl in ["lessons.md", "todo.md"]:
                    src = TASKS_DIR / tpl
                    dest = tasks_dir / tpl
                    if dest.exists() and file_has_content(dest):
                        log.append(("skipped", f"tasks/{tpl} (has content)"))
                    else:
                        shutil.copy2(src, dest)
                        log.append(("installed", f"tasks/{tpl}"))

            if args.auto_read:
                install_auto_read(cwd, log)
        else:
            print("  Skipped project install — not in a git repo.")
            log.append(("skipped", "Project install (not in a git repo)"))

    # --- Print results ---
    print()
    STATUS_COLORS = {
        "installed": "\033[32m",  # green
        "updated":   "\033[33m",  # yellow
        "removed":   "\033[31m",  # red
        "current":   "\033[90m",  # dim
        "skipped":   "\033[90m",  # dim
        "snapshot":  "\033[36m",  # cyan
        "restored":  "\033[32m",  # green
        "warning":   "\033[33m",  # yellow
    }
    STATUS_SYMBOLS = {
        "installed": "+  INSTALLED",
        "updated":   "~  UPDATED  ",
        "removed":   "-  REMOVED  ",
        "current":   "=  CURRENT  ",
        "skipped":   ".  SKIPPED  ",
        "snapshot":  "◆  SNAPSHOT ",
        "restored":  "↩  RESTORED ",
        "warning":   "⚠  WARNING ",
    }
    RESET = "\033[0m"

    for status, label in log:
        color = STATUS_COLORS.get(status, "")
        symbol = STATUS_SYMBOLS.get(status, "   ")
        print(f"  {color}{symbol}  {label}{RESET}")

    # Summary counts
    counts = {}
    for status, _ in log:
        counts[status] = counts.get(status, 0) + 1
    parts = []
    if counts.get("installed", 0):
        parts.append(f"{counts['installed']} installed")
    if counts.get("updated", 0):
        parts.append(f"{counts['updated']} updated")
    if counts.get("removed", 0):
        parts.append(f"{counts['removed']} removed")
    if counts.get("current", 0):
        parts.append(f"{counts['current']} unchanged")
    if counts.get("skipped", 0):
        parts.append(f"{counts['skipped']} skipped")
    if counts.get("warning", 0):
        parts.append(f"\033[33m{counts['warning']} warnings{RESET}")
    if parts:
        print(f"\n  {' | '.join(parts)}")
    print()


# ---------------------------------------------------------------------------
# CLI uninstall
# ---------------------------------------------------------------------------

def run_uninstall() -> None:
    """Remove all managed files from ~/.claude/, with a snapshot backup first."""
    RESET = "\033[0m"

    if not CLAUDE_HOME.exists():
        print("  Nothing to uninstall — ~/.claude/ does not exist.")
        return

    # Snapshot before removing anything
    snap = create_snapshot()
    if snap:
        print(f"  \033[36m◆  SNAPSHOT   Backed up to {snap}{RESET}")

    removed = 0

    # Remove CLAUDE.md
    claude_md = CLAUDE_HOME / "CLAUDE.md"
    if claude_md.exists() and not claude_md.is_symlink():
        claude_md.unlink()
        print(f"  \033[31m-  REMOVED    ~/.claude/CLAUDE.md{RESET}")
        removed += 1

    # Remove managed directories
    for dirname in ("rules", "agents", "tasks"):
        d = CLAUDE_HOME / dirname
        if d.exists() and d.is_dir():
            count = sum(1 for f in d.iterdir() if f.is_file() and not f.is_symlink())
            shutil.rmtree(d)
            print(f"  \033[31m-  REMOVED    ~/.claude/{dirname}/ ({count} files){RESET}")
            removed += 1

    if removed:
        print(f"\n  Uninstalled. Backup saved to {snap}")
        print("  To undo: ai-coding-standards --restore")
    else:
        print("  Nothing to remove — no managed files found.")
    print()


# ---------------------------------------------------------------------------
# CLI restore
# ---------------------------------------------------------------------------

def run_restore_cli(args) -> None:
    """Non-interactive restore from a snapshot."""
    snapshots = discover_snapshots()
    if not snapshots:
        print("  No backups found in ~/.claude/backups/")
        return

    # Use --restore=TIMESTAMP to pick a specific snapshot, or latest
    target = args.restore if isinstance(args.restore, str) else None
    snap_dir = None

    if target:
        for ts, path in snapshots:
            if ts == target:
                snap_dir = path
                break
        if not snap_dir:
            print(f"  Snapshot '{target}' not found. Available:")
            for ts, path in snapshots:
                count = sum(1 for _ in path.rglob("*") if _.is_file())
                print(f"    {ts}  ({count} files)")
            return
    else:
        # Default to latest
        _, snap_dir = snapshots[0]

    print(f"  Restoring from {snap_dir.name}...")
    log = restore_snapshot(snap_dir)

    # Print results
    RESET = "\033[0m"
    for status, label in log:
        if status == "restored":
            print(f"  \033[32m↩  RESTORED   {label}{RESET}")
        elif status == "current":
            print(f"  \033[90m=  CURRENT    {label}{RESET}")

    restored = sum(1 for s, _ in log if s == "restored")
    current = sum(1 for s, _ in log if s == "current")
    parts = []
    if restored:
        parts.append(f"{restored} restored")
    if current:
        parts.append(f"{current} unchanged")
    if parts:
        print(f"\n  {' | '.join(parts)}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        prog="ai-coding-standards",
        description="AI Coding Standards Installer",
    )
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument("--global", dest="scope_global", action="store_true",
                             help="Install globally (~/.claude/) without TUI")
    scope_group.add_argument("--project", dest="scope_project", action="store_true",
                             help="Install project tasks and settings in current directory")
    scope_group.add_argument("--both", action="store_true",
                             help="Install global + project")
    scope_group.add_argument("--restore", nargs="?", const=True, default=False,
                             metavar="TIMESTAMP",
                             help="Restore from a backup (optionally specify YYYYMMDD-HHMMSS)")
    scope_group.add_argument("--uninstall", action="store_true",
                             help="Remove all managed files from ~/.claude/ (with backup)")
    parser.add_argument("--update", action="store_true",
                        help="Update standards from git, then install")
    parser.add_argument("--no-tasks", dest="no_tasks", action="store_true",
                        help="Skip creating tasks/ directories")
    parser.add_argument("--auto-read", dest="auto_read", action="store_true",
                        help="Auto-approve read operations for agents in project")
    parser.add_argument("--model", choices=["sonnet", "opus", "haiku", "none"],
                        default="sonnet",
                        help="Default Claude model for Bedrock (default: sonnet)")
    args = parser.parse_args()

    if args.update:
        run_update()

    if args.uninstall:
        run_uninstall()
    elif args.restore:
        run_restore_cli(args)
    elif args.scope_global or args.scope_project or args.both:
        run_cli(args)
    elif not args.update:
        if not _TEXTUAL_AVAILABLE:
            print()
            print("  textual is required for the interactive installer.")
            print()
            print("  Install it with:")
            print("    pip install textual")
            print()
            print("  Or use CLI flags: --global, --project, --both, --restore")
            sys.exit(1)
        app = InstallerApp()
        app.run()
    else:
        print("  Updated. Use --global, --project, or --both to also install.")


if __name__ == "__main__":
    main()
