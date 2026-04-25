# Learning Checkpoints

A running log of the concepts covered in each phase of this project, with questions I answered along the way. Used for self-review and interview preparation.

---

## Phase 1 — Local Foundation (kind cluster)

**Concepts covered:** Homebrew, Docker Desktop, Terraform (via HashiCorp tap), kubectl, Helm, kind, AWS CLI, basic K8s primitives (Pod, Deployment, Service, NodePort).

### Q1. What's the difference between a Pod, a Deployment, and a Service?

- **Pod:** The smallest deployable unit in Kubernetes. One or more containers that share network and storage, scheduled together on a node.
- **Deployment:** A controller that manages a set of identical Pods. Handles rolling updates, rollbacks, and maintaining the desired replica count.
- **Service:** A stable network endpoint (DNS name + virtual IP) that routes traffic to a set of Pods matched by labels. Pods come and go; Services stay.

### Q2. What does NodePort do vs ClusterIP vs LoadBalancer?

- **ClusterIP** (default): Internal-only virtual IP, reachable only from inside the cluster. Used for service-to-service communication.
- **NodePort:** Exposes the Service on a static port (30000–32767) on every node's IP. Reachable from outside the cluster via `<node-ip>:<nodeport>`. Used for dev/testing.
- **LoadBalancer:** Tells the cloud provider to provision an external load balancer (e.g., AWS ELB) that forwards traffic to the Service. Production-grade external exposure.

### Q3. Why did we use `extraPortMappings` in the kind config?

Kind runs nodes as Docker containers. Those containers' ports aren't automatically exposed to the Mac host. `extraPortMappings` punches a hole from the host (localhost) through the kind control-plane container's port, so when we expose a Service on NodePort 30000, `curl http://localhost:30000` works from the Mac.

### Q4. What happens to Pods if you `docker restart` the kind container?

The kind node (container) restarts, kubelet comes back up, and Pods are rescheduled. Ephemeral state inside the Pod is lost unless backed by a PersistentVolumeClaim. Pods are cattle, not pets — they're designed to be replaceable.

---

## Phase 2a — Postgres on Kubernetes

**Concepts covered:** Namespace, Secret, ConfigMap, StatefulSet, PersistentVolumeClaim, volumeClaimTemplates, readiness/liveness probes, resource requests/limits, ClusterIP Service, cross-namespace DNS.

### Q1. Why did we use StatefulSet instead of Deployment for Postgres?

StatefulSets give each pod a stable name (postgres-0, postgres-1), stable network identity, and stable per-pod storage (unique PVC per replica). Deployments treat pods as interchangeable — any pod can replace any other. Databases need per-pod identity for replication, consistent storage, and ordered startup/shutdown.

### Q2. What's the difference between `kubectl apply` and `kubectl create`?

- **`create`** is imperative — errors if the resource already exists.
- **`apply`** is declarative and idempotent — creates the resource if missing, updates it to match the YAML if present.

Always use `apply` in practice. It matches the GitOps model where YAML is the source of truth.

### Q3. What happens to the PVC if you `kubectl delete statefulset postgres`?

The PVC **survives by default** — this is a safety feature. Data is preserved. You must delete the PVC manually (`kubectl delete pvc postgres-data-postgres-0`) to free the volume. This protects against accidentally destroying a database by removing the StatefulSet.

### Q4. Why is the Service ClusterIP and not NodePort?

Principle of least privilege. Databases should never be exposed outside the cluster. Only apps inside the cluster (Spark, our producer) need to talk to Postgres, so ClusterIP is correct. Exposing a database externally is a security failure.

### Q5. If another pod in a different namespace wants to connect to this Postgres, what hostname does it use?

`postgres.data.svc.cluster.local` (or the short form `postgres.data`). The full DNS pattern is `<service-name>.<namespace>.svc.cluster.local`. Services in the same namespace can use just `postgres`.

### Q6. What happens when I `kubectl delete pod postgres-0` in a StatefulSet?

The StatefulSet controller immediately recreates the pod with the same name. The new pod re-attaches to the existing PVC (`postgres-data-postgres-0`) and finds the data exactly where the previous pod left it. Restart counter resets to 0 because it's technically a new pod, not a restart of the existing one.

