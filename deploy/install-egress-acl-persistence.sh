#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "run this installer as root" >&2
  exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
agens_web_dir=${AGENS_WEB_DIR:-$(CDPATH= cd -- "$script_dir/.." && pwd)}
template="$script_dir/systemd/agens-web-egress-acl.service"
module_config="$script_dir/systemd/agens-web-br-netfilter.conf"

[ -f "$script_dir/apply-egress-acl.sh" ] || {
  echo "apply-egress-acl.sh is missing" >&2
  exit 1
}
[ -f "$script_dir/wait-for-egress-runtime.sh" ] || {
  echo "wait-for-egress-runtime.sh is missing" >&2
  exit 1
}
[ -f "$template" ] && [ -f "$module_config" ] || {
  echo "systemd persistence assets are incomplete" >&2
  exit 1
}

escaped_dir=$(printf '%s' "$agens_web_dir" | sed 's/[&|\\]/\\&/g')
temp_unit=$(mktemp)
trap 'rm -f "$temp_unit"' EXIT HUP INT TERM
sed "s|@AGENS_WEB_DIR@|$escaped_dir|g" "$template" > "$temp_unit"

install -D -m 0644 "$module_config" /etc/modules-load.d/agens-web-br-netfilter.conf
install -D -m 0644 "$temp_unit" /etc/systemd/system/agens-web-egress-acl.service
systemctl daemon-reload
systemctl enable --now agens-web-egress-acl.service
systemctl is-active --quiet agens-web-egress-acl.service
