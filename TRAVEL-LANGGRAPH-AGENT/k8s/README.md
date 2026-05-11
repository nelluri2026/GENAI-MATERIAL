# EKS Deployment Manifests

These manifests deploy the travel planner as two Kubernetes services:

- `travel-agent-api`: FastAPI + LangGraph backend, internal `ClusterIP`
- `travel-agent-ui`: Chainlit UI, exposed through NGINX Ingress

## Prerequisites

- EKS cluster is running.
- NGINX Ingress Controller is installed.
- Metrics Server is installed if you want to use the HPA manifests.
- Backend and UI images are pushed to ECR.
- Worker nodes can pull from ECR.
- Postgres/Neon database is reachable from the cluster.

## Files

```text
00-namespace.yaml
01-configmap.yaml
02-secret.example.yaml
03-backend.yaml
04-ui.yaml
05-ingress.yaml
06-hpa.yaml
kustomization.yaml
```

## Setup

1. Update image URIs in:

```bash
k8s/03-backend.yaml
k8s/04-ui.yaml
```

Replace:

```text
111122223333.dkr.ecr.us-east-1.amazonaws.com/...
```

2. Create the runtime secret locally:

```bash
cp k8s/02-secret.example.yaml k8s/02-secret.yaml
```

Then fill:

```text
OPENAI_API_KEY
SERPAPI_API_KEY
DUFFEL_ACCESS_TOKEN
LANGGRAPH_POSTGRES_URI
```

`k8s/02-secret.yaml` is ignored by git.

3. Update the ingress hostname:

```bash
k8s/05-ingress.yaml
```

Replace:

```text
travel-agent.example.com
```

4. For first deployment only, enable table setup in `01-configmap.yaml`:

```text
LANGGRAPH_POSTGRES_SETUP: "true"
BOOKINGS_TABLE_SETUP: "true"
```

For the setup deployment, keep `travel-agent-api` replicas at `1` in `03-backend.yaml` to avoid multiple pods trying to run setup at the same time.

Deploy once, confirm startup succeeds, then set both setup flags back to:

```text
LANGGRAPH_POSTGRES_SETUP: "false"
BOOKINGS_TABLE_SETUP: "false"
```

After that, scale `travel-agent-api` back to `2` or more replicas.

## Deploy

```bash
kubectl apply -k k8s
```

Check pods:

```bash
kubectl get pods -n travel-agent
```

Check services:

```bash
kubectl get svc -n travel-agent
```

Check ingress:

```bash
kubectl get ingress -n travel-agent
```

View logs:

```bash
kubectl logs -n travel-agent deploy/travel-agent-api
kubectl logs -n travel-agent deploy/travel-agent-ui
```

## Recommended Production Upgrade

For a stronger production setup, replace `02-secret.yaml` with one of:

- AWS Secrets Manager + External Secrets Operator
- AWS Secrets Store CSI Driver
- Sealed Secrets

That avoids applying raw Kubernetes Secret YAML from a local machine.

You may also want:

- AWS Load Balancer Controller if you prefer ALB Ingress instead of NGINX.
- cert-manager for TLS automation.
- NetworkPolicies to allow UI-to-backend traffic and restrict everything else.
- PodDisruptionBudgets for rolling upgrades.
