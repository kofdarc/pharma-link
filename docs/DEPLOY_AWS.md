# Deploying to AWS

The simplest managed path for this stack: **App Runner** for the Django API, **RDS** for
Postgres, **S3** for encrypted prescription files, and **Amplify Hosting** for the Next.js
web app. No servers to patch, no orchestration to write, autoscaling included. `tools/connector`
is not part of this guide - it runs inside each pharmacy, not on your infrastructure.

```
                         ┌─────────────────────┐
   shopper / pharmacy →  │  Amplify Hosting     │  apps/web (Next.js, SSR)
                         │  yourdomain.com      │
                         └──────────┬───────────┘
                                    │ HTTPS, NEXT_PUBLIC_API_BASE_URL
                                    ▼
                         ┌──────────────────────┐        ┌───────────────────┐
                         │  App Runner          │  ───▶  │  S3 (private)     │
                         │  api.yourdomain.com  │  IAM   │  prescription     │
                         │  apps/api (Docker)   │  role  │  files (encrypted)│
                         └──────────┬───────────┘        └───────────────────┘
                                    │ VPC connector
                                    ▼
                         ┌──────────────────────┐
                         │  RDS Postgres         │
                         │  private subnet        │
                         └──────────────────────┘
```

## Prerequisites

- An AWS account and the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured (`aws configure`) with a user/role that can create RDS, S3, ECR, App Runner, IAM, and (optionally) Route 53/ACM resources.
- Docker, to build the API image.
- A domain you control, if you want `api.yourdomain.com` / `yourdomain.com` instead of the default AWS-generated URLs. Not required to get a working deployment.
- This repo pushed to a Git provider (GitHub/GitLab/Bitbucket) - Amplify Hosting deploys from a connected repo, not a local build.

