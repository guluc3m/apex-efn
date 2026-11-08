import os

# Keep the test run hermetic: no OTLP exporters start unless a test asks for them explicitly.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
