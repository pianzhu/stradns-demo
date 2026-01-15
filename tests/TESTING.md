# Test Commands

Unit tests:
- PYTHONPATH=src python -m unittest discover -s tests/unit -v
- PYTHONPATH=src python -m unittest discover -s tests/unit -p "test_models.py" -v

Integration tests (DashScope):
- RUN_DASHSCOPE_IT=1 DASHSCOPE_API_KEY=... PYTHONPATH=src python -m unittest discover -s tests/integration -v
- RUN_DASHSCOPE_IT=1 DASHSCOPE_API_KEY=... PYTHONPATH=src python -m unittest tests.integration.test_dashscope_integration -v

All tests:
- PYTHONPATH=src python -m unittest discover -s tests -v
