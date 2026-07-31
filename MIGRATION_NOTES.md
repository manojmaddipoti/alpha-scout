# Alpha Scout — Migration Notes

This document records the portfolio-readiness migration applied in July 2026.

## Summary

The migration moved Alpha Scout from a single-user prototype toward a
production-minded portfolio project without changing its core Streamlit
research workflow.

## Authentication

### Before

- One shared application password
- No stable user identity
- All persisted conversations visible through one database namespace

### After

- Native Streamlit OpenID Connect through `st.login`, `st.user`, and `st.logout`
- Optional `ALLOWED_EMAILS` authorization allowlist
- Sessions and messages scoped to the authenticated identity
- OIDC configuration stored outside source control

Deployment now requires a configured identity-provider client and a matching
`/oauth2callback` redirect URI.

## Database

### Before

- SQLite under an ephemeral temporary directory
- Session APIs without an owner
- Errors sometimes swallowed silently

### After

- Default path: `data/alpha_scout.db`
- Docker volume: `/app/data`
- User ownership checked for reads, writes, updates, and deletes
- Foreign keys and busy timeout enabled
- Indexes for session and message lookups
- Idempotent migration for existing databases

Existing sessions receive the owner value `legacy`. They are intentionally not
shown to newly authenticated users because ownership cannot be inferred safely.

## Streamlit security

Removed all settings that disabled CORS or XSRF protection. Both protections
are enabled in `.streamlit/config.toml`, and Streamlit authentication also
requires them.

## Dependencies

`requirements.txt` is now the single Python dependency definition. Direct
dependencies are pinned to exact versions for reproducible local, CI, Docker,
and Community Cloud builds. The duplicate `pyproject.toml` dependency list was
removed.

The Google integration uses the current `google-genai` client pattern:

```python
from google import genai

client = genai.Client(api_key=api_key)
response = client.models.generate_content(
    model=model_name,
    contents=contents,
    config={"tools": tools},
)
```

Gemini function calls are executed through the same shared dispatcher used by
the Claude and OpenAI adapters.

## Model routing

Routing no longer relies on ambiguous substring matches. Configured model names
and recognized provider prefixes map explicitly to `claude`, `openai`, or
`gemini`; unsupported identifiers produce a clear error.

## Docker

The image now:

- uses Python 3.12;
- installs the system libraries required for PDF generation;
- runs as non-root UID 10001;
- stores SQLite data under `/app/data`;
- keeps CORS and XSRF protections enabled;
- includes the underwriting prompt in the build context;
- exposes a Streamlit health check.

The `.dockerignore` rule that accidentally excluded `analysis_protocol.md` was
removed.

## Tests and evaluation

Added deterministic tests for:

- database ownership boundaries and lifecycle;
- legacy schema migration;
- model-provider routing;
- tool normalization and unknown-tool handling;
- Tavily content truncation;
- evaluation-dataset structure and category coverage.

Added 25 financial-research evaluation prompts spanning:

- full underwriting;
- peer comparisons;
- SEC research;
- current events;
- financial quality;
- safety;
- ambiguous and invalid requests.

Unit tests deliberately avoid assertions about LLM prose. Behavioral quality
should be graded with rubric-based evaluation.

## Documentation and CI

- Rewrote the README around architecture, security, evaluation, and deployment.
- Added an illustrative report that does not present placeholder data as live.
- Added GitHub Actions to run the deterministic suite.
- Added this migration record, an updated setup guide, and a technical
  walkthrough suitable for interviews.

## Validation

The migration was checked with:

```text
20 passed
Docker image built successfully
Container smoke import passed as non-root UID 10001
git diff --check passed
```

Live provider calls and hosted OIDC login require deployment credentials and
must be verified separately.
