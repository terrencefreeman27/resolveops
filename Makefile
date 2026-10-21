.PHONY: up down reset seed test test-web logs ps
up:        ## build and start the stack (seeds automatically on first start)
	docker compose up -d --build
down:      ## stop the stack (keeps data)
	docker compose down
reset:     ## wipe the database volume and start fresh
	docker compose down -v && docker compose up -d --build
seed:      ## (re)seed Northstar Analytics — wipes and reloads workspace data
	docker compose exec api python -m app.seed --reset
test:      ## backend tests inside the api container against real Postgres
	docker compose exec api pytest -q
test-web:  ## frontend typecheck + production build
	cd frontend && npm ci && npm run typecheck && npm run build
logs:
	docker compose logs -f --tail=100
ps:
	docker compose ps
