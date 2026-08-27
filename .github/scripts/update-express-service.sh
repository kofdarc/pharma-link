#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?}"
: "${SERVICE_ARN:?}"
: "${IMAGE:?}"

aws ecs update-express-gateway-service \
  --region "$AWS_REGION" \
  --service-arn "$SERVICE_ARN" \
  --primary-container "image=$IMAGE" \
  >/dev/null

for attempt in {1..60}; do
  service_json="$(aws ecs describe-express-gateway-service \
    --region "$AWS_REGION" \
    --service-arn "$SERVICE_ARN")"
  status="$(jq -r '.service.status.statusCode' <<<"$service_json")"
  active="$(jq -r --arg image "$IMAGE" '[.service.activeConfigurations[]? | select(.primaryContainer.image == $image)] | length' <<<"$service_json")"
  if [[ "$status" == "ACTIVE" && "$active" -gt 0 ]]; then
    exit 0
  fi
  if [[ "$status" == "INACTIVE" || "$status" == "DELETE_FAILED" ]]; then
    echo "ECS Express service entered terminal status $status" >&2
    exit 1
  fi
  sleep 10
done

echo "Timed out waiting for ECS Express service to activate $IMAGE" >&2
exit 1
