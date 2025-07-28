# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bugwarrior is a command-line utility that synchronizes issues from various issue trackers (GitHub, GitLab, Jira, etc.) with Taskwarrior. It's written in Python and supports 20+ different services.

## Development Commands

### Testing
```bash
# Run tests with coverage
pytest --cov=bugwarrior --cov-branch tests

# Run tests for a specific service
pytest tests/test_github.py

# Run a specific test
pytest tests/test_github.py::TestGithubService::test_issues
```

### Linting
```bash
# Run flake8 linting (max-line-length: 100)
flake8
```

### Installation
```bash
# Install with all dependencies
pip install -e .[all]

# Install with specific service dependencies
pip install -e .[jira,github,gitlab]

# Install test dependencies only
pip install -e .[test]
```

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
5. Register service in `setup.py` entry points

### Key Dependencies
- `taskw`: Taskwarrior Python library
- `pydantic`: Configuration validation
- `click`: CLI framework
- `dogpile.cache`: Caching for API calls
- Service-specific: `PyGithub`, `python-gitlab`, `jira`, etc.