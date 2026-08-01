# Pull requests

- CI (`.github/workflows/ci.yml`) must pass: ruff, mypy critical path, pytest + coverage.
- Prefer small PRs; Spec Request changes under `requests/` should include the Jira key in the title.
- For control-plane changes touching `workflow.py` / `naming.py` / approval, request a second pass (human or Bugbot) — reviewer should not be the same model family that authored the change when using agent review.
- Never include secrets, `.env`, or live webhook credentials.
- Template sync: if you change `templates/`, note whether `scripts/sync_template_repos.sh` was run.
