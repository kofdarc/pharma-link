#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?}"
: "${SERVICE_ARN:?}"
: "${IMAGE:?}"

service_json="$(aws ecs describe-express-gateway-service \
  --region "$AWS_REGION" \
  --service-arn "$SERVICE_ARN")"

active_task_definition="$(jq -er '.service.activeConfigurations[0].taskDefinitionArn' <<<"$service_json")"
task_json="$(aws ecs describe-task-definition \
  --region "$AWS_REGION" \
  --task-definition "$active_task_definition")"

task_role="$(jq -er '.taskDefinition.taskRoleArn' <<<"$task_json")"
execution_role="$(jq -er '.taskDefinition.executionRoleArn' <<<"$task_json")"
environment="$(jq -c '.taskDefinition.containerDefinitions[] | select(.name == "Main") | .environment // []' <<<"$task_json")"
secrets="$(jq -c '.taskDefinition.containerDefinitions[] | select(.name == "Main") | .secrets // []' <<<"$task_json")"

jq -n \
  --arg image "$IMAGE" \
  --arg task_role "$task_role" \
  --arg execution_role "$execution_role" \
  --arg region "$AWS_REGION" \
  --argjson environment "$environment" \
  --argjson secrets "$secrets" \
  '{
    family: "pharmalink-oneoff",
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
      entryPoint: [],
      command: ["python", "manage.py", "migrate", "--noinput"],
      environment: $environment,
      secrets: $secrets,
      logConfiguration: {
        logDriver: "awslogs",
        options: {
          "awslogs-group": "/aws/ecs/default/pharmalink-api-197d",
          "awslogs-region": $region,
          "awslogs-stream-prefix": "oneoff"
        }
      }
    }]
  }' > /tmp/pharmalink-oneoff.json

oneoff_arn="$(aws ecs register-task-definition \
  --region "$AWS_REGION" \
  --cli-input-json file:///tmp/pharmalink-oneoff.json \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)"

jq -n \
  --arg image "$IMAGE" \
  --arg task_role "$task_role" \
  --arg execution_role "$execution_role" \
  --arg region "$AWS_REGION" \
  --argjson environment "$environment" \
  --argjson secrets "$secrets" \
  '{
    family: "pharmalink-scheduler",
    networkMode: "awsvpc",
    requiresCompatibilities: ["FARGATE"],
    cpu: "256",
    memory: "512",
    taskRoleArn: $task_role,
    executionRoleArn: $execution_role,
    runtimePlatform: {cpuArchitecture: "X86_64", operatingSystemFamily: "LINUX"},
    containerDefinitions: [{
      name: "scheduler",
      image: $image,
      essential: true,
      entryPoint: [],
      command: ["python", "manage.py", "run_scheduler", "--plan"],
      environment: $environment,
      secrets: $secrets,
      logConfiguration: {
        logDriver: "awslogs",
        options: {
          "awslogs-group": "/ecs/pharmalink-scheduler",
          "awslogs-region": $region,
          "awslogs-stream-prefix": "scheduler"
        }
      }
    }]
  }' > /tmp/pharmalink-scheduler.json

scheduler_arn="$(aws ecs register-task-definition \
  --region "$AWS_REGION" \
  --cli-input-json file:///tmp/pharmalink-scheduler.json \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)"

echo "oneoff=$oneoff_arn" >> "$GITHUB_OUTPUT"
echo "scheduler=$scheduler_arn" >> "$GITHUB_OUTPUT"
