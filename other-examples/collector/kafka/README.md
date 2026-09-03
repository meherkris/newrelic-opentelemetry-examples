# Kafka Monitoring with OpenTelemetry and New Relic

End-to-end observability for Apache Kafka using the [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) and [New Relic](https://newrelic.com).

## Examples

| Example | Environment | Description |
|---------|-------------|-------------|
| [`self-host-kafka/`](self-host-kafka/) | Docker Compose | Self-hosted Kafka on bare metal / VMs / Docker. OTel Java Agent on brokers, kafkametrics receiver for consumer lag |
| [`k8s-self-managed/`](k8s-self-managed/) | Kubernetes | Kafka on Kubernetes (plain StatefulSet, KRaft). OTel Java Agent via init container, OTel Collector as plain Deployment |
| [`k8s-strimzi/`](k8s-strimzi/) | Kubernetes + Strimzi | Strimzi-managed Kafka on Kubernetes. Prometheus JMX Exporter on each broker, OTel Collector scrapes via Prometheus receiver |

---

## What You'll See in New Relic

| Signal | Source | Details |
|--------|--------|---------|
| **Broker metrics** | OTel Java Agent (self-host, k8s-self-managed) or JMX Exporter (k8s-strimzi) | Request latency, throughput, ISR, log sizes per broker |
| **Cluster metrics** | `kafkametrics` receiver | Partition counts, topic counts, offline partitions |
| **Consumer lag** | `kafkametrics` receiver | Lag per topic / partition / consumer group |
| **Producer traces** | Java app + OTel Java Agent | End-to-end spans for each message produced |
| **Consumer traces** | Java app + OTel Java Agent | Spans linked back to producer via W3C Trace Context |

---

## Quick Start

**Option 1 — Docker Compose (self-host-kafka):**
```bash
cd self-host-kafka
cp .env.example .env      # add NEW_RELIC_LICENSE_KEY
docker compose up --build
```
See [self-host-kafka/README.md](self-host-kafka/README.md) for full setup instructions.

**Option 2 — Kubernetes self-managed (k8s-self-managed):**
```bash
cd k8s-self-managed
cp secrets.yaml.template secrets.yaml   # add NEW_RELIC_LICENSE_KEY
kubectl apply -f .
```
See [k8s-self-managed/README.md](k8s-self-managed/README.md) for full setup instructions.

**Option 3 — Kubernetes Strimzi (k8s-strimzi):**
```bash
# Install Strimzi operator first
kubectl create namespace kafka
kubectl create -f 'https://strimzi.io/install/latest?namespace=kafka'
kubectl wait deployment -n kafka strimzi-cluster-operator --for=condition=Available --timeout=5m

cd k8s-strimzi
cp secrets.yaml.template secrets.yaml   # add NEW_RELIC_LICENSE_KEY
kubectl apply -f .
```
See [k8s-strimzi/README.md](k8s-strimzi/README.md) for full setup instructions.

---

## Repository Structure

```
kafka/
├── common/
│   └── apps/
│       ├── producer/          # Java producer (zero OTel SDK — agent-only)
│       └── consumer/          # Java consumer (zero OTel SDK — agent-only)
├── self-host-kafka/
│   ├── docker-compose.yaml          # 2 brokers + collector + apps
│   ├── otel-collector-config.yaml   # Collector pipelines
│   ├── jmx-custom-config.yaml       # OTel JMX rules for Kafka MBeans
│   ├── .env.example                 # Configuration template
│   └── otel-java-agent-init/        # Downloads OTel Java Agent to shared volume
├── k8s-self-managed/
│   ├── kafka.yaml                   # Namespace + Kafka StatefulSet (KRaft, OTel agent)
│   ├── collector.yaml               # OTel Collector Deployment + inline pipeline config
│   ├── sample-apps.yaml             # Producer + Consumer Deployments (optional)
│   └── secrets.yaml.template        # Secret template (copy → secrets.yaml, add license key)
└── k8s-strimzi/
    ├── kafka.yaml                   # JMX ConfigMap + Kafka CR (Strimzi) + KafkaTopic
    ├── collector.yaml               # Namespace + RBAC + OTel Collector Deployment
    ├── sample-apps.yaml             # Producer + Consumer Deployments (optional)
    └── secrets.yaml.template        # Secret template (copy → secrets.yaml, add license key)
```

## Related Resources

- [New Relic self-hosted Kafka documentation](https://docs.newrelic.com/docs/opentelemetry/integrations/kafka/self-hosted/)
- [New Relic Strimzi Kafka documentation](https://docs.newrelic.com/docs/opentelemetry/integrations/kafka/kubernetes-strimzi/)
- [OpenTelemetry Java Agent](https://opentelemetry.io/docs/zero-code/java/agent/)
- [OpenTelemetry Collector kafkametrics receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/kafkametricsreceiver)
- [Strimzi Kafka operator](https://strimzi.io/)
