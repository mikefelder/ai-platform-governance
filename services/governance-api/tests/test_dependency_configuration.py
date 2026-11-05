"""Keep deployed dependency versions aligned with the audited configuration."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_collector_is_built_from_reviewed_components():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    collector = compose["services"]["otel-collector"]
    assert collector["build"]["context"] == "./services/otel-collector"
    assert "image" not in collector, "Do not replace the patched build with the upstream Contrib image"


def test_terraform_requires_an_explicit_collector_image():
    variables = (ROOT / "infra/variables.tf").read_text()
    image = re.search(r'variable "otel_collector_image"\s*\{([^}]*)\}', variables)
    assert image is not None
    assert "default" not in image.group(1), "Deployments must explicitly select the custom Collector image"
