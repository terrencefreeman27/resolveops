.PHONY: up down reset seed test test-web e2e eval eval-live logs ps
up:        ## build and start the stack (seeds automatically on first start)
	docker compose up -d --build
down:      ## stop the stack (keeps data)
	docker compose down
reset:     ## wipe the database volume and start fresh
	docker compose down -v && docker compose up -d --build
seed:      ## (re)seed both demo workspaces (Northstar, Lumen); reviewer-created workspaces untouched
	docker compose exec api python -m app.seed --reset
test:      ## backend tests inside the api container against real Postgres
	docker compose exec api pytest -q
test-web:  ## frontend typecheck + production build
	cd frontend && npm ci && npm run typecheck && npm run build
e2e:       ## browser checks against the running stack (needs a Playwright Chromium; see README)
	cd frontend && npm run e2e
eval:      ## AI task eval (demo, simulated), live eval status (records "not run" without a key), backend checks
	docker compose exec -e EVAL_GIT_COMMIT=$$(git rev-parse --short HEAD) api python -m eval.run_ai_eval --mode demo
	docker compose exec -e EVAL_GIT_COMMIT=$$(git rev-parse --short HEAD) api python -m eval.run_ai_eval --mode live
	docker compose exec -e EVAL_GIT_COMMIT=$$(git rev-parse --short HEAD) api python -m eval.run_backend_eval
eval-live: ## live AI eval + prompt-only baseline (needs ANTHROPIC_API_KEY in .env; spends tokens)
	docker compose exec -e EVAL_GIT_COMMIT=$$(git rev-parse --short HEAD) api python -m eval.run_ai_eval --mode live
logs:
	docker compose logs -f --tail=100
ps:
	docker compose ps
