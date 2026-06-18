#!/bin/bash
# RTS CPI — Let's Encrypt auto-renewal (webroot via running nginx, then reload)
set -e
docker run --rm \
  -v /opt/cpi/nginx/letsencrypt:/etc/letsencrypt \
  -v /opt/cpi/nginx/acme:/var/www/certbot \
  certbot/certbot renew --webroot -w /var/www/certbot --quiet
docker exec cpi-nginx-1 nginx -s reload
