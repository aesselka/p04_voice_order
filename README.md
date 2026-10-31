# Voice Cart NLU (ru + kk)

Речь → STT → текст → **Command** (add / remove / modify / cancel / confirm) → Cart State Machine.
NLU не меняет корзину и не считает цены; он отдаёт только структурированное намерение.

## Запуск (Windows, PowerShell)

### Что нужно
- Python 3.10+ (проверено на 3.14), `python --version`.
- Ключ ElevenLabs — для голоса (см. шаг 2). Без ключа работает только текстовый ввод.
- Браузер с микрофоном (Chrome/Edge/Firefox).

### 1. Окружение
Скачайте проект (`git clone <url>` или ZIP) и выполняйте все команды из его корня
(папка, где лежит `requirements.txt`).

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1                # если запрещено: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
    pip install -r requirements.txt
    python -m pytest -q                         # текстовые диалоги, без голоса и без LLM — должно быть «passed»

macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`, остальное так же.

### 2. Ключи — файл `.env` в корне проекта
**Где взять ключ ElevenLabs:**
1. Зарегистрируйтесь на https://elevenlabs.io (есть бесплатный тариф с лимитом минут).
2. Откройте https://elevenlabs.io/app/settings/api-keys → **Create API Key**.
3. Если включаете ограничения ключа — оставьте доступ **Speech to Text**, иначе будет ошибка 401/403.
4. Скопируйте ключ (вида `sk_...`) — он показывается один раз.

**Куда положить:** скопируйте шаблон и впишите ключ:

    Copy-Item .env.example .env                 # macOS/Linux: cp .env.example .env
    notepad .env

    ELEVENLABS_API_KEY=sk_...                   # обязательно для голоса (ElevenLabs Scribe)
    # ANTHROPIC_API_KEY=sk-ant-...              # опционально: LLM-fallback (pip install anthropic)
    # MENU_PATH=C:\path\to\menu.json            # опционально: своё меню, формат = voice_cart_nlu/data/menu.json

`api.py` и CLI сами читают `.env` при старте (python-dotenv), `export`/`$env:` не нужны.
`.env` в `.gitignore` — не коммитьте его. После изменения `.env` перезапустите uvicorn
(`--reload` следит за кодом, а не за `.env`).

Альтернатива (нужен Node.js): `npx -y @elevenlabs/cli@latest onboard init` — создаст `.env` с ключом сам.

Без ключа ElevenLabs сервер стартует, но работают только текстовые эндпоинты.
Без ElevenLabs вообще — используйте локальный Whisper (см. «Выбор STT» ниже).

### 3. Сервер

    uvicorn voice_cart_nlu.api:app --reload

- UI (голосовой заказ): http://127.0.0.1:8000/
- Swagger, можно пробовать запросы: http://127.0.0.1:8000/docs
- Остановить: `Ctrl+C`. Порт занят → `--port 8001`.

### Выбор STT: ElevenLabs или Whisper
По умолчанию — **ElevenLabs** (`scribe_v2`), без fallback. Whisper включается переменными
(в `.env` или в той же сессии PowerShell до запуска uvicorn):

| Режим | Что сделать |
|---|---|
| ElevenLabs (по умолчанию) | `ELEVENLABS_API_KEY` в `.env` |
| Только Whisper, локально | `pip install faster-whisper`, `STT_PROVIDER=whisper` (модель `large-v3`, первый запуск скачает её) |
| ElevenLabs, при ошибке → Whisper | `pip install faster-whisper`, `WHISPER_FALLBACK=1` (модель `small`) |

Прочее: `WHISPER_MODEL` — размер модели Whisper, `ELEVENLABS_STT_MODEL` — модель Scribe,
`LLM_MODEL` — модель для LLM-fallback.

### Проверка без UI (из файлов)

    python -m voice_cart_nlu.stt audio\kart.mp3 --lang ru        # только транскрипция
    python -m voice_cart_nlu.cart audio\kart.mp3 audio\remove.mp3 # речь -> корзина, файлы по порядку разговора

### Если не работает
| Симптом | Причина / решение |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, затем снова активировать |
| `uvicorn` / `No module named ...` | не активирован `.venv` или не выполнен `pip install -r requirements.txt` |
| `503 STT is not configured` | нет `ELEVENLABS_API_KEY` в `.env` (или не перезапущен сервер) |
| `502 STT failed: ... 401` | неверный ключ или у ключа нет доступа Speech to Text |
| `502 STT failed: ... 429` / quota | исчерпан лимит тарифа ElevenLabs |
| Браузер не даёт микрофон | открывайте `http://127.0.0.1:8000/` (не файл `index.html`) и разрешите микрофон в адресной строке |
| Кириллица «кракозябрами» в PowerShell | только отображение в Windows PowerShell 5.1; ответ сервера корректный |

