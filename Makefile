.PHONY: test cov

test:
	pytest

cov:
	pytest --cov=jiuwenswarm --cov-report=term-missing --cov-report=html --cov-report=xml
