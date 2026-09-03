# Downloads the OTel Java Agent JAR at build time (cached in Docker layers).
# At runtime, copies the JAR to the shared "otel-agent" volume so each
# Kafka broker can attach it via -javaagent in KAFKA_OPTS.
FROM alpine:3.20
RUN apk add --no-cache curl && \
    curl -fSL \
      "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar" \
      -o /opentelemetry-javaagent.jar && \
    apk del curl
CMD ["cp", "/opentelemetry-javaagent.jar", "/output/opentelemetry-javaagent.jar"]
