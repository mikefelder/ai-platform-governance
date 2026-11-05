FROM python:3.15-alpine@sha256:20a82dbc2783112ddb91d1534603f802d222a3e63e593cd002eb2ac534e70211

ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/

WORKDIR /app
COPY main.py .
COPY requirements.txt .

RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip

CMD ["python", "main.py"]
