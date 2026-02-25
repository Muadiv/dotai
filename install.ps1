<#
.SYNOPSIS
    dotai - Interactive PowerShell Installer

.DESCRIPTION
    Menu-driven installer for standardized Claude Code configuration.
    Alternative to install.py for Windows users without Python.
    Works on PowerShell 5.1+ (Windows) and PowerShell 7+ (any platform).

.EXAMPLE
    .\install.ps1               # Windows PowerShell
    pwsh install.ps1            # PowerShell 7 (any platform)
#>

param(
    [switch]$Global,
    [switch]$Project,
    [switch]$Both,
    [switch]$Update,
    [switch]$NoTasks,
    [switch]$Restore,
    [string]$RestoreTimestamp = "",
    [switch]$AutoRead,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$HomeDir = Join-Path (Join-Path $ScriptDir "standards") "home"
$HomeClaude = Join-Path $HomeDir "CLAUDE.md"
$HomeRulesDir = Join-Path $HomeDir "rules"
$AgentsDir = Join-Path (Join-Path $ScriptDir "standards") "agents"
$TasksDir = Join-Path (Join-Path $ScriptDir "standards") "tasks"

$ClaudeHome = $(if ($env:USERPROFILE) {
    Join-Path $env:USERPROFILE ".claude"
} else {
    Join-Path $HOME ".claude"
})
$ClaudeMd = Join-Path $ClaudeHome "CLAUDE.md"
$ClaudeRules = Join-Path $ClaudeHome "rules"
$ClaudeAgents = Join-Path $ClaudeHome "agents"
$BackupsDir = Join-Path $ClaudeHome "backups"

$MandatoryRules = @("security.md")
$MandatoryAgents = @("security-auditor.md", "compliance-reviewer.md")

$HomeSettingsJson = Join-Path $HomeDir "settings.json"
$HomeStatusline = Join-Path $HomeDir "statusline.sh"
$ClaudeSettings = Join-Path $ClaudeHome "settings.json"
$ClaudeStatusline = Join-Path $ClaudeHome "statusline.sh"


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

function Get-MdFiles {
    param([string]$Directory)
    if (-not (Test-Path $Directory)) { return @() }
    Get-ChildItem -Path $Directory -Filter "*.md" |
        Where-Object { -not $_.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint) } |
        Sort-Object Name |
        ForEach-Object { @{ Name = $_.Name; Path = $_.FullName } }
}

function Test-GitRepo {
    param([string]$Path)
    $current = (Resolve-Path $Path).Path
    while ($true) {
        if (Test-Path (Join-Path $current ".git")) { return $true }
        $parent = Split-Path $current -Parent
        if ($parent -eq $current -or [string]::IsNullOrEmpty($parent)) { return $false }
        $current = $parent
    }
}

function Get-RepoName {
    param([string]$Path)
    $current = (Resolve-Path $Path).Path
    while ($true) {
        if (Test-Path (Join-Path $current ".git")) { return Split-Path $current -Leaf }
        $parent = Split-Path $current -Parent
        if ($parent -eq $current -or [string]::IsNullOrEmpty($parent)) { return Split-Path $Path -Leaf }
        $current = $parent
    }
}

function Get-FileStatus {
    param([string]$Src, [string]$Dest)
    if (-not (Test-Path $Dest)) { return "new" }
    $srcHash = (Get-FileHash $Src -Algorithm SHA256).Hash
    $destHash = (Get-FileHash $Dest -Algorithm SHA256).Hash
    if ($srcHash -eq $destHash) { return "installed" } else { return "update" }
}

function Get-Heading {
    param([string]$FilePath)
    foreach ($line in (Get-Content $FilePath)) {
        if ($line -match "^#") {
            return ($line -replace "^#+\s*", "").Trim()
        }
    }
    return [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
}

function Get-FrontmatterField {
    param([string]$FilePath, [string]$Field)
    $lines = Get-Content $FilePath
    if ($lines.Count -lt 2 -or $lines[0] -ne "---") { return "" }
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -eq "---") { break }
        if ($lines[$i] -match "^${Field}:\s*(.+)$") { return $Matches[1].Trim() }
    }
    return ""
}

function Get-Description {
    param([string]$FilePath)
    Get-FrontmatterField -FilePath $FilePath -Field "description"
}

function Get-Model {
    param([string]$FilePath)
    Get-FrontmatterField -FilePath $FilePath -Field "model"
}

function Backup-File {
    param([string]$FilePath)
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    $name = Split-Path $FilePath -Leaf
    $dir = Split-Path $FilePath -Parent
    $backupName = "$name.bak.$ts"
    $backupPath = Join-Path $dir $backupName
    Copy-Item -Path $FilePath -Destination $backupPath -Force
    return $backupName
}

function Test-HasContent {
    param([string]$FilePath)
    if (-not (Test-Path $FilePath)) { return $false }
    $text = Get-Content $FilePath -Raw
    if ([string]::IsNullOrWhiteSpace($text)) { return $false }
    $text = $text -replace "(?s)<!--.*?-->", ""
    $lines = $text -split "`n" | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") }
    return ($lines.Count -gt 0)
}

function Test-FreshInstall {
    return -not (Test-Path $ClaudeMd)
}

