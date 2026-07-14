#!/bin/sh
set -eu

compose_file=${COMPOSE_FILE:-deploy/docker-compose.yml}
project=${COMPOSE_PROJECT_NAME:-agens-web}
chain=AGENS_WEB_EGRESS

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 1; }
command -v iptables >/dev/null 2>&1 || { echo "iptables is required" >&2; exit 1; }
command -v modprobe >/dev/null 2>&1 || { echo "modprobe is required" >&2; exit 1; }
command -v sysctl >/dev/null 2>&1 || { echo "sysctl is required" >&2; exit 1; }

modprobe br_netfilter
sysctl -q -w net.bridge.bridge-nf-call-iptables=1
[ "$(sysctl -n net.bridge.bridge-nf-call-iptables)" = 1 ] || {
  echo "bridge netfilter must be enabled" >&2
  exit 1
}

app_id=$(docker compose -p "$project" -f "$compose_file" ps -q agens-web)
proxy_id=$(docker compose -p "$project" -f "$compose_file" ps -q egress-proxy)
redis_id=$(docker compose -p "$project" -f "$compose_file" ps -q redis)
[ -n "$app_id" ] && [ -n "$proxy_id" ] && [ -n "$redis_id" ] || {
  echo "agens-web, egress-proxy and redis must be running" >&2
  exit 1
}

app_ips=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$app_id")
proxy_ips=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$proxy_id")
redis_ips=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$redis_id")
db_host=$(docker exec "$app_id" python -c 'import os; print(os.environ.get("AGENS_DB_HOST_FOR_ACL", ""))')
[ -n "$db_host" ] || { echo "AGENS_DB_HOST_FOR_ACL is required" >&2; exit 1; }
db_port=$(docker exec "$app_id" python -c 'import os; print(os.environ.get("AGENS_DB_PORT_FOR_ACL", "5432"))')
case "$db_port" in
  ""|*[!0-9]*) echo "AGENS_DB_PORT_FOR_ACL must be numeric" >&2; exit 1 ;;
esac
[ "$db_port" -ge 1 ] && [ "$db_port" -le 65535 ] || {
  echo "AGENS_DB_PORT_FOR_ACL must be between 1 and 65535" >&2
  exit 1
}
db_ips=$(docker exec "$app_id" python -c 'import socket,sys; print(" ".join(sorted({item[4][0] for item in socket.getaddrinfo(sys.argv[1], int(sys.argv[2]), type=socket.SOCK_STREAM)})))' "$db_host" "$db_port")
[ -n "$app_ips" ] && [ -n "$proxy_ips" ] && [ -n "$redis_ips" ] && [ -n "$db_ips" ] || {
  echo "failed to resolve container ACL addresses" >&2
  exit 1
}

iptables -N "$chain" 2>/dev/null || true
iptables -F "$chain"

for app_ip in $app_ips; do
  iptables -A "$chain" -s "$app_ip" -m conntrack --ctstate ESTABLISHED,RELATED --ctdir REPLY -j ACCEPT
  for proxy_ip in $proxy_ips; do
    iptables -A "$chain" -s "$app_ip" -d "$proxy_ip" -p tcp --dport 3128 -j ACCEPT
  done
  for redis_ip in $redis_ips; do
    iptables -A "$chain" -s "$app_ip" -d "$redis_ip" -p tcp --dport 6379 -j ACCEPT
  done
  for db_ip in $db_ips; do
    iptables -A "$chain" -s "$app_ip" -d "$db_ip" -p tcp --dport "$db_port" -j ACCEPT
  done
  iptables -A "$chain" -s "$app_ip" -j REJECT
done

iptables -A "$chain" -j RETURN
while iptables -C DOCKER-USER -j "$chain" 2>/dev/null; do
  iptables -D DOCKER-USER -j "$chain"
done
iptables -I DOCKER-USER 1 -j "$chain"
echo "agens-web outbound ACL applied"