Rough cost for the POC scale (db.t4g.micro RDS, App Runner at 1 vCPU/2GB with 1 instance, Amplify's free tier build minutes): **~$25-40/month**. RDS is the dominant cost; App Runner and S3 are usage-based and near-zero at low traffic.

## 1. RDS Postgres

Console is easiest for the networking setup (VPC/subnet group), but roughly:

```bash
aws rds create-db-subnet-group \
  --db-subnet-group-name pharmalink-db-subnets \
  --db-subnet-group-description "HealthConnect RDS" \
  --subnet-ids <subnet-1> <subnet-2>   # at least 2 subnets, different AZs, in your default VPC

aws rds create-db-instance \
  --db-instance-identifier pharmalink-db \
  --db-instance-class db.t4g.micro \
  --engine postgres \
  --engine-version 16 \
  --master-username pharmalink \
  --master-user-password '<strong-password>' \
  --allocated-storage 20 \
  --db-name pharmalink \
  --db-subnet-group-name pharmalink-db-subnets \
  --vpc-security-group-ids <sg-id>     # create one that allows 5432 from the App Runner VPC connector's SG only
  --no-publicly-accessible \
  --backup-retention-period 7
```

Note the resulting endpoint - you'll set `DATABASE_URL` to
`postgresql://pharmalink:<password>@<endpoint>:5432/pharmalink`.

Do **not** make this instance publicly accessible. App Runner reaches it through a VPC
connector (step 5), so the security group should only allow inbound 5432 from that
connector's security group.

## 2. S3 bucket for prescription files

```bash
aws s3api create-bucket --bucket pharmalink-prescriptions-prod --region <region> \
  --create-bucket-configuration LocationConstraint=<region>

aws s3api put-public-access-block --bucket pharmalink-prescriptions-prod \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption --bucket pharmalink-prescriptions-prod \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Files are already encrypted at the application layer before they're written (see
`apps/prescriptions/storage.py`), so SSE here is defense-in-depth, not the only layer.

### Product images (public)

Medicine/supplement photos (`apps/medicines/storage.py`) are written to the same bucket under
a `product-images/` prefix, but unlike prescriptions they need to be publicly readable so the
web app can render them directly. Scope public read to just that prefix rather than opening the
whole bucket:

```bash
aws s3api put-public-access-block --bucket pharmalink-prescriptions-prod \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false

aws s3api put-bucket-policy --bucket pharmalink-prescriptions-prod --policy '{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadProductImages",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::pharmalink-prescriptions-prod/product-images/*"
  }]
}'
```

ACLs stay blocked (access is via the bucket policy, not per-object ACLs) and every other prefix
in the bucket - prescriptions included - stays private; the policy only opens `product-images/*`.

## 3. Push the API image to ECR

```bash
aws ecr create-repository --repository-name pharmalink-api

aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker build -t pharmalink-api ./apps/api
docker tag pharmalink-api:latest <account-id>.dkr.ecr.<region>.amazonaws.com/pharmalink-api:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/pharmalink-api:latest
```

Re-run the last three commands (build/tag/push) whenever you want to ship a new version -
App Runner can auto-deploy on new image pushes if you enable that on the service.

## 4. App Runner service

**Networking first:** create a VPC connector so App Runner can reach RDS:

```bash
aws apprunner create-vpc-connector \
  --vpc-connector-name pharmalink-vpc-connector \
  --subnets <subnet-1> <subnet-2> \
  --security-groups <sg-that-can-reach-rds>
```

**IAM instance role**, so the container can talk to S3 without static keys:

```bash
aws iam create-role --role-name pharmalink-apprunner-instance \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam put-role-policy --role-name pharmalink-apprunner-instance \
  --policy-name s3-prescriptions \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":"arn:aws:s3:::pharmalink-prescriptions-prod/*"},{"Effect":"Allow","Action":"s3:ListBucket","Resource":"arn:aws:s3:::pharmalink-prescriptions-prod"}]}'
```

**Create the service** (console is more forgiving for the first pass: App Runner → Create
service → Container registry → pick the ECR image → configure below). Key settings:

- Port: `8080`
- CPU/memory: 1 vCPU / 2 GB is plenty for a POC
- VPC connector: `pharmalink-vpc-connector` (under "Networking")
- Instance role: `pharmalink-apprunner-instance`
- Environment variables (App Runner → Configuration → Environment variables; put secrets like `DJANGO_SECRET_KEY` and the DB password in **Secrets Manager** and reference them instead of plaintext):

  | Variable | Value |
  |---|---|
  | `DJANGO_SECRET_KEY` | a long random string (generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
  | `DJANGO_DEBUG` | `false` |
  | `DJANGO_ALLOWED_HOSTS` | `api.yourdomain.com,<the .awsapprunner.com hostname>` |
  | `DATABASE_URL` | `postgresql://pharmalink:<password>@<rds-endpoint>:5432/pharmalink` |
  | `CORS_ALLOWED_ORIGINS` | `https://yourdomain.com` |
  | `CSRF_TRUSTED_ORIGINS` | `https://yourdomain.com` |
  | `SESSION_COOKIE_SECURE` | `true` |
  | `CSRF_COOKIE_SECURE` | `true` |
  | `USE_S3` | `true` |
  | `AWS_STORAGE_BUCKET_NAME` | `pharmalink-prescriptions-prod` |
  | `AWS_S3_REGION_NAME` | `<region>` |
  | `PUBLIC_WEB_BASE_URL` | `https://yourdomain.com` |

  Leave `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` unset - the instance role covers S3 access.

Migrations run automatically on container boot (`docker-entrypoint.sh`) - there's no separate
release step to trigger.

**Custom domain** (optional): App Runner → your service → Custom domains → add
`api.yourdomain.com`, then create the CNAME/validation records it gives you in Route 53 (or
your DNS provider). App Runner provisions and renews the TLS cert for you.

## 5. Amplify Hosting for the web app

1. Amplify console → **Create app** → **Host web app** → connect the GitHub repo, branch `main`.
2. Amplify auto-detects `amplify.yml` at the repo root (already in this repo, configured for the `apps/web` monorepo package). Confirm the app root is `apps/web`.
3. Environment variables (Amplify → App settings → Environment variables):

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | `https://api.yourdomain.com/api` |

4. Deploy. Amplify builds and serves the Next.js app (SSR) behind its own CDN/HTTPS.
5. **Custom domain** (optional): Amplify → Domain management → add `yourdomain.com`; it walks you through the Route 53 records and provisions the cert.

Once both domains are live, go back and tighten `CORS_ALLOWED_ORIGINS` /
`CSRF_TRUSTED_ORIGINS` / `DJANGO_ALLOWED_HOSTS` on the API to the real custom domains (drop
any `*.awsapprunner.com`/`*.amplifyapp.com` placeholders you used to get the first deploy working).

## 6. Verify

```bash
curl https://api.yourdomain.com/api/  # or the *.awsapprunner.com URL if no custom domain yet
```

Then open the web app, log in, and confirm a prescription upload round-trips (this is the
one thing that only works end-to-end once S3 + the instance role are both correct).

To seed demo data against the deployed DB, run `python manage.py seed_poc` from a machine
that can reach RDS - easiest is temporarily adding your IP to the RDS security group and
pointing `DATABASE_URL` at the endpoint from your local `.venv`, then reverting the security
group rule.

## 7. Background scheduler (EventBridge Scheduler + ECS Fargate)

`python manage.py run_scheduler` (see `apps/orders/management/commands/run_scheduler.py`)
expires stale stock holds, generates due recurring orders, releases scheduled orders into
the dispatch pool, optionally re-plans routes, and delivers pending outgoing webhooks. It
needs to run on a timer somewhere. App Runner has no native cron or background-loop support
- every App Runner instance only ever serves HTTP, and there is no "worker" instance type -
so this cannot live on the same service as the API. The `scheduler` service in
`docker-compose.yml` covers local/self-hosted deployments (it loops forever with
`--loop --plan`); in AWS the equivalent is a **scheduled ECS Fargate task**, invoked by
**EventBridge Scheduler** on a fixed interval, running a single pass (no `--loop` - the
schedule itself provides the periodicity).

This section documents the approach; it is not automated (no Terraform/CDK exists in this
repo to extend, matching the manual-console-plus-CLI style of the rest of this guide).

**Reuse the same image** already pushed to ECR in step 3 - no separate build.

**ECS cluster** (a cheap Fargate-only cluster, no EC2 capacity to manage):

```bash
aws ecs create-cluster --cluster-name pharmalink
```

**Task execution role** (lets ECS pull the image and write logs) and **task role** (what the
container itself can do - same S3 access as the App Runner instance role, since the
scheduler's webhook/notification paths don't touch S3 but staying consistent is simplest):

```bash
aws iam create-role --role-name pharmalink-ecs-execution \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name pharmalink-ecs-execution \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam create-role --role-name pharmalink-scheduler-task \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
```

**Task definition** (`scheduler-task-def.json`) - same `DATABASE_URL`/`DJANGO_SECRET_KEY`/etc.
as the App Runner service, plus a `command` override so the container runs the scheduler
pass instead of gunicorn:

```json
{
  "family": "pharmalink-scheduler",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/pharmalink-ecs-execution",
  "taskRoleArn": "arn:aws:iam::<account-id>:role/pharmalink-scheduler-task",
  "containerDefinitions": [
    {
      "name": "scheduler",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/pharmalink-api:latest",
      "command": ["python", "manage.py", "run_scheduler", "--plan"],
      "environment": [
        {"name": "DJANGO_DEBUG", "value": "false"},
        {"name": "DATABASE_URL", "value": "postgresql://pharmalink:<password>@<rds-endpoint>:5432/pharmalink"},
        {"name": "PUBLIC_WEB_BASE_URL", "value": "https://yourdomain.com"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {"awslogs-group": "/ecs/pharmalink-scheduler", "awslogs-region": "<region>", "awslogs-stream-prefix": "scheduler"}
      }
    }
  ]
}
```

Put `DJANGO_SECRET_KEY` and the DB password in Secrets Manager and reference them via
`secrets` instead of plaintext `environment`, same as the security checklist below asks for
the App Runner service.

```bash
aws logs create-log-group --log-group-name /ecs/pharmalink-scheduler
aws ecs register-task-definition --cli-input-json file://scheduler-task-def.json
```

**EventBridge Scheduler rule**, firing the task on a fixed interval (every 5 minutes here -
match whatever `--every` you'd otherwise pass to `--loop`):

```bash
aws scheduler create-schedule \
  --name pharmalink-scheduler-tick \
  --schedule-expression "rate(5 minutes)" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target '{
    "Arn": "arn:aws:ecs:<region>:<account-id>:cluster/pharmalink",
    "RoleArn": "arn:aws:iam::<account-id>:role/pharmalink-scheduler-invoke",
    "EcsParameters": {
      "TaskDefinitionArn": "arn:aws:ecs:<region>:<account-id>:task-definition/pharmalink-scheduler",
      "LaunchType": "FARGATE",
      "NetworkConfiguration": {
        "awsvpcConfiguration": {
          "Subnets": ["<subnet-1>", "<subnet-2>"],
          "SecurityGroups": ["<sg-that-can-reach-rds>"],
          "AssignPublicIp": "DISABLED"
        }
      }
    }
  }'
```

`pharmalink-scheduler-invoke` is a small role EventBridge Scheduler assumes to call
`ecs:RunTask`, trusted to `scheduler.amazonaws.com` and scoped to `RunTask` on that one task
definition plus `iam:PassRole` for the two roles above - create it the same way as the other
roles in this guide.

Each firing runs one pass and exits; there is nothing long-running to monitor beyond the
task's CloudWatch Logs (`/ecs/pharmalink-scheduler`) and EventBridge Scheduler's own
invocation history/dead-letter queue if you configure one.

## Updating a deployed environment

- **API**: rebuild/tag/push the image (step 3), then App Runner → Deploy (or enable
  automatic deployments on the ECR image repository so a push triggers it).
- **Web**: push to the connected branch - Amplify redeploys automatically.
- **Migrations**: ship with the API image and apply themselves on boot. Review any
  destructive migration (dropping a column/table) manually before deploying it - the
  auto-migrate-on-boot pattern is a convenience for additive changes, not a safety net.

## Security checklist before going live

- [ ] `DJANGO_DEBUG=false`, `SESSION_COOKIE_SECURE=true`, `CSRF_COOKIE_SECURE=true`
- [ ] RDS not publicly accessible; security group only allows the App Runner VPC connector
- [ ] S3 bucket has Block Public Access on, no public bucket policy
- [ ] `DJANGO_SECRET_KEY` is a real random value, stored in Secrets Manager, not plaintext in git or in this doc
- [ ] `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` / `DJANGO_ALLOWED_HOSTS` list only your real domains
- [ ] `EMAIL_BACKEND` pointed at a real SMTP provider (prescription QR emails are still going to the console log otherwise)