function New-Snapshot {
    if (-not (Test-Path $ClaudeHome)) { return $null }

    # Only snapshot files we manage: CLAUDE.md, settings.json, rules/, agents/, tasks/
    $filesToSnap = @()
    $claudeMdFile = Join-Path $ClaudeHome "CLAUDE.md"
    if (Test-Path $claudeMdFile) {
        $filesToSnap += Get-Item $claudeMdFile
    }
    $settingsFile = Join-Path $ClaudeHome "settings.json"
    if (Test-Path $settingsFile) {
        $filesToSnap += Get-Item $settingsFile
    }
    $statuslineFile = Join-Path $ClaudeHome "statusline.sh"
    if (Test-Path $statuslineFile) {
        $filesToSnap += Get-Item $statuslineFile
    }
    foreach ($subdir in @("rules", "agents", "tasks")) {
        $d = Join-Path $ClaudeHome $subdir
        if (Test-Path $d) {
            foreach ($f in (Get-ChildItem -Path $d -File |
                Where-Object { -not $_.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint) })) {
                $filesToSnap += $f
            }
        }
    }

    if ($filesToSnap.Count -eq 0) { return $null }

    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    $snapDir = Join-Path $BackupsDir $ts
    New-Item -Path $snapDir -ItemType Directory -Force | Out-Null

    foreach ($f in $filesToSnap) {
        $rel = $f.FullName.Substring($ClaudeHome.Length + 1)
        $dest = Join-Path $snapDir $rel
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) {
            New-Item -Path $destDir -ItemType Directory -Force | Out-Null
        }
        Copy-Item -Path $f.FullName -Destination $dest -Force
    }

    return $snapDir
}

function Get-Snapshots {
    if (-not (Test-Path $BackupsDir)) { return @() }
    $snaps = @()
    foreach ($d in (Get-ChildItem -Path $BackupsDir -Directory | Sort-Object Name -Descending)) {
        if ($d.Name -match '^\d{8}-\d{6}$') {
            $snaps += @{ Name = $d.Name; Path = $d.FullName }
        }
    }
    return $snaps
}

function Invoke-Restore {
    param([string]$SnapDir)
    $log = [System.Collections.ArrayList]::new()
    $resolvedHome = (Resolve-Path $ClaudeHome).Path
    foreach ($f in (Get-ChildItem -Path $SnapDir -File -Recurse |
        Where-Object { -not $_.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint) })) {
        $rel = $f.FullName.Substring($SnapDir.Length + 1)
        $dest = Join-Path $ClaudeHome $rel
        # Verify destination stays under ~/.claude/
        $resolvedDest = [System.IO.Path]::GetFullPath($dest)
        if (-not $resolvedDest.StartsWith($resolvedHome)) { continue }
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) {
            New-Item -Path $destDir -ItemType Directory -Force | Out-Null
        }
        if (Test-Path $dest) {
            if ((Get-FileHash $f.FullName -Algorithm SHA256).Hash -eq (Get-FileHash $dest -Algorithm SHA256).Hash) {
                [void]$log.Add(@{ Status = "current"; Label = "~/.claude/$rel" })
                continue
            }
            Backup-File -FilePath $dest | Out-Null
        }
        Copy-Item -Path $f.FullName -Destination $dest -Force
        [void]$log.Add(@{ Status = "restored"; Label = "~/.claude/$rel" })
    }
    return $log
}

# ---------------------------------------------------------------------------
# Build file info (status, mandatory, heading, model)
# ---------------------------------------------------------------------------

function Build-FileInfo {
    param(
        [array]$SourceFiles,
        [string]$InstallDir,
        [array]$Mandatory
    )
    $items = @()
    foreach ($file in $SourceFiles) {
        $dest = Join-Path $InstallDir $file.Name
        $status = Get-FileStatus -Src $file.Path -Dest $dest
        $items += @{
            Name        = $file.Name
            Src         = $file.Path
            Status      = $status
            Mandatory   = $file.Name -in $Mandatory
            Heading     = Get-Heading -FilePath $file.Path
            Description = Get-Description -FilePath $file.Path
            Model       = Get-Model -FilePath $file.Path
        }
    }
    return $items
}

# ---------------------------------------------------------------------------
# Smart install / remove
# ---------------------------------------------------------------------------

function Install-SmartFile {
    param([string]$Src, [string]$Dest, [string]$Label, [System.Collections.ArrayList]$Log)
    $dir = Split-Path $Dest -Parent
    if (-not (Test-Path $dir)) { New-Item -Path $dir -ItemType Directory -Force | Out-Null }

    if (-not (Test-Path $Dest)) {
        Copy-Item -Path $Src -Destination $Dest -Force
        [void]$Log.Add(@{ Status = "installed"; Label = $Label })
    }
    elseif ((Get-FileHash $Src -Algorithm SHA256).Hash -ne (Get-FileHash $Dest -Algorithm SHA256).Hash) {
        $bak = Backup-File -FilePath $Dest
        Copy-Item -Path $Src -Destination $Dest -Force
        [void]$Log.Add(@{ Status = "updated"; Label = "$Label (backed up -> $bak)" })
    }
    else {
        [void]$Log.Add(@{ Status = "current"; Label = $Label })
    }
}

