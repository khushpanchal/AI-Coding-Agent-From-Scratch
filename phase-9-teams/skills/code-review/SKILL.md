---
name: code-review
description: Review code for quality, bugs, security issues, and best practices.
---

# Code Review Skill

When reviewing code, follow this structured approach:

## Review Checklist

1. **Correctness** — Does the code do what it claims? Are there edge cases?
2. **Security** — SQL injection, XSS, command injection, path traversal, hardcoded secrets?
3. **Performance** — N+1 queries, unnecessary allocations, missing indexes?
4. **Readability** — Clear naming, reasonable function length, comments where needed?
5. **Error Handling** — Are errors caught and handled appropriately?
6. **Testing** — Are there tests? Do they cover the important paths?

## Output Format

For each issue found:
- **File:Line** — Location
- **Severity** — Critical / Warning / Suggestion
- **Issue** — What's wrong
- **Fix** — How to fix it

End with a summary: total issues by severity, overall assessment.

## Guidelines

- Be specific — point to exact lines, not vague areas
- Suggest fixes, don't just complain
- Acknowledge good patterns when you see them
- Focus on substance over style (don't nitpick formatting)
- Flag security issues as critical, always
