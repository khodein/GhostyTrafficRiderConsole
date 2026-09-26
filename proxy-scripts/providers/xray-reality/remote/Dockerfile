# Adapted from AmneziaVPN's server_scripts/xray/Dockerfile (GPL, amnezia-server-scripts).
# Self-contained Alpine image with Xray-core - no external base beyond the
# official Xray-core GitHub release.
FROM alpine:3.19
LABEL maintainer="ghosty-traffic-rider-console"

ARG XRAY_RELEASE="v26.7.28"

RUN apk add --no-cache curl unzip bash openssl iptables ip6tables dumb-init

RUN mkdir -p /opt/amnezia/xray
RUN curl -L "https://github.com/XTLS/Xray-core/releases/download/${XRAY_RELEASE}/Xray-linux-64.zip" -o /root/xray.zip \
  && unzip /root/xray.zip -d /usr/bin/ \
  && chmod a+x /usr/bin/xray \
  && rm /root/xray.zip

COPY start.sh /opt/amnezia/start.sh
RUN chmod a+x /opt/amnezia/start.sh

ENV TZ=UTC

ENTRYPOINT ["dumb-init", "/opt/amnezia/start.sh"]