function Remove-WithLog {
    param([string]$Dest, [string]$Label, [System.Collections.ArrayList]$Log)
    if (Test-Path $Dest) {
        $bak = Backup-File -FilePath $Dest
        Remove-Item -Path $Dest -Force
        [void]$Log.Add(@{ Status = "removed"; Label = "$Label (backed up -> $bak)" })
    }
}

function ConvertTo-Hashtable {
    param([Parameter(ValueFromPipeline)]$InputObject)
    process {
        if ($null -eq $InputObject) { return @{} }
        if ($InputObject -is [System.Collections.Hashtable]) { return $InputObject }
        $hash = @{}
        foreach ($prop in $InputObject.PSObject.Properties) {
            if ($prop.Value -is [PSCustomObject]) {
                $hash[$prop.Name] = ConvertTo-Hashtable -InputObject $prop.Value
            }
            elseif ($prop.Value -is [System.Collections.IEnumerable] -and $prop.Value -isnot [string]) {
                $hash[$prop.Name] = @($prop.Value)
            }
            else {
                $hash[$prop.Name] = $prop.Value
            }
        }
        return $hash
    }
}

function Merge-DeepSettings {
    param(
        [hashtable]$Base,
        [hashtable]$Overlay
    )
    $merged = @{}
    foreach ($key in $Base.Keys) { $merged[$key] = $Base[$key] }
    foreach ($key in $Overlay.Keys) {
        if ($merged.ContainsKey($key) -and $merged[$key] -is [hashtable] -and $Overlay[$key] -is [hashtable]) {
            $merged[$key] = Merge-DeepSettings -Base $merged[$key] -Overlay $Overlay[$key]
        }
        elseif ($merged.ContainsKey($key) -and $merged[$key] -is [array] -and $Overlay[$key] -is [array]) {
            foreach ($item in $Overlay[$key]) {
                if ($item -notin $merged[$key]) {
                    $merged[$key] += $item
                }
            }
        }
        else {
            $merged[$key] = $Overlay[$key]
        }
    }
    return $merged
}


function Install-GlobalSettings {
    param(
        [System.Collections.ArrayList]$Log
    )

    if (-not (Test-Path $ClaudeHome)) {
        New-Item -Path $ClaudeHome -ItemType Directory -Force | Out-Null
    }

    # Load template
    try {
        $templateJson = Get-Content $HomeSettingsJson -Raw
        $template = ConvertTo-Hashtable -InputObject ($templateJson | ConvertFrom-Json)
    } catch {
        [void]$Log.Add(@{ Status = "warning"; Label = "~/.claude/settings.json (failed to read template: $_)" })
        return
    }

    # Load existing settings
    $existing = @{}
    if (Test-Path $ClaudeSettings) {
        try {
            $existingJson = Get-Content $ClaudeSettings -Raw
            $existing = ConvertTo-Hashtable -InputObject ($existingJson | ConvertFrom-Json)
        } catch {
            $bak = Backup-File -FilePath $ClaudeSettings
            [void]$Log.Add(@{ Status = "warning"; Label = "~/.claude/settings.json (malformed JSON, backed up -> $bak)" })
            $existing = @{}
        }
    }

    # Merge: template is the base, existing user customizations preserved on top
    $merged = Merge-DeepSettings -Base $template -Overlay $existing

    # Ensure template env vars are present
    if ($template.ContainsKey("env")) {
        if (-not $merged.ContainsKey("env")) { $merged["env"] = @{} }
        foreach ($envKey in $template["env"].Keys) {
            $merged["env"][$envKey] = $template["env"][$envKey]
        }
    }

    # Ensure template permissions lists are present
    if ($template.ContainsKey("permissions")) {
        if (-not $merged.ContainsKey("permissions")) { $merged["permissions"] = @{} }
        foreach ($permKey in @("allow", "deny", "ask")) {
            if ($template["permissions"].ContainsKey($permKey)) {
                if (-not $merged["permissions"].ContainsKey($permKey)) { $merged["permissions"][$permKey] = @() }
                foreach ($item in $template["permissions"][$permKey]) {
                    if ($item -notin $merged["permissions"][$permKey]) {
                        $merged["permissions"][$permKey] += $item
                    }
                }
            }
        }
        # Scalar permission keys from template
        foreach ($scalarKey in @("defaultMode", "disableBypassPermissionsMode")) {
            if ($template["permissions"].ContainsKey($scalarKey)) {
                $merged["permissions"][$scalarKey] = $template["permissions"][$scalarKey]
            }
        }
    }

    # Compare with existing to detect changes
    $mergedJson = ($merged | ConvertTo-Json -Depth 10)
    $existingJson = ($existing | ConvertTo-Json -Depth 10)

    if ($existingJson -eq $mergedJson -and $existing.Count -gt 0) {
        [void]$Log.Add(@{ Status = "current"; Label = "~/.claude/settings.json" })
    } else {
        if ((Test-Path $ClaudeSettings) -and $existing.Count -gt 0) {
            $bak = Backup-File -FilePath $ClaudeSettings
            $mergedJson | Set-Content $ClaudeSettings -Encoding UTF8
            [void]$Log.Add(@{ Status = "updated"; Label = "~/.claude/settings.json (backed up -> $bak)" })
        } else {
            $mergedJson | Set-Content $ClaudeSettings -Encoding UTF8
            [void]$Log.Add(@{ Status = "installed"; Label = "~/.claude/settings.json" })
        }
    }

    # Install statusline script
    if (Test-Path $HomeStatusline) {
        Install-SmartFile -Src $HomeStatusline -Dest $ClaudeStatusline -Label "~/.claude/statusline.sh" -Log $Log
    }
}

