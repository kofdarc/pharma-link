# PharmaLink production deployment on AWS

PharmaLink runs in AWS account `423401347463`, region `eu-central-1`. Always pass
`--region eu-central-1`; the local AWS CLI default points at another region.

## Production architecture

- **API:** ECS Express Mode service `pharmalink-api` in cluster `default`, exposed at
  `https://ph-dfe6101ee62a4136ab991c2944576b6d.ecs.eu-central-1.on.aws`.
- **API image:** private ECR repository `pharmalink-api`. ECS always receives an image
  URI pinned by `sha256` digest.
- **Database:** RDS PostgreSQL `database-1` is publicly addressable, but its security
  group restricts PostgreSQL to `sg-09239269d18019b99` and the approved `/32`
  operator address. Never allow `0.0.0.0/0` on port 5432.
- **Web:** Amplify SSR app `d11grhcyzvk01x`, branch `main`, serving
  `https://healthconnect.dev` and `https://www.healthconnect.dev`.
- **Scheduler:** EventBridge Scheduler runs the `pharmalink-scheduler` Fargate task every
  five minutes. Failed invocations go to its SQS dead-letter queue.
- **Secrets:** ECS container definitions reference the existing Secrets Manager fields by
  ARN. Do not fetch, print, copy, or place their values in GitHub.

AWS App Runner is not part of this architecture. AWS stopped accepting new App Runner
customers on 2026-04-30; ECS Express Mode is the supported deployment target here.

## GitHub Actions pipeline

### Pull request and main-branch CI

`.github/workflows/ci.yml` runs four required jobs in parallel:

1. `api-tests` runs the Django suite on SQLite.
2. `api-tests-postgres` runs the same suite against PostgreSQL 18, matching production, so PostgreSQL-only
   migrations and indexes are exercised.
3. `migrations` checks for missing migration files, runs Django deployment checks, and
   publishes a `migration-safety-<sha>` artifact. Newly added migrations containing
   `RemoveField`, `DeleteModel`, or `AlterField` are marked destructive.
4. `web` installs the locked pnpm graph, type-checks, lints, and executes the same
   production build used by Amplify.

Mark these four exact check names as required in GitHub branch protection. CI has no AWS
credentials and receives no AWS role.

### API deployment

`.github/workflows/deploy-api.yml` runs for API changes merged to `main` and by manual
dispatch. It waits for the successful CI run for the exact commit and downloads CI's
migration-safety artifact before obtaining AWS credentials.

The workflow then:

1. Assumes `arn:aws:iam::423401347463:role/pharmalink-gha-deploy` through GitHub OIDC.
2. Captures the currently deployed digest for rollback.
3. Builds `apps/api` with a registry-backed BuildKit cache, pushes the commit and `latest`
   tags, and keeps the resulting immutable digest.
4. Registers a `pharmalink-oneoff` task definition with `entryPoint: ["python"]` and the
   command `manage.py migrate --noinput`, bypassing the image's Docker entrypoint.
5. Runs that task in the production VPC, waits for it to stop, and requires exit code 0.
6. Registers the next `pharmalink-scheduler` revision on the same digest.
7. Updates ECS Express Mode to the new digest, waits for the new revision to become active,
   and smoke-tests `/api/health/` for `{"status":"ok"}`.
8. Restores the previous digest if service activation or the smoke test fails.

An image rollback does **not** undo an already-applied database migration. Use forward fixes
for migration problems; do not make rollback migrations automatically.

Routine additive migrations deploy automatically. A destructive migration routes through
the GitHub `production` environment and waits for its required reviewer. Manual deployments
from non-`main` branches also use that environment so their OIDC identity remains tightly
scoped.

Automatic deployment also requires the repository variable
`API_AUTO_DEPLOY_ENABLED=true`. Keep it `false` for the initial pipeline merge because
GitHub cannot dispatch a workflow until its file exists on the default branch. After the
first manual end-to-end run succeeds, set it to `true`.

