FROM amazoncorretto:21-alpine AS builder
ARG GRADLE_VERSION=8.12.1
RUN apk add --no-cache curl unzip && \
    curl -fSL "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
      -o /tmp/gradle.zip && \
    unzip -q /tmp/gradle.zip -d /opt && \
    mv "/opt/gradle-${GRADLE_VERSION}" /opt/gradle && \
    rm /tmp/gradle.zip && \
    apk del curl unzip
ENV PATH="/opt/gradle/bin:${PATH}"

WORKDIR /build
COPY build.gradle settings.gradle ./
RUN gradle dependencies --no-daemon -q

COPY src ./src
RUN gradle shadowJar --no-daemon -q


FROM alpine:3.20 AS agent-downloader
RUN apk add --no-cache curl && \
    curl -fSL \
      "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar" \
      -o /opentelemetry-javaagent.jar


FROM gcr.io/distroless/java21-debian12
WORKDIR /app

COPY --from=builder /build/build/libs/app.jar ./app.jar
COPY --from=agent-downloader /opentelemetry-javaagent.jar ./opentelemetry-javaagent.jar

ENV JAVA_TOOL_OPTIONS="-javaagent:/app/opentelemetry-javaagent.jar \
  -Dotel.instrumentation.kafka.experimental-span-attributes=true \
  -Dotel.instrumentation.messaging.experimental.receive-telemetry.enabled=true \
  -Dotel.instrumentation.kafka.producer-propagation.enabled=true \
  -Dotel.instrumentation.kafka.enabled=true \
  -Dotel.instrumentation.runtime-telemetry.enabled=false"

CMD ["/app/app.jar"]
