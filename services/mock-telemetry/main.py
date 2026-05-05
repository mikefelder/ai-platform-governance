"""Mock telemetry generator for local development.

Emits synthetic OTEL traces and metrics that simulate agent
telemetry, allowing the governance API to be tested end-to-end locally
via docker-compose without real Azure resources.
"""

from __future__ import annotations

import os
import random
import time

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

INTERVAL = int(os.environ.get("TELEMETRY_INTERVAL_SECONDS", "5"))
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

AGENTS = [
    {"service.name": "rag-agent", "agent.type": "rag", "cloud.provider": "azure"},
    {"service.name": "supervisor-agent", "agent.type": "supervisor", "cloud.provider": "azure"},
    {"service.name": "bedrock-gateway", "agent.type": "llm", "cloud.provider": "aws"},
    {"service.name": "incident-agent", "agent.type": "incident", "cloud.provider": "azure"},
]

MODELS = ["gpt-4o", "gpt-4o-mini", "claude-3-sonnet", "claude-3-haiku"]


def create_provider(agent: dict) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": agent["service.name"],
            "service.namespace": "uaip",
            "agent.type": agent["agent.type"],
            "cloud.provider": agent["cloud.provider"],
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
    )
    return provider


def emit_agent_span(provider: TracerProvider, agent: dict) -> None:
    tracer = provider.get_tracer(agent["service.name"])
    model = random.choice(MODELS)
    tokens_prompt = random.randint(100, 2000)
    tokens_completion = random.randint(50, 1500)
    is_error = random.random() < 0.05  # 5% error rate

    with tracer.start_as_current_span(
        f"agent.{agent['agent.type']}.invoke",
        attributes={
            "agent.name": agent["service.name"],
            "agent.type": agent["agent.type"],
            "gen_ai.system": "openai" if "gpt" in model else "anthropic",
            "gen_ai.request.model": model,
            "gen_ai.response.model": model,
            "gen_ai.usage.prompt_tokens": tokens_prompt,
            "gen_ai.usage.completion_tokens": tokens_completion,
            "tokens_total": tokens_prompt + tokens_completion,
            "cloud.provider": agent["cloud.provider"],
        },
    ) as span:
        # Simulate processing time
        time.sleep(random.uniform(0.01, 0.1))

        if is_error:
            span.set_status(trace.StatusCode.ERROR, "Simulated error")
            span.set_attribute("error.type", "SimulatedError")


def main() -> None:
    providers = {a["service.name"]: create_provider(a) for a in AGENTS}

    print(f"Mock telemetry generator started — interval={INTERVAL}s, endpoint={OTLP_ENDPOINT}")
    while True:
        agent = random.choice(AGENTS)
        provider = providers[agent["service.name"]]
        emit_agent_span(provider, agent)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
