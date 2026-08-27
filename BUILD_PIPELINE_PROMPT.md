# Execution prompt — PharmaLink CI/CD

Build the CI/CD pipeline for this repo. The app is ALREADY LIVE and serving real traffic —
every change must keep it that way. Work phase by phase, and stop for my approval before
anything that touches the running service or the database.

## Verified environment (do not re-derive, but do re-verify before you change anything)

- AWS account `423401347463`, region **`eu-central-1`**. My CLI default is `us-east-1` —
  pass `--region eu-central-1` explicitly everywhere or you will create empty resources
  in the wrong region.
- API: ECS **Express Mode** service `pharmalink-api` on cluster `default`.
  ARN `arn:aws:ecs:eu-central-1:423401347463:service/default/pharmalink-api`.
  1 vCPU / 2 GB, autoscale 1–3 on 60% CPU, health path `/api/health/`, container port 8080.
  Image is pinned **by digest** — keep it that way, rollback depends on it.
  Public URL `https://ph-dfe6101ee62a4136ab991c2944576b6d.ecs.eu-central-1.on.aws`.
- Web: Amplify app `d11grhcyzvk01x` (`pharma-link`), branch `main`, SSR (WEB_COMPUTE),
  monorepo root `apps/web`, custom domain `healthconnect.dev` attached and serving.
  Auto-build is ON.
- ECR: `pharmalink-api` in eu-central-1. No lifecycle policy.
- DB: RDS `database-1`, Postgres 16, `PubliclyAccessible: true`, SG `sg-0c7f374bd10d50452`
  admits 5432 from `185.84.106.238/32` and from task SG `sg-09239269d18019b99`.
- Secrets: `DATABASE_URL` and `DJANGO_SECRET_KEY` already come from Secrets Manager.
  Never print, echo, or fetch their values. Reference them by ARN only.
- Task/exec role: `pharmalink-ecs-task-role`. Subnets `subnet-0fb1407cfa6c4767e`,
  `subnet-095d07bde4fb4d8d6`. Task SGs `sg-09239269d18019b99`, `sg-0e42684ae52970a3e`.
- GitHub: `kofdarc/pharma-link`, default branch `main`. No `.github/workflows` yet,
  no GitHub OIDC provider in IAM.

## Non-negotiable constraints

1. **Never touch `apps/api/test.sqlite3`.** It is the shared live dev database despite the
   name. See CLAUDE.md.
2. **Do not start a second `next dev` against `apps/web`.** Shared `.next` cache. See CLAUDE.md.
3. Other sessions may be working in this tree. Nothing destructive without asking.
4. No long-lived AWS access keys in GitHub. OIDC only.
5. Do not `get-secret-value` on anything. Load the `aws-secrets-manager` skill if you need
   to handle a secret.
6. Prefer the AWS MCP server over raw CLI where it covers the call.
7. Use the AWS skills (`aws-deployment`, `aws-containers`) rather than recalling API shapes
   from memory. Verify any API parameter you are unsure of against the docs.
8. Commit to a branch and open a PR. Do not push to `main`.

## Phase 0 — Foundations

- Register the GitHub OIDC provider:
  `aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com`
- Create role `pharmalink-gha-deploy`, trust policy conditioned on
  `token.actions.githubusercontent.com:sub` = `repo:kofdarc/pharma-link:ref:refs/heads/main`
  and `repo:kofdarc/pharma-link:environment:production`, audience `sts.amazonaws.com`.
  Scope the inline policy to exactly:
  - `ecr:GetAuthorizationToken` on `*`
  - ECR push/pull actions on the `pharmalink-api` repository ARN only
  - `ecs:RegisterTaskDefinition` (resource `*`, it does not support ARN scoping)
  - `ecs:RunTask` + `ecs:DescribeTasks` scoped to the `pharmalink-oneoff` family
  - `ecs:UpdateExpressGatewayService` + `ecs:DescribeExpressGatewayService` on the one
    service ARN
  - `iam:PassRole` on `pharmalink-ecs-task-role`, conditioned to `ecs-tasks.amazonaws.com`
  - `amplify:StartJob` + `amplify:GetJob` on the app ARN
  The CI workflow needs no AWS access at all — do not give it a role.
- Add an ECR lifecycle policy: expire untagged after 1 day, keep the last 20 tagged.
- **Ask me before** modifying RDS. The intended change is `--no-publicly-accessible` plus
  dropping the `185.84.106.238/32` rule, but tell me first how I get emergency psql access
  afterwards.

Report the role ARN when done — I have to add it to GitHub myself.

## Phase 1 — CI gate: `.github/workflows/ci.yml`

Triggers: `pull_request`, and `push` to `main`. Jobs run in parallel.

- **`api-tests`** — Python 3.12 with pip cache. apt-install `tesseract-ocr`,
  `tesseract-ocr-fra`, `tesseract-ocr-ara`, `poppler-utils`.
  Create `apps/api/requirements-ci.txt` = `requirements.txt` minus the `easyocr` line.
  This is safe: `easyocr` is imported lazily inside a function
  (`apps/prescriptions/services/ocr/easyocr_provider.py:33`) and the default provider is
  tesseract (`config/settings.py:257`). It saves a multi-GB torch install per run.
  Run `DJANGO_TEST_SQLITE=1 python manage.py test`.