$AutoReadPermissions = @{
    permissions = @{
        allow = @(
            "Read",
            "Glob",
            "Grep",
            "Bash(ls:*)",
            "Bash(git diff:*)",
            "Bash(git log:*)",
            "Bash(git status:*)"
        )
    }
}

function Install-AutoRead {
    param([string]$Cwd, [System.Collections.ArrayList]$Log)
    $settingsDir = Join-Path $Cwd ".claude"
    if (-not (Test-Path $settingsDir)) {
        New-Item -Path $settingsDir -ItemType Directory -Force | Out-Null
    }
    $settingsFile = Join-Path $settingsDir "settings.json"

    if (Test-Path $settingsFile) {
        try {
            $existing = Get-Content $settingsFile -Raw | ConvertFrom-Json
        } catch {
            $existing = @{}
        }
        if (-not $existing.permissions) {
            $existing | Add-Member -NotePropertyName "permissions" -NotePropertyValue @{ allow = @(); deny = @(); ask = @() }
        }
        if (-not $existing.permissions.allow) {
            $existing.permissions.allow = @()
        }
        $added = 0
        foreach ($tool in $AutoReadPermissions.permissions.allow) {
            if ($tool -notin $existing.permissions.allow) {
                $existing.permissions.allow += $tool
                $added++
            }
        }
        if ($added -gt 0) {
            $existing | ConvertTo-Json -Depth 10 | Set-Content $settingsFile -Encoding UTF8
            [void]$Log.Add(@{ Status = "installed"; Label = ".claude/settings.json (added $added permissions)" })
        } else {
            [void]$Log.Add(@{ Status = "current"; Label = ".claude/settings.json (permissions already present)" })
        }
    } else {
        $AutoReadPermissions | ConvertTo-Json -Depth 10 | Set-Content $settingsFile -Encoding UTF8
        [void]$Log.Add(@{ Status = "installed"; Label = ".claude/settings.json (auto-approve read)" })
    }
}

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║            AI Coding Standards                   ║" -ForegroundColor Cyan
    Write-Host "  ║  Standardized Claude Code configuration          ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-StatusBadge {
    param([string]$Status)
    switch ($Status) {
        "new"       { Write-Host "NEW" -ForegroundColor Cyan -NoNewline }
        "installed" { Write-Host "UP TO DATE" -ForegroundColor Green -NoNewline }
        "update"    { Write-Host "UPDATE" -ForegroundColor Yellow -NoNewline }
    }
}

