#!/bin/sh
set -eu

config=/tmp/squid.conf

cat >"$config" <<'EOF'
http_port 3128
pid_filename /tmp/squid.pid
cache deny all
cache_mem 16 MB
maximum_object_size 0 KB
access_log stdio:/dev/stdout
cache_log stdio:/dev/stderr
via off
forwarded_for delete

acl CONNECT method CONNECT
acl SSL_ports port 443
acl private_dst dst 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8
acl private_dst dst 169.254.0.0/16 172.16.0.0/12 192.0.0.0/24 192.168.0.0/16
acl private_dst dst 192.0.2.0/24 192.31.196.0/24 192.52.193.0/24 192.88.99.0/24
acl private_dst dst 192.175.48.0/24 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24
acl private_dst dst 224.0.0.0/4 240.0.0.0/4 ::/128 ::1/128 fc00::/7 fe80::/10
acl private_dst dst ::ffff:0:0/96 64:ff9b::/96 100::/64 2001::/23 2001:db8::/32
acl private_dst dst 2002::/16 ff00::/8
EOF

for host in apihub.agnes-ai.com api.deepseek.com dashscope.aliyuncs.com open.bigmodel.cn; do
  printf 'acl model_hosts dstdomain %s\n' "$host" >>"$config"
done

old_ifs=$IFS
IFS=,
for raw in ${AGENS_MODEL_BASE_URL_ALLOWLIST:-}; do
  item=$(printf '%s' "$raw" | tr -d '[:space:]')
  [ -n "$item" ] || continue
  case "$item" in
    *:443) host=${item%:443} ;;
    *:*) echo "invalid model allowlist port" >&2; exit 1 ;;
    *) host=$item ;;
  esac
  case "$host" in
    ""|.*|*..*|*[!A-Za-z0-9.-]*) echo "invalid model allowlist host" >&2; exit 1 ;;
  esac
  printf 'acl model_hosts dstdomain %s\n' "$host" >>"$config"
done
IFS=$old_ifs

cat >>"$config" <<'EOF'
http_access deny !CONNECT
http_access deny !SSL_ports
http_access deny private_dst
http_access allow model_hosts
http_access deny all
EOF

exec squid -N -f "$config"
