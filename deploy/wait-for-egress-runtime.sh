#!/bin/sh
set -eu

compose_file=${COMPOSE_FILE:-deploy/docker-compose.yml}
project=${COMPOSE_PROJECT_NAME:-agens-web}
attempts=${AGENS_EGRESS_WAIT_ATTEMPTS:-24}
delay_seconds=${AGENS_EGRESS_WAIT_DELAY_SECONDS:-5}

case "$attempts" in
  ""|*[!0-9]*) echo "AGENS_EGRESS_WAIT_ATTEMPTS must be numeric" >&2; exit 1 ;;
esac
case "$delay_seconds" in
  ""|*[!0-9]*) echo "AGENS_EGRESS_WAIT_DELAY_SECONDS must be numeric" >&2; exit 1 ;;
esac

ready=0
attempt=1
while [ "$attempt" -le "$attempts" ]; do
  ready=1
  for service in agens-web egress-proxy redis; do
    container_id=$(docker compose -p "$project" -f "$compose_file" ps -q "$service")
    if [ -z "$container_id" ]; then
      ready=0
      break
    fi
    health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
    if [ "$health" != "healthy" ]; then
      ready=0
      break
    fi
  done
  if [ "$ready" -eq 1 ]; then
    exit 0
  fi
  sleep "$delay_seconds"
  attempt=$((attempt + 1))
done

echo "agens-web runtime services did not become healthy before ACL reapplication" >&2
exit 1
