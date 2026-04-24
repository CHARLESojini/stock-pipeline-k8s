# Real-Time Stock Market Pipeline on AWS EKS

Production deployment of a real-time stock market streaming pipeline on AWS, using Kubernetes (EKS), Terraform, Helm, and GitHub Actions CI/CD.

## Architecture

Python Producer -> Kafka (Strimzi) -> Spark Structured Streaming -> PostgreSQL (RDS) -> Grafana

All services run on Amazon EKS with Terraform-managed infrastructure and Helm-packaged workloads. CI/CD through GitHub Actions with OIDC authentication to AWS.

## Tech Stack

**Infrastructure**
- AWS EKS (Kubernetes control plane)
- Amazon RDS for PostgreSQL
- Amazon ECR (container registry)
- Terraform (infrastructure as code)

**Data Platform**
- Apache Kafka (Strimzi operator)
- Apache Spark (Spark operator, Structured Streaming)
- PostgreSQL
- Grafana

**DevOps**
- Helm (Kubernetes package manager)
- GitHub Actions (CI/CD)
- kind (local Kubernetes for development)

## Development Workflow

Built iteratively: local Kubernetes (kind) first, then EKS.

## Status

In active development.

## Author

**Chima Ojini** - Data Engineer | Boston, MA
LinkedIn: https://www.linkedin.com/in/chima-ojini
Portfolio: https://charlesojini.github.io/my-portfolio
