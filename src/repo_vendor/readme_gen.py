"""Generate / render the README written into a freshly vended repo."""

from __future__ import annotations

_PLACEHOLDER_KEYS = (
    "REPO_NAME",
    "SUMMARY",
    "DESCRIPTION",
    "ISSUE_KEY",
    "REPO_URL",
    "TEMPLATE",
)


def _description_text(summary: str, description: str) -> str:
    desc = (description or summary or "").strip()
    if len(desc) > 500:
        desc = desc[:497] + "..."
    return desc or summary or "Vended repository."


def render_template_readme(
    template_text: str,
    *,
    repo_name: str,
    summary: str,
    description: str,
    issue_key: str,
    template: str,
    repo_url: str,
) -> str:
    """Substitute ``{{PLACEHOLDER}}`` tokens; leave terraform-docs markers intact."""
    values = {
        "REPO_NAME": repo_name,
        "SUMMARY": summary or "(none)",
        "DESCRIPTION": _description_text(summary, description),
        "ISSUE_KEY": issue_key,
        "REPO_URL": repo_url,
        "TEMPLATE": template,
    }
    out = template_text
    for key, value in values.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def has_readme_placeholders(text: str) -> bool:
    return any(f"{{{{{key}}}}}" in text for key in _PLACEHOLDER_KEYS)


def build_vended_readme(
    *,
    repo_name: str,
    summary: str,
    description: str,
    issue_key: str,
    template: str,
    repo_url: str,
) -> str:
    """Legacy full rewrite for old templates without placeholders."""
    about = _description_text(summary, description)
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


def resolve_vended_readme(
    template_readme: str | None,
    *,
    repo_name: str,
    summary: str,
    description: str,
    issue_key: str,
    template: str,
    repo_url: str,
) -> str:
    """Prefer placeholder substitution when the template README supports it."""
    if template_readme and has_readme_placeholders(template_readme):
        return render_template_readme(
            template_readme,
            repo_name=repo_name,
            summary=summary,
            description=description,
            issue_key=issue_key,
            template=template,
            repo_url=repo_url,
        )
    return build_vended_readme(
        repo_name=repo_name,
        summary=summary,
        description=description,
        issue_key=issue_key,
        template=template,
        repo_url=repo_url,
    )