### Q7. Why did kubectl warn about credentials being recorded in container logs?

When you pass a password as a CLI argument (e.g., `psql "postgresql://user:pass@..."`), the full command line gets logged in the container's stdout — which Kubernetes captures and stores. This is fine for local dev, but in production credentials should come from environment variables sourced from Secrets, never from CLI arguments. This is one of the reasons production deployments use Sealed Secrets, External Secrets Operator, or AWS Secrets Manager.

### Q8. What's the practical difference between `kubectl exec -it` and `kubectl run --rm -it`?

- `kubectl exec` runs a command inside an *existing* pod. Used for debugging or one-off queries against a running app.
- `kubectl run` creates a brand new ephemeral pod, runs the command, and (with `--rm`) deletes the pod when done. Used for ad-hoc tooling that doesn't have a permanent home in the cluster.
---

## Phase 2b — Kafka on Kubernetes (Strimzi Operator)

**Concepts covered:** Custom Resource Definitions (CRDs), Custom Resources (CRs), the operator pattern, Strimzi, KRaft mode, KafkaNodePool, replication factor vs min.insync.replicas, headless Services, bootstrap Services, Strimzi version compatibility windows.

### Q1. What's the difference between a CRD and a CR?

A **CRD (Custom Resource Definition)** extends the Kubernetes API with a new resource type. Strimzi's CRDs add `Kafka`, `KafkaTopic`, `KafkaUser`, etc. to your cluster.

A **CR (Custom Resource)** is an instance of that type. Your `stock-kafka` is a Kafka CR, your `stock-prices` is a KafkaTopic CR.

Analogy: CRD is the class definition, CR is the object instance.

### Q2. What does an operator actually do?

An operator is a deployment that runs a controller loop in the cluster. The loop watches CRs of a specific type and continuously reconciles reality with the spec. If you write `replicas: 3` in a Kafka CR but only 2 broker pods exist, the operator notices the diff and creates the missing pod. If a broker pod dies, the operator brings it back. It encodes operational knowledge as code.

### Q3. Why use KRaft mode instead of Zookeeper?

KRaft (KIP-500) replaces Zookeeper with Kafka's own Raft-based consensus protocol. Benefits:
- One fewer system to operate
- Faster controller failover (seconds vs minutes)
- Simpler ops, smaller resource footprint
- Zookeeper is officially removed in Kafka 4.0

For new deployments in 2026, KRaft is the only reasonable choice.

### Q4. What's the difference between `replication.factor` and `min.insync.replicas`?

- **replication.factor**: how many copies of each partition exist across brokers. We set 3.
- **min.insync.replicas**: how many replicas must acknowledge a write before the producer considers it successful. We set 2.

With 3/2, the cluster survives 1 broker failure without data loss or write failures. If 2 brokers fail, writes pause until at least 2 are healthy again — preserves consistency over availability.

### Q5. What's a headless service and why does Kafka use one?

A headless service has `clusterIP: None`. Instead of a single virtual IP that load-balances, it creates one DNS A-record per pod (e.g., `stock-kafka-dual-role-0.stock-kafka-kafka-brokers.kafka.svc.cluster.local`). Kafka clients need direct access to specific brokers (each broker owns specific partitions), so the headless service gives clients per-broker DNS. The bootstrap service handles the initial connection, then clients are told which brokers to talk to for which partitions.

### Q6. Why did Strimzi create one PVC per broker, but our Postgres StatefulSet had `volumeClaimTemplates`?

Same idea, different syntax. Strimzi's `KafkaNodePool` does the volumeClaimTemplates expansion for you internally. Both produce a unique PVC per replica (e.g., `data-stock-kafka-dual-role-0/1/2`). The operator pattern hides the StatefulSet plumbing while still using StatefulSets under the hood.

### Q7. What happened with the Kafka 3.8.0 version error?

Strimzi 0.51.0 only supports Kafka 4.1.0, 4.1.1, and 4.2.0 — older Kafka versions are dropped from each new operator release. Production teams pin both the operator version and the Kafka version explicitly to avoid this. Lesson: when using a "latest" install URL, always check what versions that release actually supports before writing your CRs.

