# Contributing to RTS CPI

## Branch Naming Convention

```
feat/short-description     # New feature
fix/short-description      # Bug fix
chore/short-description    # Maintenance, dependencies, CI
docs/short-description     # Documentation only
```

Always branch from `main`. Keep branch names lowercase with hyphens.

## Commit Message Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

### Types

| Type | When to use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `chore` | Maintenance (deps, CI, config) |
| `docs` | Documentation changes |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `perf` | Performance improvement |

### Examples

```
feat(ingestion): add CFL FJL batch upload endpoint
fix(rls): correct tenant filter on dashboard queries
chore(docker): pin Superset image to 4.1.1
docs(secrets): add Azure Key Vault rotation guide
```

## Pull Request Checklist

- [ ] Branch is up to date with `main`
- [ ] Commit messages follow Conventional Commits
- [ ] No secrets or credentials in the diff
- [ ] `.env.example` updated if new environment variables were added
- [ ] Database migrations included if models changed
- [ ] API changes are backward-compatible or versioned
- [ ] Tests pass locally (when test suite is available — Phase 3)
- [ ] Documentation updated for user-facing changes

## Local Development Setup

1. Ensure Docker and Docker Compose are installed.
2. Clone the repository:
   ```bash
   git clone <repo-url> && cd CPI
   ```
3. Create your environment file:
   ```bash
   cp .env.example .env
   ```
4. Fill in `.env` values (see [docs/SECRETS.md](docs/SECRETS.md)).
5. Start the stack:
   ```bash
   docker compose up -d
   ```
6. Access services:
   - API: http://localhost:8000
   - Frontend: http://localhost:5173
   - Superset: http://localhost:8088

## Running Tests

> Test infrastructure will be added in Phase 3. This section will be updated
> with commands for `pytest` (API) and `vitest` (frontend) once available.

## Code Style

- **Python (API):** Follow PEP 8. Linting via Ruff (to be configured in Phase 3).
- **TypeScript (Frontend):** Follow project ESLint config.
- Keep functions focused and files under 300 lines where practical.
- Prefer explicit over implicit — especially around tenant scoping and RLS.
