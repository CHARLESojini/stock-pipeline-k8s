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

*To be added*

---

## Phase 2c — Spark on Kubernetes

*To be added*

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