### Q8. Why is "delete all 3 brokers at once" a bad idea?

In a Kafka cluster with replication factor 3 and `min.insync.replicas: 2`, you need at least 2 brokers online at all times for writes to succeed. Deleting all 3 simultaneously means:

- **Zero in-sync replicas** — all writes pause
- **Controller election deadlock risk** — KRaft needs a quorum of controllers online to elect a leader; with all gone, the cluster bootstraps from disk and may take longer to recover
- **Potential split-brain on recovery** — if brokers come back at different times with diverging local state

In production, you ALWAYS do **rolling restarts**: delete one broker, wait for it to rejoin and become an in-sync replica (ISR), then move to the next. Strimzi handles this for you when you change the cluster spec; manual `kubectl delete` bypasses that safety.

Lesson: in a real cluster with traffic, this would cause dropped writes and angry users. On a kind cluster with no traffic, the operator pattern saved me — Strimzi rebuilt brokers in sequence (visible in the staggered pod ages) even though they were deleted simultaneously.

---

## Phase 2c — Spark on Kubernetes

**Concepts covered:** Spark Operator (CRD pattern), Spark on K8s scheduler, custom Docker images, local container registries with kind, Spark Structured Streaming, watermarking, foreachBatch sink pattern, dual-sink streaming, JDBC connectors, cross-namespace DNS in practice, Helm chart value drift between versions.

### Q1. How does Spark on Kubernetes actually work — what's the lifecycle?

The Spark Operator watches `SparkApplication` CRs. When you apply one:
1. Operator validates the spec via its admission webhook
2. Operator runs `spark-submit` with K8s scheduler backend args
3. spark-submit creates the **driver pod** in the target namespace
4. The driver pod's main process runs your Python `main()`
5. The driver internally calls the K8s API to create **executor pods** (this is why we needed RBAC in Phase 2c)
6. Executors register back to the driver via NettyRPC
7. Driver hands tasks to executors; executors run them, send results back
8. When the SparkApplication ends, the operator cleans up all pods

The driver is the only thing the operator creates directly. The executors are created BY the driver — that's why the driver needs RBAC permissions to create pods.

### Q2. Why did we need a local container registry?

Kind cluster nodes are containers themselves, with their own filesystems. Even though Docker is running everything on your Mac, the kind nodes can't reach into your laptop's local Docker image cache. We need an intermediary "post office" — a registry that both your build tool and the kind nodes can talk to.

`docker run registry:2 -p 5001:5000` spins up a tiny registry. We connect it to the same Docker network as kind. We then patch each kind node's containerd config to know `localhost:5001` redirects to the `kind-registry` container internally.

### Q3. What does `foreachBatch` do, and when should I use it?

Spark's built-in writers (Parquet, JSON, Kafka) handle micro-batch persistence automatically. But Postgres via JDBC isn't a native streaming sink — Spark's continuous mode doesn't know how to maintain a JDBC connection across micro-batches.

`foreachBatch` is the escape hatch: Spark hands you the batch DataFrame, you write it however you want using the regular batch DataFrame writer. It's the standard pattern for streaming-to-anything-without-a-native-sink (databases, REST APIs, custom queues).

### Q4. What's a watermark in Spark streaming?

A watermark is the maximum lateness Spark tolerates. We set `withWatermark("event_time", "2 minutes")` meaning: "If a record arrives more than 2 minutes after its window has closed, drop it instead of reopening that window."

Without watermarks, Spark would have to keep ALL windows in memory forever in case a 10-year-old message shows up. Watermarks let Spark close out old windows and free memory.

### Q5. Why are aggregations using `outputMode("update")`?

Three modes:
- `append`: only emit final, completed windows. Wait until watermark passes the window-end + watermark-delay.
- `complete`: emit every window every batch. Huge — only for small aggregations.
- `update`: emit only the windows that CHANGED in this batch.

We use `update` because late data within the watermark can update a window's running avg, and we want to see those updates emitted to Postgres immediately (not wait for the window to fully close).

### Q6. Why did Helm say "Upgrade complete" but the operator's pod args didn't change?

