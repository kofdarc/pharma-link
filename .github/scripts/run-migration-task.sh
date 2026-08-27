#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?}"
: "${CLUSTER:?}"
: "${TASK_DEFINITION:?}"
: "${SUBNETS:?}"
: "${SECURITY_GROUPS:?}"

network_configuration="awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUPS],assignPublicIp=ENABLED}"
task_arn="$(aws ecs run-task \
  --region "$AWS_REGION" \
  --cluster "$CLUSTER" \
  --launch-type FARGATE \
  --task-definition "$TASK_DEFINITION" \
  --network-configuration "$network_configuration" \
  --query 'tasks[0].taskArn' \
  --output text)"

if [[ -z "$task_arn" || "$task_arn" == "None" ]]; then
  echo "ECS did not start the migration task" >&2
  exit 1
fi

echo "Migration task: $task_arn"
aws ecs wait tasks-stopped --region "$AWS_REGION" --cluster "$CLUSTER" --tasks "$task_arn"

task_json="$(aws ecs describe-tasks \
  --region "$AWS_REGION" \
  --cluster "$CLUSTER" \
  --tasks "$task_arn")"
exit_code="$(jq -er '.tasks[0].containers[] | select(.name == "Main") | .exitCode' <<<"$task_json")"
if [[ "$exit_code" != "0" ]]; then
  jq -r '.tasks[0] | {stoppedReason, containers: [.containers[] | {name, exitCode, reason}]}' <<<"$task_json" >&2
  exit 1
fi
