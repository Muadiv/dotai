# Security Standards

> IMPORTANT: These rules are MANDATORY. They apply to ALL interactions, ALL projects, ALL code.

## Secrets & Credentials

- NEVER include API keys, passwords, tokens, connection strings, or certificates in code, comments, prompts, or commit messages
- NEVER hardcode credentials — use environment variables, secret vaults (e.g., Azure Key Vault, AWS Secrets Manager), or configuration references
- Flag any file that matches secret patterns: `.env`, `credentials.json`, `*_key.*`, `*.pem`, `*.p12`, `secrets.*`, `*token*`
- Before committing: warn if any staged file may contain secrets
- If you accidentally see a secret in code, immediately flag it and recommend rotation

## Code Security

- Flag security-sensitive changes: authentication flows, cryptographic operations, network calls, database queries, file system access, permission/role changes
- Call out OWASP Top 10 risks when spotted — especially injection, broken auth, sensitive data exposure, and security misconfiguration
- NEVER introduce `eval()`, `exec()`, `Function()`, dynamic SQL, or shell injection vectors without explicit user approval
- Sanitize all user inputs at system boundaries — never trust external data
- Use parameterized queries for all database operations
- Prefer allowlists over denylists for input validation

## Data Privacy

- NEVER include Protected Health Information (PHI) or Personally Identifiable Information (PII) in code, logs, comments, or AI prompts
- Flag code that logs, stores, or transmits user data without explicit consent mechanisms
- Warn when error messages or stack traces might expose sensitive information
- Recommend data minimization — only collect and process what's necessary

## Audit Trails

- Preserve audit trails — NEVER silently delete, overwrite, or modify logs, records, or versioned data
- Flag changes to validated systems or regulated code paths
- When in doubt about compliance impact, STOP and ask before proceeding