- **`api-tests-postgres`** — same, but with a `postgres:16` service container and a real
  `DATABASE_URL`. This exists because `apps/medicines/migrations/0006_trigram_search_indexes.py`
  explicitly no-ops on non-Postgres backends, so the SQLite job never exercises the only
  code path production actually uses.
- **`migrations`** — `manage.py makemigrations --check --dry-run` and
  `manage.py check --deploy`. Then diff the migration files added versus `origin/main` and
  grep for `RemoveField`, `DeleteModel`, `AlterField`; set a job output
  `destructive=true|false`. Phase 2 consumes this.
- **`web`** — `pnpm install --frozen-lockfile`, `npx tsc --noEmit`, `pnpm lint`, `pnpm build`.
  The build is the real gate: it is the same command Amplify runs.

Tell me which checks to mark required in branch protection. Do not change repo settings
yourself.

## Phase 2 — API delivery: `.github/workflows/deploy-api.yml`

Trigger: `push` to `main` under `apps/api/**`, plus `workflow_dispatch`.

1. Assume the OIDC role. `AWS_REGION: eu-central-1`.
2. Buildx build of `apps/api` with registry cache
   (`--cache-from`/`--cache-to type=registry,ref=...:buildcache`). Tag `${{ github.sha }}`
   and `latest`. Push. Capture the image **digest**.
3. Capture the CURRENTLY deployed digest first, into a job output — rollback needs it.
4. If phase 1 flagged `destructive=true`, require a GitHub `production` environment
   approval before continuing.
5. **Migrate as its own step.** Register a new `pharmalink-oneoff` task definition revision
   at the new digest, with `entryPoint: []` and
   `command: ["python","manage.py","migrate","--noinput"]`.
   **This override is mandatory** — `docker-entrypoint.sh` ignores its arguments and always
   runs migrate then gunicorn, so without it the task never exits, the wait times out, and
   the migration you think you gated on never ran as a distinct step. The existing revision 1
   of that family has exactly this bug.
   `run-task` in the service's subnets/SGs, `aws ecs wait tasks-stopped`, then assert the
   container `exitCode` is 0. Fail the deploy if it is not.
6. `aws ecs update-express-gateway-service --service-arn <arn> --primary-container image=<digest>`.
   Poll `describe-express-gateway-service` until the new service revision is active.
7. Smoke test: `curl -f https://ph-dfe6101ee62a4136ab991c2944576b6d.ecs.eu-central-1.on.aws/api/health/`
   with retries. Expect `{"status":"ok"}`.
8. On failure of 6 or 7: re-run `update-express-gateway-service` with the digest from step 3,
   then fail the workflow loudly. Note in the job summary that a rollback does NOT revert a
   migration that already applied.
9. **Only after a green end-to-end run**, remove `python manage.py migrate --noinput` from
   `apps/api/docker-entrypoint.sh` in a follow-up commit. Leaving both in place reintroduces
   the boot race this phase exists to remove.

Dry-run the whole workflow with `workflow_dispatch` on a no-op commit before it ever fires
automatically. Show me the run before you consider this done.

## Phase 3 — Web delivery

Start with the cheap option: leave Amplify auto-build ON. Branch protection from phase 1
already means only tested code reaches `main`.

Then tell me whether to switch to pipeline-driven releases —
`aws amplify start-job --app-id d11grhcyzvk01x --branch-name main --job-type RELEASE --commit-id $GITHUB_SHA`
after the API is healthy — which buys lockstep ordering at the cost of one more moving part.

Either way, enable Amplify pull request previews.

## Phase 4 — Approval gate

Do the fifteen-minute version, not a staging tier: a GitHub `production` environment with me
as required reviewer, required by the deploy job only when the destructive-migration flag is
set. Routine additive deploys stay fully automatic.

## Phase 5 — The missing scheduler

There is **no EventBridge schedule or rule in any region** and no Lambda — `run_scheduler`
has never been deployed. In production right now, stock holds never expire, recurring orders
never generate, scheduled orders never release, and outgoing webhooks never deliver.

- Create a `pharmalink-scheduler` task definition on the same image, `entryPoint: []`,
  `command: ["python","manage.py","run_scheduler","--plan"]` (no `--loop` — the schedule
  provides the periodicity), 256 CPU / 512 memory, log group `/ecs/pharmalink-scheduler`,
  secrets by ARN.
- EventBridge Scheduler `rate(5 minutes)` targeting `ecs:RunTask` on it, with its own
  invoke role and a dead-letter queue.
- Have `deploy-api.yml` register a new revision of this task definition on every release so
  it cannot drift onto a stale image.
- Verify one firing actually ran and exited 0 before you call it done.

Then add CloudWatch alarms on ECS task restart count and ALB 5xx rate, and rewrite
`docs/DEPLOY_AWS.md` — it currently documents an App Runner architecture that is not running
and that AWS closed to new customers on 2026-04-30. It should describe ECS Express Mode, the
pipeline, and how to do a manual emergency deploy when the pipeline is down.

## Reporting

After each phase: what you changed, what you verified and how, and anything you found that
contradicts the notes above. If a claim in this prompt turns out to be wrong when you check
it, say so and stop rather than working around it.
