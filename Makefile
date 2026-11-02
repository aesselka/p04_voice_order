PY ?= .venv/bin/python

.PHONY: setup test cov lint eval eval-llm massive record tts voice-eval check

setup:            ## окружение + dev-зависимости
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements-dev.txt

test:             ## все тесты (без сети и ключей)
	$(PY) -m pytest

cov:              ## тесты + покрытие
	$(PY) -m pytest --cov --cov-report=term-missing

lint:
	$(PY) -m ruff check voice_cart_nlu tests evals voice_eval

eval:             ## эталонные диалоги -> evals/reports/rules.md
	$(PY) -m evals.run --gate

eval-llm:         ## то же с LLM-fallback (нужен ANTHROPIC_API_KEY)
	$(PY) -m evals.run --llm

massive:          ## фразы Amazon MASSIVE -> evals/reports/massive.md
	$(PY) -m evals.massive

record:           ## студия записи голоса -> http://127.0.0.1:8765
	$(PY) -m voice_eval.recorder

tts:              ## синтетические ru-записи голосом Milena (macOS)
	$(PY) -m voice_eval.tts

voice-eval:       ## make voice-eval SPEAKER=nurasyl PROVIDER=elevenlabs
	$(PY) -m voice_eval.stt_eval --speaker $(SPEAKER) --provider $(or $(PROVIDER),elevenlabs)

check: lint cov eval massive   ## всё, что гоняет CI
