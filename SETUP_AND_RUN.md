# Alpha Scout — Setup and Run Guide

## Prerequisites

- Python 3.12
- Git
- API keys for Anthropic, OpenAI, Google Gemini, and Tavily
- An OpenID Connect client from Google, Microsoft Entra ID, Okta, Auth0, or
  another OIDC provider

## Local setup

```bash
git clone https://github.com/manojmaddipoti/alpha-scout.git
cd alpha-scout
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Add API values to `.env`:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key
TAVILY_API_KEY=your_tavily_api_key
SEC_IDENTITY=Your Name your@email.com
```

Do not commit `.env`.

## Configure authentication

Register an OIDC web application with this local redirect URL:

```text
http://localhost:8501/oauth2callback
```

Then update `.streamlit/secrets.toml`:

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "a-long-random-secret"
client_id = "your-client-id"
client_secret = "your-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Generate `cookie_secret` with a cryptographically secure password generator.
The example uses Google's metadata URL; use the URL supplied by your identity
provider when configuring another provider.

To restrict access further, add an email allowlist to `.env`:

```env
ALLOWED_EMAILS=you@example.com,recruiter@example.com
```

## Run the application

```bash
source .venv/bin/activate
streamlit run app.py
```

Open `http://localhost:8501`, select **Log in**, and authenticate through the
configured provider.

## Run tests

```bash
source .venv/bin/activate
pytest -q
```

The suite does not require live provider keys because external calls are mocked.

## Local data

SQLite defaults to:

```text
data/alpha_scout.db
```

Override it when needed:

```env
DB_PATH=/absolute/path/to/alpha_scout.db
```

Database files are ignored by Git. Each conversation is scoped to the
authenticated user's stable OIDC identity.

## Docker

Build:

```bash
docker build -t alpha-scout .
```

Run with a persistent database volume and read-only secrets mount:

```bash
docker run --env-file .env \
  -v alpha-scout-data:/app/data \
  -v "$PWD/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro" \
  -p 8501:8501 \
  alpha-scout
```

The image runs as an unprivileged user and exposes the health endpoint at
`/_stcore/health`.

## Streamlit Community Cloud

1. Create an app from the GitHub repository.
2. Select `app.py` and Python 3.12.
3. Paste API values and the `[auth]` section into deployment Secrets.
4. Replace the redirect URI with:

   ```text
   https://<your-app>.streamlit.app/oauth2callback
   ```

5. Register that same URI with the identity provider.
6. Verify login, one research request, report export, and logout.

Community Cloud's local filesystem is ephemeral. Use managed Postgres or another
durable datastore if hosted conversation history must survive restarts.

## Troubleshooting

### OIDC authentication is not configured

- Confirm `.streamlit/secrets.toml` exists.
- Confirm all five `[auth]` values are present.
- Restart Streamlit after changing the secrets file.

### Redirect URI mismatch

The URI must match exactly in Streamlit secrets and the identity-provider
client, including scheme, hostname, port, and `/oauth2callback`.

### Provider API-key errors

Confirm the relevant environment variable exists and that the selected model is
available to that account.

### SEC filing errors

Set `SEC_IDENTITY` to a real name and email in the format required by SEC EDGAR.

### Database errors

Confirm the parent directory of `DB_PATH` is writable. For Docker, mount the
named volume shown above.

### PDF export errors

Install the system libraries listed in `packages.txt`. The Docker image already
includes them.

### Port 8501 is busy

```bash
streamlit run app.py --server.port=8502
```

Update the local OIDC redirect URI to use port 8502 as well.

## Security checklist

- Never commit `.env` or `.streamlit/secrets.toml`.
- Keep CORS and XSRF protection enabled.
- Use OIDC and an allowlist for restricted deployments.
- Rotate credentials exposed in logs or screenshots.
- Mount persistent data with the minimum necessary permissions.
- Treat generated research as unverified and not as investment advice.
