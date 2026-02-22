.PHONY: proto test lint typecheck fmt clean build

proto:
	python -m grpc_tools.protoc \
		-I proto \
		--python_out=vani/generated \
		--grpc_python_out=vani/generated \
		--pyi_out=vani/generated \
		proto/vani/v1/*.proto

test:
	pytest tests/ -q

lint:
	ruff check vani/ tests/

typecheck:
	mypy vani/

fmt:
	ruff format vani/ tests/

build:
	rm -rf dist/
	python -m build

clean:
	rm -rf dist/ build/ *.egg-info vani/generated/*.py
