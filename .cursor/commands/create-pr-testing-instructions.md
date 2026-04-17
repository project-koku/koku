## Purpose

Draft PR testing instructions using the standard Koku template. Follow the format below and keep it concise and actionable.

## When to Use

Use this command when preparing a PR description or a `pr-testing.md` file. If a Jira ticket exists, link it. If not, mark it as `None`.

## Output Template

Use this exact structure and headings:

```
## Jira Ticket

[COST-####](https://issues.redhat.com/browse/COST-####)

## Description

This change will ...

## Testing

1. Checkout branch.
2. Restart Koku.
3. Hit endpoint or launch shell.
    1. You should see ...
4. Do more things...

## Release Notes
- [ ] proposed release note

```markdown
* [COST-####](https://issues.redhat.com/browse/COST-####) Fix some things
```
```

## Jira Optional Handling

If there is no Jira ticket, keep the section but use `None`:

```
## Jira Ticket

None
```

## Guidance

- Be specific about endpoints, identities, env vars, and expected responses.
- Include any setup or feature flag requirements (for example, `.env` values).
- For APIs, provide a `curl` example and the expected status or message.
- Keep steps minimal but complete for someone else to verify the change.
- Ensure the release note matches the change and is formatted as shown.