function Write-Legend {
    Write-Host "  " -NoNewline
    Write-Host "NEW" -ForegroundColor Cyan -NoNewline
    Write-Host " = not yet installed   " -ForegroundColor DarkGray -NoNewline
    Write-Host "UP TO DATE" -ForegroundColor Green -NoNewline
    Write-Host " = current   " -ForegroundColor DarkGray -NoNewline
    Write-Host "UPDATE" -ForegroundColor Yellow -NoNewline
    Write-Host " = new version available" -ForegroundColor DarkGray
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Toggle list prompt
# ---------------------------------------------------------------------------

function Show-ToggleList {
    param(
        [string]$Title,
        [string]$Subtitle,
        [array]$Items,         # array of hashtables with Name, Heading, Status, Mandatory, Model
        [bool[]]$Selected,
        [bool]$ShowModel = $false
    )

    while ($true) {
        Clear-Host
        Write-Banner
        Write-Host "  $Title" -ForegroundColor White
        Write-Host "  $Subtitle" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  MANDATORY items cannot be deselected" -ForegroundColor Red
        Write-Legend
        Write-Host ""

        for ($i = 0; $i -lt $Items.Count; $i++) {
            $item = $Items[$i]
            $mark = $(if ($Selected[$i]) { "X" } else { " " })
            $num = $i + 1

            Write-Host "  [$mark] " -NoNewline
            Write-Host "$num. " -NoNewline -ForegroundColor White
            Write-Host "$($item.Heading) " -NoNewline -ForegroundColor White
            Write-Host "($($item.Name))" -NoNewline -ForegroundColor DarkGray

            if ($ShowModel -and $item.Model) {
                Write-Host " [$($item.Model)]" -NoNewline -ForegroundColor DarkYellow
            }

            if ($item.Mandatory) {
                Write-Host " [MANDATORY]" -NoNewline -ForegroundColor Red
            }

            Write-Host "  " -NoNewline
            Write-StatusBadge -Status $item.Status
            Write-Host ""
        }

        Write-Host ""
        Write-Host "  Toggle by number (e.g. " -ForegroundColor DarkGray -NoNewline
        Write-Host "1 3 4" -ForegroundColor White -NoNewline
        Write-Host "), Enter to continue: " -ForegroundColor DarkGray -NoNewline
        $userInput = Read-Host

        if ([string]::IsNullOrWhiteSpace($userInput)) {
            return $Selected
        }

        $nums = $userInput -split "\s+" | Where-Object { $_ -match "^\d+$" }
        foreach ($n in $nums) {
            $idx = [int]$n - 1
            if ($idx -ge 0 -and $idx -lt $Items.Count) {
                if ($Items[$idx].Mandatory -and $Selected[$idx]) {
                    Write-Host "  Cannot deselect mandatory item: $($Items[$idx].Heading)" -ForegroundColor Red
                    Start-Sleep -Milliseconds 800
                }
                else {
                    $Selected[$idx] = -not $Selected[$idx]
                }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Scope prompt
# ---------------------------------------------------------------------------

function Show-ScopeMenu {
    param([string]$Cwd, [bool]$InRepo, [string]$RepoName, [bool]$Fresh)

    Clear-Host
    Write-Banner

    Write-Host "  $Cwd" -ForegroundColor DarkGray
    if ($InRepo) {
        Write-Host "  (repo: $RepoName)" -ForegroundColor DarkGray
    }
    if (-not $Fresh) {
        Write-Host "  Existing installation detected - select items to add, update, or remove" -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "  Select install scope:" -ForegroundColor White
    Write-Host ""
    $repoNote = $(if ($InRepo) { "" } else { "  (no repo detected)" })
    Write-Host "    [1] Global  - CLAUDE.md + rules + agents to ~/.claude/" -ForegroundColor White
    Write-Host "    [2] Project - tasks + settings in current repo$repoNote" -ForegroundColor White
    Write-Host "    [3] Both    - global + project" -ForegroundColor White
    Write-Host ""
    Write-Host "  Choice [1]: " -ForegroundColor DarkGray -NoNewline
    $choice = Read-Host

    switch ($choice) {
        "2" { return "project" }
        "3" { return "both" }
        default { return "global" }
    }
}

# ---------------------------------------------------------------------------
# Model picker
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Options prompts
# ---------------------------------------------------------------------------

function Show-GlobalTasksPrompt {
    Write-Host ""
    Write-Host "  Create ~/.claude/tasks/ (lessons + todo)? [Y/n]: " -ForegroundColor White -NoNewline
    $answer = Read-Host
    return ($answer -ne "n" -and $answer -ne "N")
}

function Show-ProjectOptions {
    param([string]$RepoName, [bool]$InRepo)

    $createTasks = $true

    if (-not $InRepo) {
        Write-Host ""
        Write-Host "  Project install will be skipped - not in a git repo" -ForegroundColor Red
        return @{ CreateTasks = $false }
    }

    Write-Host ""
    Write-Host "  Project: $RepoName" -ForegroundColor White

    Write-Host ""
    Write-Host "  Create ./tasks/ (lessons + todo)? [Y/n]: " -ForegroundColor White -NoNewline
    $taskAnswer = Read-Host
    $createTasks = ($taskAnswer -ne "n" -and $taskAnswer -ne "N")

    Write-Host ""
    Write-Host "  Tip: Use /init inside Claude Code to generate a project CLAUDE.md" -ForegroundColor DarkGray

    return @{ CreateTasks = $createTasks }
}

# ---------------------------------------------------------------------------
# Install execution
# ---------------------------------------------------------------------------

function Invoke-Install {
    param(
        [string]$Scope,
        [array]$RuleInfo,
        [array]$AgentInfo,
        [bool[]]$SelectedRules,
        [bool[]]$SelectedAgents,
        [bool]$CreateGlobalTasks,
        [bool]$CreateProjectTasks,
        [bool]$EnableAutoRead = $false,
        [string]$Cwd,
        [bool]$InRepo
    )

    $log = [System.Collections.ArrayList]::new()

    # Snapshot existing files before making changes
    if ($Scope -eq "global" -or $Scope -eq "both") {
        $snap = New-Snapshot
        if ($snap) {
            [void]$log.Add(@{ Status = "snapshot"; Label = "Backed up to $snap" })
        }
    }

    if ($Scope -eq "global" -or $Scope -eq "both") {
        # CLAUDE.md
        Install-SmartFile -Src $HomeClaude -Dest $ClaudeMd -Label "~/.claude/CLAUDE.md" -Log $log

        # Rules
        if (-not (Test-Path $ClaudeRules)) { New-Item -Path $ClaudeRules -ItemType Directory -Force | Out-Null }
        for ($i = 0; $i -lt $RuleInfo.Count; $i++) {
            $item = $RuleInfo[$i]
            $dest = Join-Path $ClaudeRules $item.Name
            if ($SelectedRules[$i]) {
                Install-SmartFile -Src $item.Src -Dest $dest -Label "~/.claude/rules/$($item.Name)" -Log $log
            }
            else {
                Remove-WithLog -Dest $dest -Label "~/.claude/rules/$($item.Name)" -Log $log
            }
        }

        # Agents
        if (-not (Test-Path $ClaudeAgents)) { New-Item -Path $ClaudeAgents -ItemType Directory -Force | Out-Null }
        for ($i = 0; $i -lt $AgentInfo.Count; $i++) {
            $item = $AgentInfo[$i]
            $dest = Join-Path $ClaudeAgents $item.Name
            if ($SelectedAgents[$i]) {
                Install-SmartFile -Src $item.Src -Dest $dest -Label "~/.claude/agents/$($item.Name)" -Log $log
            }
            else {
                Remove-WithLog -Dest $dest -Label "~/.claude/agents/$($item.Name)" -Log $log
            }
        }

        # Tasks
        if ($CreateGlobalTasks) {
            $globalTasksDir = Join-Path $ClaudeHome "tasks"
            if (-not (Test-Path $globalTasksDir)) { New-Item -Path $globalTasksDir -ItemType Directory -Force | Out-Null }
            foreach ($tpl in @("lessons.md", "todo.md")) {
                $src = Join-Path $TasksDir $tpl
                $dest = Join-Path $globalTasksDir $tpl
                if ((Test-Path $dest) -and (Test-HasContent -FilePath $dest)) {
                    [void]$log.Add(@{ Status = "skipped"; Label = "~/.claude/tasks/$tpl (has content)" })
                }
                else {
                    Copy-Item -Path $src -Destination $dest -Force
                    [void]$log.Add(@{ Status = "installed"; Label = "~/.claude/tasks/$tpl" })
                }
            }
        }

        # Global settings.json (permissions)
        Install-GlobalSettings -Log $log
    }

    if ($Scope -eq "project" -or $Scope -eq "both") {
        if ($InRepo) {
            if ($CreateProjectTasks) {
                $projTasksDir = Join-Path $Cwd "tasks"
                if (-not (Test-Path $projTasksDir)) { New-Item -Path $projTasksDir -ItemType Directory -Force | Out-Null }
                foreach ($tpl in @("lessons.md", "todo.md")) {
                    $src = Join-Path $TasksDir $tpl
                    $dest = Join-Path $projTasksDir $tpl
                    if ((Test-Path $dest) -and (Test-HasContent -FilePath $dest)) {
                        [void]$log.Add(@{ Status = "skipped"; Label = "tasks/$tpl (has content)" })
                    }
                    else {
                        Copy-Item -Path $src -Destination $dest -Force
                        [void]$log.Add(@{ Status = "installed"; Label = "tasks/$tpl" })
                    }
                }
            }

            if ($EnableAutoRead) {
                Install-AutoRead -Cwd $Cwd -Log $log
            }
        }
        else {
            [void]$log.Add(@{ Status = "skipped"; Label = "Project install (not in a git repo)" })
        }
    }

    return $log
}

# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------

function Show-Results {
    param([System.Collections.ArrayList]$Log, [string]$Scope, [bool]$InRepo, [string]$Cwd)

    Clear-Host
    Write-Banner
    Write-Host "  Installation Complete" -ForegroundColor Green
    Write-Host ""

    $counts = @{ installed = 0; updated = 0; removed = 0; current = 0; skipped = 0; snapshot = 0; restored = 0; warning = 0 }
    foreach ($entry in $Log) {
        if ($counts.ContainsKey($entry.Status)) { $counts[$entry.Status]++ }
        switch ($entry.Status) {
            "installed" { Write-Host "  +  INSTALLED  $($entry.Label)" -ForegroundColor Green }
            "updated"   { Write-Host "  ~  UPDATED    $($entry.Label)" -ForegroundColor Yellow }
            "removed"   { Write-Host "  -  REMOVED    $($entry.Label)" -ForegroundColor Red }
            "current"   { Write-Host "  =  CURRENT    $($entry.Label)" -ForegroundColor DarkGray }
            "skipped"   { Write-Host "  .  SKIPPED    $($entry.Label)" -ForegroundColor DarkGray }
            "snapshot"  { Write-Host "  *  SNAPSHOT   $($entry.Label)" -ForegroundColor Cyan }
            "restored"  { Write-Host "  <  RESTORED   $($entry.Label)" -ForegroundColor Green }
            "warning"   { Write-Host "  !  WARNING    $($entry.Label)" -ForegroundColor Yellow }
        }
    }

    Write-Host ""
    $parts = @()
    if ($counts.installed -gt 0) { $parts += "$($counts.installed) installed" }
    if ($counts.updated -gt 0) { $parts += "$($counts.updated) updated" }
    if ($counts.removed -gt 0) { $parts += "$($counts.removed) removed" }
    if ($counts.current -gt 0) { $parts += "$($counts.current) unchanged" }
    if ($counts.skipped -gt 0) { $parts += "$($counts.skipped) skipped" }
    if ($counts.warning -gt 0) { $parts += "$($counts.warning) warnings" }
    if ($parts.Count -gt 0) {
        Write-Host "  Summary: $($parts -join ' | ')" -ForegroundColor White
    }

    Write-Host ""
    if ($Scope -eq "global" -or $Scope -eq "both") {
        Write-Host "  CLAUDE.md   $ClaudeMd" -ForegroundColor DarkGray
        Write-Host "  Rules       $ClaudeRules" -ForegroundColor DarkGray
        Write-Host "  Agents      $ClaudeAgents" -ForegroundColor DarkGray
    }
    if (($Scope -eq "project" -or $Scope -eq "both") -and $InRepo) {
        Write-Host "  Project     $Cwd" -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "  Re-run this script anytime to add, update, or remove items." -ForegroundColor DarkGray
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Non-interactive CLI
# ---------------------------------------------------------------------------

function Invoke-Update {
    Write-Host "Updating standards from git..." -ForegroundColor White
    $result = & git -C "$ScriptDir" pull 2>&1
    if ($LASTEXITCODE -eq 0) {
        if ($result -match "Already up to date") {
            Write-Host "  Already up to date." -ForegroundColor DarkGray
        } else {
            Write-Host "  Updated: $result" -ForegroundColor Green
        }
    } else {
        Write-Host "  Error: $result" -ForegroundColor Red
    }
}

function Invoke-Cli {
    param(
        [string]$Scope,
        [bool]$SkipTasks,
        [bool]$EnableAutoRead = $false
    )

    $cwd = (Get-Location).Path
    $inRepo = Test-GitRepo -Path $cwd

    # Discover source files and build info
    $rules = @(Get-MdFiles -Directory $HomeRulesDir)
    $agents = @(Get-MdFiles -Directory $AgentsDir)
    $ruleInfo = @(Build-FileInfo -SourceFiles $rules -InstallDir $ClaudeRules -Mandatory $MandatoryRules)
    $agentInfo = @(Build-FileInfo -SourceFiles $agents -InstallDir $ClaudeAgents -Mandatory $MandatoryAgents)

    # Non-interactive: select everything
    $selectedRules = [bool[]]::new($ruleInfo.Count)
    for ($i = 0; $i -lt $ruleInfo.Count; $i++) { $selectedRules[$i] = $true }
    $selectedAgents = [bool[]]::new($agentInfo.Count)
    for ($i = 0; $i -lt $agentInfo.Count; $i++) { $selectedAgents[$i] = $true }

    $createGlobalTasks = -not $SkipTasks
    $createProjectTasks = -not $SkipTasks

    $log = Invoke-Install `
        -Scope $Scope `
        -RuleInfo $ruleInfo `
        -AgentInfo $agentInfo `
        -SelectedRules $selectedRules `
        -SelectedAgents $selectedAgents `
        -CreateGlobalTasks $createGlobalTasks `
        -CreateProjectTasks $createProjectTasks `
        -EnableAutoRead $EnableAutoRead `
        -Cwd $cwd `
        -InRepo $inRepo

    Show-Results -Log $log -Scope $Scope -InRepo $inRepo -Cwd $cwd
}

# ---------------------------------------------------------------------------
# Main (interactive)
# ---------------------------------------------------------------------------

function Main-Interactive {
    $cwd = (Get-Location).Path
    $inRepo = Test-GitRepo -Path $cwd
    $repoName = $(if ($inRepo) { Get-RepoName -Path $cwd } else { "" })
    $fresh = Test-FreshInstall

    # Discover source files
    $rules = @(Get-MdFiles -Directory $HomeRulesDir)
    $agents = @(Get-MdFiles -Directory $AgentsDir)

    # Build file info with status
    $ruleInfo = @(Build-FileInfo -SourceFiles $rules -InstallDir $ClaudeRules -Mandatory $MandatoryRules)
    $agentInfo = @(Build-FileInfo -SourceFiles $agents -InstallDir $ClaudeAgents -Mandatory $MandatoryAgents)

    # Pre-select: fresh = all selected, re-install = installed/update + mandatory
    $selectedRules = [bool[]]::new($ruleInfo.Count)
    for ($i = 0; $i -lt $ruleInfo.Count; $i++) {
        $selectedRules[$i] = $fresh -or $ruleInfo[$i].Status -ne "new" -or $ruleInfo[$i].Mandatory
    }
    $selectedAgents = [bool[]]::new($agentInfo.Count)
    for ($i = 0; $i -lt $agentInfo.Count; $i++) {
        $selectedAgents[$i] = $fresh -or $agentInfo[$i].Status -ne "new" -or $agentInfo[$i].Mandatory
    }

    # --- Flow ---

    # 1. Scope
    $scope = Show-ScopeMenu -Cwd $cwd -InRepo $inRepo -RepoName $repoName -Fresh $fresh

    # 2. Rules (global/both only)
    if ($scope -eq "global" -or $scope -eq "both") {
        $selectedRules = Show-ToggleList `
            -Title "Select Rules" `
            -Subtitle "Auto-loaded from ~/.claude/rules/ every session" `
            -Items $ruleInfo `
            -Selected $selectedRules `
            -ShowModel $false
    }

    # 3. Agents (global/both only)
    if ($scope -eq "global" -or $scope -eq "both") {
        $selectedAgents = Show-ToggleList `
            -Title "Select Agents" `
            -Subtitle "Invoked via /agent-name in Claude Code" `
            -Items $agentInfo `
            -Selected $selectedAgents `
            -ShowModel $true
    }

    # 4. Options
    Clear-Host
    Write-Banner
    Write-Host "  Options" -ForegroundColor White
    Write-Host "  Final settings before installation" -ForegroundColor DarkGray
    Write-Host ""

    $createGlobalTasks = $false
    $createProjectTasks = $false

    if ($scope -eq "global" -or $scope -eq "both") {
        $createGlobalTasks = Show-GlobalTasksPrompt
    }

    if ($scope -eq "project" -or $scope -eq "both") {
        $projectOpts = Show-ProjectOptions -RepoName $repoName -InRepo $inRepo
        $createProjectTasks = $projectOpts.CreateTasks
    }

    # 5. Install
    Write-Host ""
    Write-Host "  Installing..." -ForegroundColor White

    $log = Invoke-Install `
        -Scope $scope `
        -RuleInfo $ruleInfo `
        -AgentInfo $agentInfo `
        -SelectedRules $selectedRules `
        -SelectedAgents $selectedAgents `
        -CreateGlobalTasks $createGlobalTasks `
        -CreateProjectTasks $createProjectTasks `
        -Cwd $cwd `
        -InRepo $inRepo

    # 6. Results
    Show-Results -Log $log -Scope $scope -InRepo $inRepo -Cwd $cwd
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

function Invoke-RestoreCli {
    param([string]$Timestamp)

    $snapshots = @(Get-Snapshots)
    if ($snapshots.Count -eq 0) {
        Write-Host "  No backups found in ~/.claude/backups/" -ForegroundColor DarkGray
        return
    }

    $snapDir = $null
    if ($Timestamp) {
        foreach ($s in $snapshots) {
            if ($s.Name -eq $Timestamp) {
                $snapDir = $s.Path
                break
            }
        }
        if (-not $snapDir) {
            Write-Host "  Snapshot '$Timestamp' not found. Available:" -ForegroundColor Red
            foreach ($s in $snapshots) {
                $count = (Get-ChildItem -Path $s.Path -File -Recurse).Count
                Write-Host "    $($s.Name)  ($count files)" -ForegroundColor DarkGray
            }
            return
        }
    } else {
        $snapDir = $snapshots[0].Path
    }

    $snapName = Split-Path $snapDir -Leaf
    Write-Host "  Restoring from $snapName..." -ForegroundColor White
    $log = Invoke-Restore -SnapDir $snapDir

    foreach ($entry in $log) {
        switch ($entry.Status) {
            "restored" { Write-Host "  <  RESTORED   $($entry.Label)" -ForegroundColor Green }
            "current"  { Write-Host "  =  CURRENT    $($entry.Label)" -ForegroundColor DarkGray }
        }
    }

    $restored = ($log | Where-Object { $_.Status -eq "restored" }).Count
    $current = ($log | Where-Object { $_.Status -eq "current" }).Count
    $parts = @()
    if ($restored -gt 0) { $parts += "$restored restored" }
    if ($current -gt 0) { $parts += "$current unchanged" }
    if ($parts.Count -gt 0) {
        Write-Host ""
        Write-Host "  $($parts -join ' | ')" -ForegroundColor White
    }
    Write-Host ""
}

# ---------------------------------------------------------------------------
# CLI uninstall
# ---------------------------------------------------------------------------

function Invoke-Uninstall {
    if (-not (Test-Path $ClaudeHome)) {
        Write-Host "  Nothing to uninstall — ~/.claude/ does not exist." -ForegroundColor DarkGray
        return
    }

    # Snapshot before removing
    $snap = New-Snapshot
    if ($snap) {
        Write-Host "  SNAPSHOT   Backed up to $snap" -ForegroundColor Cyan
    }

    $removed = 0

    # Remove CLAUDE.md
    $cm = Join-Path $ClaudeHome "CLAUDE.md"
    if (Test-Path $cm) {
        Remove-Item $cm -Force
        Write-Host "  -  REMOVED    ~/.claude/CLAUDE.md" -ForegroundColor Red
        $removed++
    }

    # Remove managed directories
    foreach ($dirname in @("rules", "agents", "tasks")) {
        $d = Join-Path $ClaudeHome $dirname
        if (Test-Path $d) {
            $count = (Get-ChildItem -Path $d -File -ErrorAction SilentlyContinue).Count
            Remove-Item $d -Recurse -Force
            Write-Host "  -  REMOVED    ~/.claude/$dirname/ ($count files)" -ForegroundColor Red
            $removed++
        }
    }

    if ($removed -gt 0) {
        Write-Host ""
        Write-Host "  Uninstalled. Backup saved to $snap" -ForegroundColor White
        Write-Host "  To undo: .\install.ps1 -Restore" -ForegroundColor DarkGray
    } else {
        Write-Host "  Nothing to remove — no managed files found." -ForegroundColor DarkGray
    }
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Mutual exclusivity check
$scopeCount = [int]$Global.IsPresent + [int]$Project.IsPresent + [int]$Both.IsPresent + [int]$Restore.IsPresent + [int]$Uninstall.IsPresent
if ($scopeCount -gt 1) {
    Write-Host "  Error: -Global, -Project, -Both, -Restore, and -Uninstall are mutually exclusive." -ForegroundColor Red
    exit 1
}

if ($Update) {
    Invoke-Update
}

if ($Uninstall) {
    Invoke-Uninstall
} elseif ($Restore) {
    Invoke-RestoreCli -Timestamp $RestoreTimestamp
} elseif ($Both) {
    Invoke-Cli -Scope "both" -SkipTasks $NoTasks -EnableAutoRead $AutoRead
} elseif ($Global) {
    Invoke-Cli -Scope "global" -SkipTasks $NoTasks
} elseif ($Project) {
    Invoke-Cli -Scope "project" -SkipTasks $NoTasks -EnableAutoRead $AutoRead
} elseif (-not $Update) {
    Main-Interactive
} else {
    Write-Host "  Updated. Use -Global, -Project, or -Both to also install." -ForegroundColor DarkGray
}
