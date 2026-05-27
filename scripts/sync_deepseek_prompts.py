#!/usr/bin/env bash
# DeepSeek answer-промпты (см. sync_provider_answer_prompts.py anthropic_claude для Claude).
exec docker compose -f docker-compose.prod.yml exec -T backend python scripts/sync_deepseek_prompts.py "$@"
