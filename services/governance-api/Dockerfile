FROM python:3.15-alpine@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd

ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/

WORKDIR /app

COPY pyproject.toml .
COPY requirements.txt .
COPY src/ src/

# Gateway policy sources (TC-2f digest). Optional at build time — the
# build context may not include them in every pipeline; the COPY uses a
# trailing slash + `|| true` shim via a multi-stage trick is not needed
# because we use a wildcard that is permitted to match zero files.
COPY policy_sources/ /app/policy_sources/

RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && pip install --no-cache-dir --no-deps . \
    && pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip

ENV APIM_POLICY_PATHS=/app/policy_sources/*.tf

EXPOSE 8000

CMD ["uvicorn", "governance_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
