# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bugwarrior is a command-line utility that synchronizes issues from various issue trackers (GitHub, GitLab, Jira, etc.) with Taskwarrior. It's written in Python and supports 20+ different services.

**Python version:** Requires >3.9, <4

## Development Commands

### Installation

**Primary (UV - recommended):**

```bash
# Install with all dependencies
uv sync --all-extras

# Install with specific service dependencies
uv sync --extra jira --extra github --extra gitlab

# Install test dependencies only
uv sync --extra test

# Install locally as a tool
uv tool install -e .
```

**Alternative (pip):**

```bash
# Install with all dependencies
pip install -e .[all]

# Install with specific service dependencies
pip install -e .[jira,github,gitlab]
```

### Testing

```bash
# Run tests with coverage
uv run pytest --cov=bugwarrior --cov-branch tests

# Run tests for a specific service
uv run pytest tests/test_github.py

# Run a specific test
uv run pytest tests/test_github.py::TestGithubService::test_issues

# Without UV
pytest --cov=bugwarrior --cov-branch tests
```

**Test Patterns:**

- All service tests inherit from `AbstractServiceTest` and `ServiceTest` base classes
- Use `responses` library for mocking HTTP requests (`@responses.activate` decorator)
- Use `TaskConstructor` utility to verify final taskwarrior record format
- Configuration tests inherit from `ConfigTest` for temp directory setup

### Linting

```bash
# Check for issues (with UV)
uv run ruff check .

# Auto-fix issues
uv run ruff check . --fix

# Format code
uv run ruff format .

# Without UV
ruff check .
ruff format .
```

**Note:** Max line length is 100 characters. Ruff has replaced flake8 in this project.

## Architecture

### Core Components

1. **Service Architecture** (`bugwarrior/services/`)

   - Each service inherits from `IssueService` base class
   - Services implement `issues()` generator and `Issue` subclass
   - UDAs (User Defined Attributes) are defined per service
   - Services use Pydantic for configuration validation

2. **Configuration System** (`bugwarrior/config/`)

   - Uses Pydantic models for schema validation
   - Supports TOML and legacy INI formats
   - Secrets can be stored in keyring or environment variables
   - Configuration loading happens through `load_config()`
   - **Configuration file discovery order:**
     1. `$BUGWARRIORRC` environment variable
     2. `$XDG_CONFIG_HOME/bugwarrior/bugwarrior.toml`
     3. `$XDG_CONFIG_HOME/bugwarrior/bugwarriorrc`
     4. `~/.bugwarrior.toml`
     5. `~/.bugwarriorrc`

3. **Issue Synchronization** (`bugwarrior/db.py`)

   - `synchronize()` handles the main sync logic
   - Issues are uniquely identified by service-specific keys
   - Supports bidirectional sync for some services

4. **Command Structure** (`bugwarrior/command.py`)
   - Main commands: `pull`, `vault`, `uda`
   - Uses Click for CLI handling
   - Supports dry-run mode and flavors

### Service Implementation Pattern

When implementing a new service:

1. Create service class inheriting from `IssueService`
2. Define Issue class with required UDAs
3. Implement `issues()` generator method
4. Add configuration schema using Pydantic
5. Register service in `pyproject.toml` entry points:
   ```toml
   [project.entry-points."bugwarrior.service"]
   github = "bugwarrior.services.github:GithubService"
   ```
6. The `get_service()` function in `collect.py` dynamically loads services from entry points

### Key Dependencies

- `taskw`: Taskwarrior Python library
- `pydantic`: Configuration validation
- `click`: CLI framework
- `dogpile.cache`: Caching for API calls
- `ruff`: Linting and formatting
- Service-specific: `PyGithub`, `python-gitlab`, `jira`, etc.
