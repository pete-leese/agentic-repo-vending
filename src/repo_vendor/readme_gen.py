"""Generate the README written into a freshly vended repo."""

from __future__ import annotations


def build_vended_readme(
    *,
    repo_name: str,
    summary: str,
    description: str,
    issue_key: str,
    template: str,
    repo_url: str,
) -> str:
    """Project-facing README (not the template boilerplate)."""
    desc = (description or summary or "").strip()
    if len(desc) > 500:
        desc = desc[:497] + "..."
    about = desc or summary or "Vended repository."
    return "\n".join(
        [
            f"# {repo_name}",
            "",
            about,
            "",
            "## Origin",
            "",
            f"- **Jira:** `{issue_key}`",
            f"- **Summary:** {summary or '(none)'}",
            f"- **Created from template:** `{template}`",
            f"- **Repository:** {repo_url}",
            "",
            "## Getting started",
            "",
            "Replace this section with setup and usage notes for the project.",
            "",
            "## Contributing",
            "",
            "Direct pushes to `main` should be blocked — open a pull request.",
            "",
        ]
    )
