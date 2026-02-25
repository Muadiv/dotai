# Coding Standards

## No Over-Engineering

- Only make changes that are directly requested or clearly necessary
- Don't add features, refactor code, or make "improvements" beyond what was asked
- A bug fix doesn't need surrounding code cleaned up
- A simple feature doesn't need extra configurability
- Don't add docstrings, comments, or type annotations to code you didn't change

## Minimal Abstractions

- Don't create helpers, utilities, or abstractions for one-time operations
- Don't design for hypothetical future requirements
- Three similar lines of code is better than a premature abstraction
- If unused, delete it — no backwards-compatibility shims or `_unused` variables

## Error Handling

- Only add error handling at system boundaries (user input, external APIs, file I/O)
- Trust internal code and framework guarantees
- Don't add fallbacks for scenarios that can't happen

## Code Quality

- Read and understand existing code before suggesting modifications
- Match the existing code style and patterns in the project
- Keep solutions simple and focused on the problem at hand
