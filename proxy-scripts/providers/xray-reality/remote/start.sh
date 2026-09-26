#!/bin/bash
# Adapted from AmneziaVPN's server_scripts/xray/start.sh. Baked into the
# image and run as the container's entrypoint every time it starts.
set -e

echo "Container startup"

iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p icmp -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport "$XRAY_SERVER_PORT" -j ACCEPT
iptables -A INPUT -p udp --dport "$XRAY_SERVER_PORT" -j ACCEPT
iptables -P INPUT DROP

ip6tables -A INPUT -i lo -j ACCEPT
ip6tables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
ip6tables -A INPUT -p ipv6-icmp -j ACCEPT
ip6tables -P INPUT DROP

killall -KILL xray 2>/dev/null || true

if [ -f /opt/amnezia/xray/server.json ]; then
  xray -config /opt/amnezia/xray/server.json &
fi

tail -f /dev/null
