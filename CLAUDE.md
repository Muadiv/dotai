# [Project Name]

<!-- This project-level CLAUDE.md extends the global standards installed at ~/.claude/CLAUDE.md.
     Global rules (security, safety, behavior) apply automatically. This file adds project-specific context. -->

## WHAT — Tech Stack & Structure

> Identify specific versions to prevent the model from assuming legacy patterns.

- **Framework**: [e.g., React 19, Next.js 15 App Router, Django 5.1]
- **Language**: [e.g., TypeScript 5.x, Python 3.12]
- **Database**: [e.g., PostgreSQL 16, DynamoDB]
- **Infrastructure**: [e.g., Terraform, AWS CDK, Azure Bicep]
- **CI/CD**: [e.g., GitHub Actions, Jenkins, Azure DevOps]

### Directory Map

<!-- Provide a brief folder structure for key directories. Example: -->
<!--
```
src/
├── api/          # REST API endpoints
├── core/         # Business logic
├── models/       # Database models
├── services/     # External service integrations
└── utils/        # Shared utilities
```
-->

## WHY — Architecture & Rationale

> Explain why certain patterns are used so the agent can apply better judgment in ambiguous cases.

<!-- Example entries: -->
<!-- - Named exports everywhere: improves tree-shaking and makes imports grep-able -->
<!-- - Repository pattern for DB access: decouples business logic from ORM specifics -->

### Gotchas

<!-- Non-obvious workarounds, special headers, weird retry logic, etc. -->
<!-- - The /auth endpoint requires a custom X-Tenant-ID header -->
<!-- - Rate limiter resets at midnight UTC, not per-window -->

## HOW — Operational Commands

> Verified commands the agent should use. Specify working directory if not repo root.

### Build

```bash
# [build command]
```

### Test

```bash
# [test command]
# Specify: unit tests, integration tests, e2e — and how to run each
```

### Lint

```bash
# [lint command]
```

### Verification

After making changes, the agent MUST:
1. [Run the relevant test suite]
2. [Check for lint/type errors]
3. [Verify the change works as expected — how?]

## Security Notes

<!-- Check all that apply to this project. This helps the AI assistant apply appropriate caution. -->

- [ ] This project processes PHI/PII
- [ ] This project has validated system components
- [ ] This project interfaces with critical infrastructure

<!-- Add project-specific security rules below if needed -->
