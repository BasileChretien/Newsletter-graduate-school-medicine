<!--
Thanks for opening a PR! See CONTRIBUTING.md for the review-axis
checklist that this template mirrors. Skip the bullets that don't
apply, but please don't delete the headings — they help the
maintainer triage.
-->

## What this PR changes

A one-paragraph summary of the change and why it's worth merging.

## Review-axis answers

- **Architect:** does this introduce a new module / dependency / public
  API? Why?
- **Python:** any new public function? Type-annotated? Tests added?
- **Security:** any new user-input boundary? How is it validated?
- **Visual:** before/after screenshot if this changes rendered output.
- **UX:** what does the editor see in their CLI / launcher / READMEs?
- **Email deliverability:** does this change MIME structure, plaintext
  alternative, or inlined CSS? Tested in which clients?

## Tests

- [ ] New regression test(s) for the bug / feature.
- [ ] `python -m pytest` passes locally.
- [ ] Smoke build passes: `python build_newsletter.py build-template`.

## Related issues / discussions

Closes #...
