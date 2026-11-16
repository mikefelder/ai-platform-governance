FROM python:3.15-alpine@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd

ARG PIP_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/

WORKDIR /app
COPY main.py .
COPY requirements.txt .

RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.14/ensurepip

CMD ["python", "main.py"]
