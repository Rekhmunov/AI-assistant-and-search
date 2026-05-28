#!/usr/bin/env bash
# Replace api.glosix.ru nginx vhost with Docker reverse proxy (ISPmanager).
set -euo pipefail

CONF="/etc/nginx/vhosts/www-root/api.glosix.ru.conf"
BACKUP="${CONF}.bak.$(date +%s)"

if [ ! -f "$CONF" ]; then
  echo "Not found: $CONF"
  exit 1
fi

PROXY_PORT="${PROXY_PORT:-18080}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LISTEN_IP="$("$ROOT/scripts/nginx-listen-ip.sh")"

cp "$CONF" "$BACKUP"
echo "Backup: $BACKUP"
echo "listen IP: $LISTEN_IP (proxy -> 127.0.0.1:${PROXY_PORT})"

cat > "$CONF" << NGINX
server {
        server_name api.glosix.ru www.api.glosix.ru;
        charset off;
        disable_symlinks if_not_owner from=\$root_path;
        include /etc/nginx/vhosts-includes/*.conf;
        include /etc/nginx/vhosts-resources/api.glosix.ru/*.conf;
        access_log /var/www/httpd-logs/api.glosix.ru.access.log;
        error_log /var/www/httpd-logs/api.glosix.ru.error.log notice;
        return 301 https://\$host\$request_uri;
        listen ${LISTEN_IP}:80;
}
server {
        server_name api.glosix.ru www.api.glosix.ru;
        ssl_certificate "/var/www/httpd-cert/www-root/api.glosix.ru_le2.crtca";
        ssl_certificate_key "/var/www/httpd-cert/www-root/api.glosix.ru_le2.key";
        ssl_ciphers EECDH:+AES256:-3DES:RSA+AES:!NULL:!RC4;
        ssl_prefer_server_ciphers on;
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2 TLSv1.3;
        ssl_dhparam /etc/ssl/certs/dhparam4096.pem;
        charset off;
        disable_symlinks if_not_owner from=\$root_path;
        include /etc/nginx/vhosts-includes/*.conf;
        include /etc/nginx/vhosts-resources/api.glosix.ru/*.conf;
        access_log /var/www/httpd-logs/api.glosix.ru.access.log;
        error_log /var/www/httpd-logs/api.glosix.ru.error.log notice;
        gzip on;
        gzip_comp_level 5;
        gzip_disable "msie6";
        gzip_types text/plain text/css application/json application/x-javascript text/xml application/xml application/xml+rss text/javascript application/javascript image/svg+xml;
        location / {
                proxy_pass http://127.0.0.1:${PROXY_PORT};
                proxy_http_version 1.1;
                proxy_set_header Host \$host;
                proxy_set_header X-Real-IP \$remote_addr;
                proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto \$scheme;
                proxy_buffering off;
                proxy_read_timeout 300s;
        }
        listen ${LISTEN_IP}:443 ssl;
}
NGINX

nginx -t
systemctl reload nginx
echo "Done. Test: curl -s https://api.glosix.ru/health"