## API
    POST   /nlu/text              {"text": "Колу сделай большой", "cart": {"lines": [...]}}
    POST   /nlu/voice             multipart: audio=<file>, lang=ru|kk (необязательно), cart=<json>

    POST   /cart/{session}/voice  multipart: audio=<file>, lang=ru|kk  -> {transcript, actions, notes, question, cart}
    POST   /cart/{session}/text   {"text": "два комбо с колой"}         -> то же без STT
    GET    /cart/{session}        DELETE /cart/{session}

Пример из PowerShell:

    Invoke-RestMethod -Method Post http://127.0.0.1:8000/cart/demo/text `
      -ContentType "application/json; charset=utf-8" `
      -Body ([Text.Encoding]::UTF8.GetBytes('{"text": "два комбо с колой"}'))

## Голосовой заказ (речь -> корзина)

Поток: речь -> `stt.py` -> `rules.py`/`llm_parser.py` (Command) -> `actions.py` (Action JSON) -> `cart.py` -> UI.
- `actions.py` — действия: `add_item, remove_item, change_quantity, change_size, add_modifier, remove_modifier,
  set_combo_choice, clear_cart, confirm`. «Замени колу на спрайт» = `remove_item` + `add_item(replaces=true)`.
- `cart.py` — проверяет каждое действие по `menu.json` (блюдо, размер, разрешённые добавки, варианты комбо),
  отклоняет неверное (`notes`) и задаёт ОДИН уточняющий вопрос (`question`). Цены — только здесь,
  целыми тиынами (`*_cents`, 1/100 ₸) из меню; LLM цен не видит.
- Комбо: `choices` в `menu.json` (напиток, гарнир, размер). Пока не выбрано всё — строка `pending`,
  не входит в итог и блокирует `confirm`. Ответ «колу» на вопрос о напитке заполняет комбо, а не
  добавляет колу. Варианты никогда не подставляются по умолчанию.
- Цены в `data/menu.json` — заглушки (см. `_note`).

## Как работает
1. `stt.py` — ElevenLabs Scribe (основной), faster-whisper (fallback), `FallbackSTT`. Язык из переключателя UI
   передаётся в STT; названия меню — подсказка для Whisper (`initial_prompt`).
2. `rules.py` — детерминированный парсер (ru/kk/смешанный). Быстрый путь, ~1 мс.
3. `llm_parser.py` — только если rules не уверены (`confidence < 0.75` или `unknown`): JSON → Pydantic, 1 retry.
4. `validate.py` — id блюд и модификаторов проверяются по меню, выдуманные отбрасываются.

## Контракт (`schemas.py`)
- `add`    → `items[]` (menu_item_id | candidates, quantity, size, modifiers)
- `remove` → `target` (ordinal / menu_item_id / is_last), `quantity`
- `modify` → `target` + `changes` (size, quantity, modifiers add/remove, replace_with)
- `cancel` = весь заказ, `confirm`, `unknown`
- `issues`: `ambiguous_item:*`, `unknown_item:*`, `no_target`, `unrecognized:*` → State Machine решает, что уточнить.
- Составные фразы («убери колу и добавь воду») → несколько Command по порядку.

## Что остаётся за State Machine
Наличие, допустимые размеры/модификаторы, цены, уточнение параметров комбо, «неявный» target
(пустой `LineRef` = последняя тронутая строка), разрешение `ordinal` + `menu_item_id`.

## Дальше
- Заменить `data/menu.json` на 20–30 позиций im.kz (aliases ru/kk + падежные формы).
- Прогнать 30 размеченных диалогов: добавить в `tests/test_rules.py::CASES`, считать accuracy по intent/target/changes.
- Записать реальные аудио (ru/kk) и сравнить WER ElevenLabs vs Whisper именно на названиях меню.
