# Smallworld development stack
# Usage:
#   make up       — start all services (API, MCP, Web) in background
#   make down     — stop all services
#   make status   — show which services are running
#   make logs     — tail all log files
#   make restart  — down + up

LOGDIR := $(CURDIR)/.logs
API_LOG := $(LOGDIR)/api.log
MCP_LOG := $(LOGDIR)/mcp.log
WEB_LOG := $(LOGDIR)/web.log
TOOL_LOG := $(LOGDIR)/tool-calls.ndjson
API_PID := $(LOGDIR)/api.pid
MCP_PID := $(LOGDIR)/mcp.pid
WEB_PID := $(LOGDIR)/web.pid

.PHONY: up down status logs restart up-api up-mcp up-web down-api down-mcp down-web help

up: | $(LOGDIR)
	@$(MAKE) --no-print-directory up-api up-mcp up-web
	@echo ""
	@$(MAKE) --no-print-directory status

$(LOGDIR):
	@mkdir -p $(LOGDIR)

up-api:
	@if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then \
		echo "API already running (pid $$(cat $(API_PID)))"; \
	else \
		echo "Starting API on :8080..."; \
		cd apps/api && nohup uv run uvicorn smallworld_api.main:app --reload --host 0.0.0.0 --port 8080 \
			> $(API_LOG) 2>&1 & echo $$! > $(API_PID); \
		sleep 1; \
		echo "API started (pid $$(cat $(API_PID)))"; \
	fi

up-mcp:
	@if [ -f $(MCP_PID) ] && kill -0 $$(cat $(MCP_PID)) 2>/dev/null; then \
		echo "MCP already running (pid $$(cat $(MCP_PID)))"; \
	else \
		echo "Starting MCP on :8001..."; \
		cd apps/api && nohup uv run python -m smallworld_api.mcp.cli --transport http \
			> $(MCP_LOG) 2>&1 & echo $$! > $(MCP_PID); \
		sleep 1; \
		echo "MCP started (pid $$(cat $(MCP_PID)))"; \
	fi

up-web:
	@if [ -f $(WEB_PID) ] && kill -0 $$(cat $(WEB_PID)) 2>/dev/null; then \
		echo "Web already running (pid $$(cat $(WEB_PID)))"; \
	else \
		echo "Starting Web on :3000..."; \
		nohup pnpm dev:web > $(WEB_LOG) 2>&1 & echo $$! > $(WEB_PID); \
		sleep 2; \
		echo "Web started (pid $$(cat $(WEB_PID)))"; \
	fi

down: down-web down-mcp down-api
	@echo "All services stopped"

down-api:
	@if [ -f $(API_PID) ]; then \
		PID=$$(cat $(API_PID)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "Stopping API (pid $$PID)..."; \
			kill $$PID 2>/dev/null; \
			sleep 1; \
			kill -0 $$PID 2>/dev/null && kill -9 $$PID 2>/dev/null; \
		fi; \
		rm -f $(API_PID); \
	fi
	@# Also kill any orphaned uvicorn on :8080
	@lsof -ti :8080 2>/dev/null | xargs kill 2>/dev/null || true

down-mcp:
	@if [ -f $(MCP_PID) ]; then \
		PID=$$(cat $(MCP_PID)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "Stopping MCP (pid $$PID)..."; \
			kill $$PID 2>/dev/null; \
			sleep 1; \
			kill -0 $$PID 2>/dev/null && kill -9 $$PID 2>/dev/null; \
		fi; \
		rm -f $(MCP_PID); \
	fi
	@lsof -ti :8001 2>/dev/null | xargs kill 2>/dev/null || true

down-web:
	@if [ -f $(WEB_PID) ]; then \
		PID=$$(cat $(WEB_PID)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "Stopping Web (pid $$PID)..."; \
			kill $$PID 2>/dev/null; \
			sleep 1; \
			kill -0 $$PID 2>/dev/null && kill -9 $$PID 2>/dev/null; \
		fi; \
		rm -f $(WEB_PID); \
	fi
	@lsof -ti :3000 2>/dev/null | xargs kill 2>/dev/null || true

status:
	@echo "=== Smallworld Stack ==="
	@printf "  API  (:8080)  "; \
	if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then \
		echo "UP  (pid $$(cat $(API_PID)))"; \
	elif lsof -ti :8080 >/dev/null 2>&1; then \
		echo "UP  (port in use, no pidfile)"; \
	else \
		echo "DOWN"; \
	fi
	@printf "  MCP  (:8001)  "; \
	if [ -f $(MCP_PID) ] && kill -0 $$(cat $(MCP_PID)) 2>/dev/null; then \
		echo "UP  (pid $$(cat $(MCP_PID)))"; \
	elif lsof -ti :8001 >/dev/null 2>&1; then \
		echo "UP  (port in use, no pidfile)"; \
	else \
		echo "DOWN"; \
	fi
	@printf "  Web  (:3000)  "; \
	if [ -f $(WEB_PID) ] && kill -0 $$(cat $(WEB_PID)) 2>/dev/null; then \
		echo "UP  (pid $$(cat $(WEB_PID)))"; \
	elif lsof -ti :3000 >/dev/null 2>&1; then \
		echo "UP  (port in use, no pidfile)"; \
	else \
		echo "DOWN"; \
	fi

logs:
	@tail -f $(API_LOG) $(MCP_LOG) $(WEB_LOG) $(TOOL_LOG) 2>/dev/null || echo "No log files found. Run 'make up' first."

restart: down up

help:
	@echo "Smallworld development stack"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "  up          Start all services (API, MCP, Web) in background"
	@echo "  down        Stop all services"
	@echo "  restart     Stop and restart all services"
	@echo "  status      Show which services are running"
	@echo "  logs        Tail all log files"
	@echo ""
	@echo "  up-api      Start API only (:8080)"
	@echo "  up-mcp      Start MCP only (:8001)"
	@echo "  up-web      Start Web only (:3000)"
	@echo "  down-api    Stop API"
	@echo "  down-mcp    Stop MCP"
	@echo "  down-web    Stop Web"
	@echo ""
	@echo "  help        Show this help"
