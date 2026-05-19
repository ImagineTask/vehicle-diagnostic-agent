"""OpenTelemetry tracing setup.

Vendor-neutral: ships OTLP spans to whatever endpoint OTEL_EXPORTER_OTLP_ENDPOINT
points at. On GCP that's the OpenTelemetry collector → Cloud Trace; on Azure
it's the collector → Application Insights. No cloud-specific code in this file.

If no endpoint is configured, tracing is silently disabled (a no-op
TracerProvider is registered so `tracer.start_as_current_span(...)` calls
elsewhere remain safe).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI

from src.config.settings import settings

logger = logging.getLogger(__name__)


def setup_tracing(app: FastAPI) -> Optional[Any]:
    """Configure the global TracerProvider and instrument FastAPI/httpx/logging.

    Returns the TracerProvider on success, None if disabled. Safe to call once
    at startup; idempotent if the SDK is already configured.
    """
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT unset — tracing disabled")
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("OpenTelemetry packages not installed — tracing disabled")
        return None

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.namespace": "vda",
            "deployment.environment": settings.ENVIRONMENT,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # FastAPI: HTTP server spans for every request.
    FastAPIInstrumentor.instrument_app(app)
    # httpx: covers the openai SDK and most async HTTP traffic.
    HTTPXClientInstrumentor().instrument()
    # Stamps trace_id/span_id onto log records so JSON logs are correlatable.
    LoggingInstrumentor().instrument(set_logging_format=False)

    logger.info(
        "Tracing enabled (endpoint=%s, service=%s)",
        settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        settings.OTEL_SERVICE_NAME,
    )
    return provider


def shutdown_tracing(provider: Optional[Any]) -> None:
    if provider is None:
        return
    try:
        provider.shutdown()
    except Exception:
        logger.exception("Tracer provider shutdown failed")
