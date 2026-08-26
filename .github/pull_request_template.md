<!--
Complete every section that applies and remove all placeholder text. Use
"None" or "Not applicable" with a short reason where needed. Keep the
description concise, but give reviewers enough human context to understand why
the change exists and why this approach was chosen. Do not include secrets or
sensitive data. Only mark a checklist item complete when it has been verified.
-->

## Linked work

<!--
Vrax implementation PRs normally track issues in Procuratio. Use the full
cross-repository reference so the correct ticket closes when this PR merges.
Replace "ISSUE_NUMBER", or replace "Closes" with "Related to" when the PR does
not fully resolve the ticket.
-->

Closes arachne-threat-intel/Procuratio#ISSUE_NUMBER

Related issues, pull requests, specifications, or design documents:

## What changed

<!-- Summarize the change in one to three sentences or short bullets. Do not repeat the file list or diff. -->

- 

## Why

<!-- Explain the problem, user or business outcome, and why this approach was chosen. Include enough context that the reviewer does not need to reconstruct the rationale from the issue or code. -->


## Impact and dependencies

<!-- Identify affected users, workflows, components, APIs, data, configuration, or other repositories. List dependent or prerequisite PRs. State "None" where applicable. -->

- Who or what is affected:
- Dependencies or related changes:
- Compatibility, migration, rollout, or rollback considerations:

## Implementation notes

<!-- Explain only non-obvious design decisions, constraints, trade-offs, or deviations from established patterns. Explicitly identify anything deliberately unchanged or out of scope. Use "None" if the implementation is straightforward. -->


## Verification

<!--
Report each relevant check as PASS, FAIL, or NOT RUN. Include the exact command
and meaningful result. Explain FAIL and NOT RUN outcomes. Do not call a failure
"pre-existing" without evidence from main, an established baseline, or the
failure mechanism. Never imply that a check passed if it was not run.
-->

- Automated tests:
- Manual checks:
- Lint, formatting, and static checks:

## Evidence

<!-- For UI, user-visible, document, report, or other behavioural changes, attach useful before/after screenshots, a GIF, short video, or sample output. Otherwise state why evidence is not applicable. -->


## Security and privacy

<!-- Provide a proportionate review of the actual diff. State "No material impact" or explain relevant authentication, authorization, input validation, sensitive-data, secrets, logging, dependency, or abuse-case considerations and residual concerns. Do not paste sensitive values. -->


## Documentation

<!-- List documentation updated in this PR. If no update is needed, explain why. Include cross-repository documentation or interface implications. Documentation should not be silently deferred. -->


## Breaking changes and rollout

- [ ] No breaking change
- [ ] Breaking change — describe affected consumers and compatibility or migration steps below

Rollout and rollback considerations:

## Reviewer focus

<!-- Flag the areas that deserve the closest attention, specific questions, uncertainties, known limitations, or decisions you want challenged. Use "None" if there are no special considerations. -->


## Author checklist

- [ ] This PR is one focused, self-contained change and excludes unrelated cleanup or refactoring.
- [ ] If the PR is unusually large or combines several concerns, I explained why it could not be split into independently reviewable changes.
- [ ] Tests were added or updated where appropriate, and PASS, FAIL, and NOT RUN results above are accurate.
- [ ] Relevant documentation was updated, or the reason no update is required is recorded above.
- [ ] The commit sequence is logical and reviewable.
- [ ] No production credentials, production data, production configuration, or deployment systems were used for verification.
- [ ] The description reflects the final change and contains no secrets or sensitive data.
