"""OpenTelemetry setup for the Governance API.

Configures TracerProvider with exporters based on environment variables:
- Console exporter: always enabled for local dev
- OTLP exporter: enabled when OTEL_EXPORTER_OTLP_ENDPOINT is set
- Azure Monitor exporter: enabled when APPLICATIONINSIGHTS_CONNECTION_STRING is set
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "uc3-governance-api")
_initialised = False


def init_telemetry() -> None:
    """Initialise the global TracerProvider. Safe to call multiple times."""
    global _initialised
    if _initialised:
        return

    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "service.namespace": "uaip",
        }
    )
    provider = TracerProvider(resource=resource)

    # Always add console exporter for local observability
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # OTLP exporter (collector, Jaeger, etc.)
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )

    # Azure Monitor exporter
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection_string:
        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

        provider.add_span_processor(
            BatchSpanProcessor(
                AzureMonitorTraceExporter(connection_string=connection_string)
            )
        )

    trace.set_tracer_provider(provider)
    _initialised = True


def get_tracer(name: str | None = None) -> trace.Tracer:
    """Return a tracer scoped to the given module name."""
    return trace.get_tracer(name or _SERVICE_NAME)