The release pipeline bypasses `apps/api/docker-entrypoint.sh` for the migration and
scheduler tasks. The entrypoint still performs a compatibility migration during API boot;
remove that command only in the required follow-up commit after the first green end-to-end
deployment. Afterward migrations must remain a distinct ECS one-off task so concurrent API
boots cannot recreate the migration race.

### Web deployment

Amplify branch auto-build remains enabled. Branch protection ensures only commits that pass
the web build reach `main`, then Amplify deploys the SSR application. Pull request previews
are enabled on the `main` branch configuration.

`NEXT_PUBLIC_ENABLE_DEMO_LOGIN=true` adds one-click "log in as" buttons for each seeded
role on `/login`. Set it only on a demo deployment seeded via `seed_poc`, never on one holding
real user data - every seeded account shares a single password.

Pipeline-driven Amplify releases are intentionally not enabled. They would provide lockstep
API-then-web ordering, but add duplicate release orchestration while the applications already
maintain backward-compatible API changes. Reconsider this only when a release genuinely
requires coordinated cutover.

## Scheduler operations

The scheduler task bypasses the image's Docker entrypoint and runs one pass only:

```text
python manage.py run_scheduler --plan
```

Do not add `--loop`; EventBridge Scheduler supplies the five-minute cadence. The task expires
stock holds, generates recurring orders, releases scheduled orders, replans routes, and
delivers pending outgoing webhooks.

Useful checks:

```bash
aws scheduler get-schedule \
  --name pharmalink-scheduler \
  --region eu-central-1

aws ecs list-tasks \
  --cluster default \
  --family pharmalink-scheduler \
  --desired-status STOPPED \
  --region eu-central-1

aws logs tail /ecs/pharmalink-scheduler \
  --since 30m \
  --region eu-central-1
```

Treat any DLQ message as an operational failure. Inspect the scheduler execution and task
logs, correct the underlying issue, and redrive only after confirming the command is safe to
repeat.

## Manual emergency API deployment

Use this only when GitHub Actions is unavailable. Keep the service digest-pinned and record
the previous digest before changing anything.

```bash
export AWS_REGION=eu-central-1
export AWS_ACCOUNT_ID=423401347463
export ECR_REPOSITORY=pharmalink-api
export SERVICE_ARN=arn:aws:ecs:eu-central-1:423401347463:service/default/pharmalink-api

aws ecs describe-express-gateway-service \
  --service-arn "$SERVICE_ARN" \
  --region "$AWS_REGION" \
  --query 'service.activeConfigurations[0].primaryContainer.image' \
  --output text

aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker buildx build apps/api \
  --tag "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:emergency-$(git rev-parse HEAD)" \
  --push

aws ecr describe-images \
  --repository-name "$ECR_REPOSITORY" \
  --image-ids imageTag="emergency-$(git rev-parse HEAD)" \
  --region "$AWS_REGION" \
  --query 'imageDetails[0].imageDigest' \
  --output text
```

Register and run the one-off migration task using the workflow's
`.github/scripts/register-release-task-definitions.sh` and
`.github/scripts/run-migration-task.sh`, then update the service with the complete digest URI:

```bash
aws ecs update-express-gateway-service \
  --service-arn "$SERVICE_ARN" \
  --primary-container \
    "image=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY@sha256:<digest>" \
  --region "$AWS_REGION"

curl --fail --retry 12 --retry-all-errors --retry-delay 10 \
  https://ph-dfe6101ee62a4136ab991c2944576b6d.ecs.eu-central-1.on.aws/api/health/
```

If activation or health checks fail, repeat `update-express-gateway-service` with the
previously recorded digest. Again, this does not reverse migrations.

## Emergency PostgreSQL access

RDS is intentionally not public. For emergency interactive access:

1. Start a short-lived SSM-managed EC2 instance in the database VPC with no inbound rules.
2. Give it a dedicated security group and temporarily allow that group to reach the RDS
   security group on port 5432.
