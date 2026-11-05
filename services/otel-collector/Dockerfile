FROM golang:1.27-alpine AS builder

WORKDIR /build
RUN go install go.opentelemetry.io/collector/cmd/builder@v0.164.0
COPY builder-config.yaml .
RUN CGO_ENABLED=0 builder --config builder-config.yaml

FROM scratch
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=builder /build/collector/otelcol-contrib /otelcol-contrib
COPY otel-collector-config.yaml /etc/otelcol-contrib/config.yaml
USER 10001:10001
EXPOSE 4317 4318 13133
ENTRYPOINT ["/otelcol-contrib"]
CMD ["--config", "/etc/otelcol-contrib/config.yaml"]
