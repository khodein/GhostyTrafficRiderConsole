#!/bin/sh
# Baked into the image and run as the container's entrypoint every time it starts.
# Expects /data/secret, /data/proxy-secret and /data/proxy-multi.conf
# (prepared by remote/install.sh) and MTPROXY_PORT / MTPROXY_TLS_DOMAIN in env.

echo "Container startup"

SECRET=$(cat /data/secret 2>/dev/null)
if [ -z "$SECRET" ]; then
  echo "ERROR: /data/secret not found - run install.sh first"
  exec tail -f /dev/null
fi

DOMAIN_ARG=""
if [ -n "$MTPROXY_TLS_DOMAIN" ]; then
  DOMAIN_ARG="--domain $MTPROXY_TLS_DOMAIN"
fi

# Inside docker the container IP differs from the public one; without
# --nat-info the relay gets no downstream bytes from Telegram DCs.
NAT_ARG=""
INTERNAL_IP=$(hostname -i 2>/dev/null | awk '{print $1}')
if [ -n "$MTPROXY_PUBLIC_IP" ] && [ -n "$INTERNAL_IP" ] && [ "$INTERNAL_IP" != "$MTPROXY_PUBLIC_IP" ]; then
  NAT_ARG="--nat-info ${INTERNAL_IP}:${MTPROXY_PUBLIC_IP}"
fi

# shellcheck disable=SC2086
exec mtproto-proxy \
  -u root \
  -p 2398 \
  -H "${MTPROXY_PORT}" \
  -S "${SECRET}" \
  --aes-pwd /data/proxy-secret \
  -M 1 \
  -C 60000 \
  --allow-skip-dh \
  ${NAT_ARG} \
  ${DOMAIN_ARG} \
  /data/proxy-multi.conf
