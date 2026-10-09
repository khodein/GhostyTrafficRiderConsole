# The base image ships Telegram's mtproto-proxy build with FakeTLS (--domain)
# support; we only add our own entrypoint.
FROM amneziavpn/mtproxy:latest
LABEL maintainer="ghosty-traffic-rider-console"

RUN mkdir -p /opt/mtproxy /data
COPY start.sh /opt/mtproxy/start.sh
RUN chmod a+x /opt/mtproxy/start.sh

VOLUME /data
ENTRYPOINT ["/bin/sh", "/opt/mtproxy/start.sh"]
