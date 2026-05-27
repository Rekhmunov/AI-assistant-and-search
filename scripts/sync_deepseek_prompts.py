#!/usr/bin/env bash
# Обёртка: скрипт живёт в backend/scripts (попадает в Docker-образ).
exec docker compose -f docker-compose.prod.yml exec -T backend python scripts/sync_deepseek_prompts.py "$@"
