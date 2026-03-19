.PHONY: help up down restart logs worker-logs beat-logs build rebuild shell migrate createsuperuser test scout report ps clean

help:
	@echo ""
	@echo "Bounty Hunter Agent — Docker Compose commands"
	@echo ""
	@echo "  make up              Start all services in background"
	@echo "  make down            Stop all services"
	@echo "  make restart         Restart all services"
	@echo "  make logs            Follow all service logs"
	@echo "  make worker-logs     Follow Celery worker logs"
	@echo "  make beat-logs       Follow Celery beat logs"
	@echo "  make build           Build Docker images"
	@echo "  make rebuild         Rebuild images without cache"
	@echo "  make ps              Show running containers"
	@echo "  make shell           Open Django shell"
	@echo "  make migrate         Run database migrations"
	@echo "  make createsuperuser Create Django admin user"
	@echo "  make test            Run test suite"
	@echo "  make scout           Run bounty scout scan"
	@echo "  make report          Print earnings report"
	@echo "  make clean           Remove containers and volumes"
	@echo ""

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

worker-logs:
	docker compose logs -f worker

beat-logs:
	docker compose logs -f beat

build:
	docker compose build

rebuild:
	docker compose build --no-cache

ps:
	docker compose ps

shell:
	docker compose exec web python manage.py shell

migrate:
	docker compose exec web python manage.py migrate

createsuperuser:
	docker compose exec web python manage.py createsuperuser

test:
	docker compose exec web pytest --tb=short -v

scout:
	docker compose exec web python manage.py scout_scan

report:
	docker compose exec web python manage.py bounty_report

clean:
	docker compose down -v --remove-orphans
