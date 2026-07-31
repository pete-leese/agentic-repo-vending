# Terraform repository template

Boilerplate for Terraform modules and root projects. Vended by [agentic-repo-vending](https://github.com/pete-leese/agentic-repo-vending).

## Layout

- `modules/example` — sample module skeleton
- `.github/workflows/terraform.yml` — fmt, validate, tflint
- `.pre-commit-config.yaml` — local guardrails

## Usage

This repo is a **GitHub template**. New repos are created from it by the vend workflow.

## Guardrails

After vend, `main` is branch-protected (PR required; no direct pushes).
