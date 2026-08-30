#!/usr/bin/env bash
# Register and run a one-off Fargate task that fetches missing medicine images
# on prod. The task runs inside the VPC where RDS is reachable and the ECS task
# role has S3 write access.
#
# Prerequisites:
#   - The API image must be deployed (fetch_missing_medicine_images.py exists)
#   - AWS CLI configured with credentials that can register ECS tasks and run them
#
# Usage:
#   export AWS_REGION=eu-central-1
#   export ECS_CLUSTER=default
#   export SERVICE_ARN=arn:aws:ecs:eu-central-1:423401347463:service/default/pharmalink-api
#   export ECS_SUBNETS=subnet-...,subnet-...
#   export ECS_SECURITY_GROUPS=sg-...,sg-...
#   export IMAGE=<ecr-uri>@sha256:<digest>
#
#   bash .github/scripts/run-image-fetch-task.sh
#   bash .github/scripts/run-image-fetch-task.sh --limit 10          # pilot
#   bash .github/scripts/run-image-fetch-task.sh --abort-after 20    # safe
#
# The IMAGE env var is the fully qualified ECR URI with digest (not tag) of the
# API image currently deployed. You can get it from the CI deploy summary or:
#   aws ecs describe-express-gateway-service \
#     --service-arn "$SERVICE_ARN" --region "$AWS_REGION" \
#     --query 'service.activeConfigurations[0].primaryContainer.image' --output text
set -euo pipefail

: "${AWS_REGION:?}"
: "${ECS_CLUSTER:?}"
: "${SERVICE_ARN:?}"
: "${ECS_SUBNETS:?}"
: "${ECS_SECURITY_GROUPS:?}"
: "${IMAGE:?}"

EXTRA_ARGS=("$@")

# Pull the service's environment, secrets, and roles so the one-off task has the
# same database, S3, and LLM config as the running API.
service_json="$(aws ecs describe-express-gateway-service \
  --region "$AWS_REGION" \
  --service-arn "$SERVICE_ARN")"

task_role="$(jq -er '.service.activeConfigurations[0].taskRoleArn' <<<"$service_json")"
execution_role="$(jq -er '.service.activeConfigurations[0].executionRoleArn' <<<"$service_json")"
environment="$(jq -c '.service.activeConfigurations[0].primaryContainer.environment // []' <<<"$service_json")"
secrets="$(jq -c '.service.activeConfigurations[0].primaryContainer.secrets // []' <<<"$service_json")"

TASK_FAMILY="pharmalink-image-fetch"

jq -n \
  --arg image "$IMAGE" \
  --arg task_role "$task_role" \
  --arg execution_role "$execution_role" \
  --arg region "$AWS_REGION" \
  --argjson environment "$environment" \
  --argjson secrets "$secrets" \
  --argjson extra_args "$(printf '%s\n' "${EXTRA_ARGS[@]}" | jq -R . | jq -s .)" \
  '{
    family: $family,
    networkMode: "awsvpc",
    requiresCompatibilities: ["FARGATE"],
    cpu: "1024",
    memory: "2048",
    taskRoleArn: $task_role,
    executionRoleArn: $execution_role,
    runtimePlatform: {cpuArchitecture: "X86_64", operatingSystemFamily: "LINUX"},
    containerDefinitions: [{
      name: "Main",
      image: $image,
      essential: true,
      entryPoint: ["python"],
      command: (["manage.py", "fetch_missing_medicine_images"] + $extra_args),
      environment: $environment,
      secrets: $secrets,
      logConfiguration: {
        logDriver: "awslogs",
        options: {
          "awslogs-group": "/aws/ecs/default/pharmalink-api-197d",
          "awslogs-region": $region,
          "awslogs-stream-prefix": "image-fetch"
        }
      }
    }]
  }' --arg family "$TASK_FAMILY" > /tmp/pharmalink-image-fetch.json

task_def_arn="$(aws ecs register-task-definition \
  --region "$AWS_REGION" \
  --cli-input-json file:///tmp/pharmalink-image-fetch.json \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)"

echo "Registered task definition: $task_def_arn"

network_configuration="awsvpcConfiguration={subnets=[$ECS_SUBNETS],securityGroups=[$ECS_SECURITY_GROUPS],assignPublicIp=ENABLED}"

task_arn="$(aws ecs run-task \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER" \
  --launch-type FARGATE \
  --task-definition "$task_def_arn" \
  --network-configuration "$network_configuration" \
  --query 'tasks[0].taskArn' \
  --output text)"

if [[ -z "$task_arn" || "$task_arn" == "None" ]]; then
  echo "ECS did not start the image-fetch task" >&2
  exit 1
fi

echo "Image fetch task started: $task_arn"
echo "Monitor logs:"
echo "  aws logs tail /aws/ecs/default/pharmalink-api-197d --since 5m --region $AWS_REGION --follow"
echo ""
echo "Waiting for task to stop (this may take hours for a full run)..."

aws ecs wait tasks-stopped --region "$AWS_REGION" --cluster "$ECS_CLUSTER" --tasks "$task_arn"

task_json="$(aws ecs describe-tasks \
  --region "$AWS_REGION" \
  --cluster "$ECS_CLUSTER" \
  --tasks "$task_arn")"
exit_code="$(jq -er '.tasks[0].containers[] | select(.name == "Main") | .exitCode' <<<"$task_json")"

if [[ "$exit_code" != "0" ]]; then
  echo "Image fetch task failed (exit code $exit_code)" >&2
  jq -r '.tasks[0] | {stoppedReason, containers: [.containers[] | {name, exitCode, reason}]}' <<<"$task_json" >&2
  exit 1
fi

echo "Image fetch task completed successfully."