3. Use the Session Manager remote-host port-forwarding document to tunnel a local port to the
   RDS endpoint.
4. Start `psql` through the tunnel with database credentials resolved at runtime through the
   approved `asm-exec` workflow. Never use `secretsmanager get-secret-value`.
5. Terminate the instance and revoke its temporary database rule when finished.

Do not make RDS public or add a workstation IP as the routine emergency-access method.

## Patient notifications (SES + SNS)

When a doctor issues a prescription, `issue_prescription()` delivers it to the patient by
**email** (AWS SES) and, independently, by **SMS** (AWS SNS) when a phone number is on file.
Fax remains the fallback for a failed/absent email only. Both channels default to a
log-only mode, so nothing here is required for the app to run.

### Settings / task-definition environment

| Variable | Value in production | Notes |
| --- | --- | --- |
| `EMAIL_BACKEND` | `apps.common.email_backends.SESEmailBackend` | Sends raw MIME via `sesv2:SendEmail` so the QR-code attachment survives. Unset = Django console backend. |
| `AWS_SES_REGION_NAME` | `eu-central-1` | |
| `SES_CONFIGURATION_SET` | *(optional)* | Set to publish open/click/bounce events. |
| `DEFAULT_FROM_EMAIL` | `HealthConnect <no-reply@healthconnect.dev>` | The address/domain must be a verified SES identity. |
| `SMS_PROVIDER` | `aws_sns` | Unset/`console` = log only. |
| `AWS_SNS_REGION_NAME` | `eu-central-1` | |
| `SMS_SENDER_ID` | *(optional)* | Alphanumeric origination ID; not supported for every destination country. |

boto3 resolves credentials from the ECS task role (same as S3) - no SMTP password or access
key is stored. The task role needs `ses:SendEmail` and `sns:Publish`.

### One-time identity setup

Sender domain identity + Easy DKIM:

```bash
aws sesv2 create-email-identity \
  --email-identity healthconnect.dev \
  --dkim-signing-attributes NextSigningKeyLength=RSA_2048_BIT \
  --region eu-central-1

aws sesv2 get-email-identity --email-identity healthconnect.dev --region eu-central-1
```

Add the three `<token>._domainkey.healthconnect.dev` CNAME records it returns to the domain's
DNS. `DkimAttributes.Status` flips to `SUCCESS` and `VerifiedForSendingStatus` to `true` once
they propagate.

### Sandbox status (as of 2026-08-31)

Account `423401347463` / `eu-central-1` is in **both** the SES sandbox
(`ProductionAccessEnabled: false`, 200 messages/day) and the **SNS SMS sandbox**
(`MonthlySpendLimit: $1`). While sandboxed:

- SES only delivers to verified recipient identities - verify each demo recipient with
  `aws sesv2 create-email-identity --email-identity <addr>` and have them click the link.
- SNS only delivers to verified destination numbers:

  ```bash
  aws sns create-sms-sandbox-phone-number --phone-number +961XXXXXXXX --region eu-central-1
  aws sns verify-sms-sandbox-phone-number  --phone-number +961XXXXXXXX \
    --one-time-password <OTP the phone receives> --region eu-central-1
  ```

- Set the transactional default once:

  ```bash
  aws sns set-sms-attributes --attributes DefaultSMSType=Transactional --region eu-central-1
  ```

Production access for each service is a separate AWS Support case (SES: "Request production
access" in the SES console; SNS: raise the SMS spend limit and exit the SMS sandbox). Neither
is automatable here.

## Monitoring

CloudWatch alarms cover API task replacement/restarts and load-balancer 5xx rate. Error-count
alarms use `treatMissingData=notBreaching`, 60-second periods, and an M-of-N threshold to avoid
paging on a single incomplete data point. Review scheduler logs and its DLQ alongside these
alarms during incidents.
