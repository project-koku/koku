## Purpose

Draft PR testing instructions using the standard Koku template. Follow the format below and keep it concise and actionable.

## When to Use

Use this command when preparing a PR description or a `pr-testing.md` file. If a Jira ticket exists, link it. If not, mark it as `None`.

## Output Template

Use this exact structure and headings. **Deliver the completed text inside one `markdown` fenced code block** so the user can copy it into the PR in one step.

````
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
````

**Copy-paste:** Wrap the filled-in sections in a single outer ` ```markdown ` … ` ``` ` block for one-step copy. In **Testing**, use normal fenced snippets (` ```bash `, ` ```shell `, etc.) for commands, `curl`, and tox. GitHub PR descriptions render these correctly when pasted.

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
