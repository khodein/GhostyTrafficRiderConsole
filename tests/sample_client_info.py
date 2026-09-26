"""Sample client-info.json payloads for each built-in provider, reused
across tests instead of retyping them. IPs are from the 203.0.113.0/24
TEST-NET-3 block (RFC 5737) - reserved for documentation/examples, never a
real host - use that range for any new sample data too."""

SHADOWSOCKS_XRAY_INFO = {
    "provider": "shadowsocks-xray",
    "ip": "203.0.113.7",
    "domain": "203.0.113.7.sslip.io",
    "port": 23456,
    "password": "sample-password-1",
    "method": "chacha20-ietf-poly1305",
    "cert_expiry": "Jan  1 00:00:00 2027 GMT",
}

XRAY_REALITY_INFO = {
    "provider": "xray-reality",
    "ip": "203.0.113.7",
    "port": 443,
    "uuid": "11111111-2222-3333-4444-555555555555",
    "public_key": "AbCdEf1234567890abcdef1234567890abcdef1234567890a",
    "short_id": "0123456789abcdef",
    "site_name": "www.microsoft.com",
    "flow": "xtls-rprx-vision",
    "fingerprint": "chrome",
}
