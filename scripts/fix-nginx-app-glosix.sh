#!/usr/bin/env bash
# Replace app.glosix.ru nginx vhost with Docker reverse proxy (ISPmanager).
set -euo pipefail

CONF="/etc/nginx/vhosts/www-root/app.glosix.ru.conf"
BACKUP="${CONF}.bak.$(date +%s)"

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

PROXY_PORT="${PROXY_PORT:-18080}"

cp "$CONF" "$BACKUP"
echo "Backup: $BACKUP"
echo "SSL: $CRTACA"

cat > "$CONF" << NGINX
server {
        server_name app.glosix.ru www.app.glosix.ru;
        charset off;
        disable_symlinks if_not_owner from=\$root_path;
        include /etc/nginx/vhosts-includes/*.conf;
        include /etc/nginx/vhosts-resources/app.glosix.ru/*.conf;
        access_log /var/www/httpd-logs/app.glosix.ru.access.log;
        error_log /var/www/httpd-logs/app.glosix.ru.error.log notice;
        return 301 https://\$host\$request_uri;
        listen 192.168.0.175:80;
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
        disable_symlinks if_not_owner from=\$root_path;
        include /etc/nginx/vhosts-includes/*.conf;
        include /etc/nginx/vhosts-resources/app.glosix.ru/*.conf;
        access_log /var/www/httpd-logs/app.glosix.ru.access.log;
        error_log /var/www/httpd-logs/app.glosix.ru.error.log notice;
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
        }
        listen 192.168.0.175:443 ssl;
}
NGINX

nginx -t
systemctl reload nginx
echo "Done. Test: curl -s https://app.glosix.ru/ | head -5"
