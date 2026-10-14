export PYTHONPATH := src

.PHONY: install pipeline dashboard test lint docker

install:    ## install dependencies
	pip install -r requirements-dev.txt
pipeline:   ## clean data, backtest valuation, build market & yield analytics -> outputs/report.md
	python -m dubaiprop.pipeline
dashboard:  ## http://localhost:8501
	streamlit run dashboard.py
test:
	pytest -q
lint:
	ruff check .
docker:
	docker build -t dubai-property-analytics . && docker run -p 8501:8501 dubai-property-analytics
