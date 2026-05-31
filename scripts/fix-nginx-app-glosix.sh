#!/usr/bin/env bash
# Redirect app.glosix.ru -> glosix.ru (ISPmanager). Старые ссылки MAX и закладки.
set -euo pipefail

CONF="/etc/nginx/vhosts/www-root/app.glosix.ru.conf"
BACKUP="${CONF}.bak.$(date +%s)"
TARGET="${REDIRECT_TO:-https://glosix.ru}"

if [ ! -f "$CONF" ]; then
  echo "Not found: $CONF"
  exit 1
fi

CRTACA=$(ls -1 /var/www/httpd-cert/www-root/app.glosix.ru_le*.crtca 2>/dev/null | head -1 || true)
KEY=$(ls -1 /var/www/httpd-cert/www-root/app.glosix.ru_le*.key 2>/dev/null | head -1 || true)
if [ -z "$CRTACA" ] || [ -z "$KEY" ]; then
  echo "SSL cert not found for app.glosix.ru (expected le*.crtca and le*.key)"
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LISTEN_IP="$("$ROOT/scripts/nginx-listen-ip.sh")"

cp "$CONF" "$BACKUP"
echo "listen IP: $LISTEN_IP"
echo "Backup: $BACKUP"
echo "Redirect: app.glosix.ru -> ${TARGET}"
echo "SSL: $CRTACA"

cat > "$CONF" << NGINX
server {
        server_name app.glosix.ru www.app.glosix.ru;
        charset off;
        include /etc/nginx/vhosts-includes/*.conf;
        include /etc/nginx/vhosts-resources/app.glosix.ru/*.conf;
        access_log /var/www/httpd-logs/app.glosix.ru.access.log;
        error_log /var/www/httpd-logs/app.glosix.ru.error.log notice;
        return 301 https://\$host\$request_uri;
        listen ${LISTEN_IP}:80;
}
server {
        server_name app.glosix.ru www.app.glosix.ru;
        ssl_certificate "${CRTACA}";
        ssl_certificate_key "${KEY}";
        ssl_ciphers EECDH:+AES256:-3DES:RSA+AES:!NULL:!RC4;
        ssl_prefer_server_ciphers on;
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3;
        ssl_dhparam /etc/ssl/certs/dhparam4096.pem;
        charset off;
        include /etc/nginx/vhosts-includes/*.conf;
        include /etc/nginx/vhosts-resources/app.glosix.ru/*.conf;
        access_log /var/www/httpd-logs/app.glosix.ru.access.log;
        error_log /var/www/httpd-logs/app.glosix.ru.error.log notice;
        return 301 ${TARGET}\$request_uri;
        listen ${LISTEN_IP}:443 ssl;
}
NGINX

nginx -t
systemctl reload nginx
echo "Done. Test: curl -sI https://app.glosix.ru/ | grep -i location"
