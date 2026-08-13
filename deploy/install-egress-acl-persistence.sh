#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "run this installer as root" >&2
  exit 1
fi

usage() {
  echo "usage: $0 --compose-project NAME --compose-file ABSOLUTE_PATH" >&2
  exit 2
}

compose_project=""
compose_file=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --compose-project)
      [ "$#" -ge 2 ] || usage
      compose_project=$2
      shift 2
      ;;
    --compose-file)
      [ "$#" -ge 2 ] || usage
      compose_file=$2
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

case "$compose_project" in
  ""|*[!A-Za-z0-9_.-]*) usage ;;
esac
case "$compose_file" in
  /*) ;;
  *) usage ;;
esac
[ -f "$compose_file" ] || {
  echo "compose file is missing" >&2
  exit 1
}

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
escaped_project=$(printf '%s' "$compose_project" | sed 's/[&|\\]/\\&/g')
escaped_compose_file=$(printf '%s' "$compose_file" | sed 's/[&|\\]/\\&/g')
temp_unit=$(mktemp)
trap 'rm -f "$temp_unit"' EXIT HUP INT TERM
sed \
  -e "s|@AGENS_WEB_DIR@|$escaped_dir|g" \
  -e "s|@AGENS_COMPOSE_PROJECT@|$escaped_project|g" \
  -e "s|@AGENS_COMPOSE_FILE@|$escaped_compose_file|g" \
  "$template" > "$temp_unit"

grep -Fq '@AGENS_' "$temp_unit" && {
  echo "systemd template substitution failed" >&2
  exit 1
}

install -D -m 0644 "$module_config" /etc/modules-load.d/agens-web-br-netfilter.conf
install -D -m 0644 "$temp_unit" /etc/systemd/system/agens-web-egress-acl.service
systemctl daemon-reload
systemctl enable --now agens-web-egress-acl.service
systemctl is-active --quiet agens-web-egress-acl.service
