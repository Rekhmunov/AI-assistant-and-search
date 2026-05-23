.PHONY: help configure pack up down logs ps backup update check install-docker

COMPOSE_PROD = docker compose -f docker-compose.prod.yml

help:
	@echo "AI Search — hosting commands"
	@echo "  make configure   — .env + nginx from hosting.config"
	@echo "  make pack        — tar.gz for SFTP upload"
	@echo "  make up          — build and start production stack"
	@echo "  make down        — stop stack"
	@echo "  make logs        — follow backend logs"
	@echo "  make ps          — container status"
	@echo "  make backup      — PostgreSQL dump"
	@echo "  make update      — pull + rebuild + restart"
	@echo "  make check       — verify DNS, .env, health"
	@echo "  make install-docker — Docker on Ubuntu (sudo)"

configure:
	bash scripts/configure-hosting.sh

pack:
	bash scripts/pack-for-hosting.sh

up:
	$(COMPOSE_PROD) up -d --build

down:
	$(COMPOSE_PROD) down

logs:
	$(COMPOSE_PROD) logs -f backend

ps:
	$(COMPOSE_PROD) ps

backup:
	bash scripts/backup-db.sh

update:
	bash scripts/update.sh

check:
	bash scripts/check-hosting.sh

install-docker:
	sudo bash scripts/install-docker.sh
