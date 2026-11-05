FROM python:3.14-alpine@sha256:eb2c62658b8d51bff0acc408504b76521d02030de56a8a3c1e830083e89b89d2

ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/

WORKDIR /app
COPY main.py .
COPY requirements.txt .

RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip

CMD ["python", "main.py"]