The Helm chart's `values.yaml` schema changed between versions. The old key `sparkJobNamespaces` (Helm chart v1.x) was renamed to `spark.jobNamespaces` (v2.x). Helm doesn't error on unknown keys — it silently ignores them. So `helm upgrade --set sparkJobNamespaces=...` succeeded but actually configured nothing.

Lesson: after every operator install, verify the running pod's actual args (`kubectl describe pod` or grep logs for the launch command). Don't trust `helm get values` — it shows what YOU passed, not what the chart actually consumed.

This is the #1 portfolio-grade Helm gotcha.

### Q7. What's the practical difference between cluster mode and client mode?

- **client mode**: the driver runs on your laptop / wherever you ran `spark-submit`. Useful for interactive REPL/notebook usage.
- **cluster mode**: the driver runs as a pod inside the cluster. Production pattern — driver and executors share infrastructure, networking, lifecycle.

For batch and streaming jobs, always use cluster mode. Client mode is only for debugging.

### Q8. Why does the Spark image need to ship with the Kafka JAR and Postgres JDBC driver?

Spark's classpath at runtime is exactly what's in `/opt/spark/jars/` inside the image. The Kafka source connector and Postgres JDBC driver aren't part of the base Spark image — they're separate Maven artifacts. The Dockerfile downloads them at build time so they're baked into the image.

The alternative is `--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3` which downloads at runtime — but that fails in air-gapped environments and slows startup. Bake them into the image.

---

## Phase 2d — Producer app on Kubernetes

*To be added*

---

## Phase 2e — Grafana on Kubernetes

*To be added*

---

## Phase 3 — Helm

*To be added*

---

## Phase 4 — Terraform for AWS

*To be added*

---

## Phase 5 — GitHub Actions CI/CD

*To be added*

---

## Phase 6 — EKS Capstone

*To be added*

---

## Cross-cutting concepts

Questions that came up across phases, organized by topic.

### Kubernetes architecture
*To be filled in*

### Networking
*To be filled in*

### Storage
*To be filled in*

### Security
*To be filled in*

### AWS-specific
*To be filled in*
---

## Project Framing & Communication

How to describe this project in interviews, resumes, LinkedIn, and portfolio writeups. Important: framing matters as much as the technical work.

### Q1. Should I call this a "cloud migration" project?

**No.** A migration implies moving a production workload from one environment to another with continuity goals — uptime SLAs, cutover plans, rollback strategies, user impact. None of those exist here.

Better framings:

- **"Cloud-native re-architecture"** — accurate and signals senior-level thinking
- **"Productionization"** — emphasizes the move from PoC to production patterns
- **"Platform engineering project"** — highlights the infrastructure focus
- **"Reference implementation"** or **"greenfield cloud-native build"** — also valid

### Q2. How should I describe the relationship between v1 and v2?

> "v1 of this project (Real-Time Stock Pipeline, Docker Compose) proved the streaming architecture worked end-to-end. v2 rebuilds the same logical system — Python producer, Kafka, Spark Structured Streaming, Postgres, Grafana — as a cloud-native deployment to demonstrate production patterns: Kubernetes operators, Terraform-managed AWS infrastructure, and CI/CD with OIDC authentication."

This is accurate AND shows progression of thinking, which is what senior interviewers actually want to see.

### Q3. What's a strong resume bullet for this project?

> "Designed and deployed a real-time data pipeline on AWS EKS using Kubernetes operators (Strimzi for Kafka, Spark Operator), Terraform for IaC, and GitHub Actions OIDC for CI/CD."

Avoid: "Migrated stock pipeline to AWS." That sounds like lift-and-shift.

### Q4. When IS "migration" the right word?

When you actually do one in a real job — moving a live production workload with users, uptime requirements, and rollback plans. The hard parts of a migration (dual-writes, cutover, monitoring during transition, blast-radius mitigation) don't exist on a portfolio project, which is why the word doesn't fit. Save it for the real thing.

### Q5. What questions might recruiters ask if I overclaim "migration"?

- "How did you handle dual-writes during cutover?"
- "What was the rollback plan?"
- "What was the user impact and how did you measure it?"
- "What was the data validation strategy between old and new systems?"

If you can't answer these in detail, the project sounds inflated. Honest framing as "re-architecture" sidesteps these questions because the answer is "this was a greenfield build."