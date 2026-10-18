# Contributing

Thanks for helping improve RepairDesk Local. Bug reports, documentation fixes, and focused pull requests are welcome.

## Before opening an issue or pull request

- Search existing issues and pull requests to avoid duplicates.
- For a bug report, include the Python version, operating system, steps to reproduce, and a sanitized error message.
- Never attach a real repair database, customer record, screenshot, model output, `.env` file, or secret. Reproduce problems with the fictional sample jobs instead.
- For larger behavior or architecture changes, open an issue first so the scope can be discussed.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
```

On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

Keep changes focused, add or update tests for behavior changes, and update the README when setup, configuration, privacy, or user-visible behavior changes. Tests must use temporary databases and must not require Ollama or network access.

## Pull request checklist

- [ ] Tests pass with `python -m pytest`.
- [ ] No real customer data, local database, model file, credential, or `.env` file is included.
- [ ] User-facing text is clear about unconfirmed AI output and human review where applicable.
- [ ] Documentation reflects any changes to installation, configuration, or workflow.

By submitting a contribution, you agree that it may be distributed under the project's MIT License.
