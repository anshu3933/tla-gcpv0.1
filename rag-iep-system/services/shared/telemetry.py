import os
from typing import Optional
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.google_cloud import GoogleCloudInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator

# Initialize OpenTelemetry
def setup_telemetry(service_name: str):
    """Initialize OpenTelemetry with Cloud Trace exporter"""
    # Set up the tracer provider
    tracer_provider = TracerProvider()
    
    # Set up Cloud Trace exporter
    cloud_trace_exporter = CloudTraceSpanExporter()
    
    # Add span processor
    tracer_provider.add_span_processor(
        BatchSpanProcessor(cloud_trace_exporter)
    )
    
    # Set the tracer provider
    trace.set_tracer_provider(tracer_provider)
    
    # Set up Cloud Trace propagator
    set_global_textmap(CloudTraceFormatPropagator())
    
    # Get tracer
    tracer = trace.get_tracer(service_name)
    
    return tracer

# Context manager for creating spans
@contextmanager
def create_span(name: str, attributes: Optional[dict] = None):
    """Create a span with the given name and attributes"""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span

# Instrument FastAPI application
def instrument_fastapi(app):
    """Instrument FastAPI application with OpenTelemetry"""
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument other libraries
    RequestsInstrumentor().instrument()
    VertexAIInstrumentor().instrument()
    GoogleCloudInstrumentor().instrument()

# Utility function to get current trace context
def get_trace_context():
    """Get current trace context for logging"""
    current_span = trace.get_current_span()
    if current_span.is_recording():
        return {
            "logging.googleapis.com/trace": f"projects/{os.environ['PROJECT_ID']}/traces/{current_span.get_span_context().trace_id}",
            "logging.googleapis.com/spanId": current_span.get_span_context().span_id
        }
    return {} 