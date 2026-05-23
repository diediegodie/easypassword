.PHONY: test test-unit test-integration test-all

test-unit:
	RUN_INTEGRATION=0 pytest tests/unit/ -v

test-integration:
	cd ../infra/docker && docker-compose up -d
	sleep 3
	cd ../backend && RUN_INTEGRATION=1 pytest tests/integration/ -v
	cd ../infra/docker && docker-compose down

test-all: test-unit test-integration

test: test-unit
