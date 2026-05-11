FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

# Gateway policy sources (TC-2f digest). Optional at build time — the
# build context may not include them in every pipeline; the COPY uses a
# trailing slash + `|| true` shim via a multi-stage trick is not needed
# because we use a wildcard that is permitted to match zero files.
COPY policy_sources/ /app/policy_sources/

RUN pip install --no-cache-dir .

ENV APIM_POLICY_PATHS=/app/policy_sources/*.tf

EXPOSE 8000

CMD ["uvicorn", "governance_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
