---
name: coding-rules
description: Universal Python coding hygiene rules. Apply always, regardless of framework. Covers identifiers (UUID PK), time (timezone-aware UTC), money (Decimal), paths (pathlib), error handling, logging, secrets, typing, imports, string formatting, constants, docstrings, TODO discipline. Works alongside testing-rules (testing side) and framework-specific coding-<stack> skills (coding-django, coding-fastapi, coding-postgis).
type: skill
---

# Coding rules — правила гигиены Python-кода

Применяются всегда — при написании нового кода, правке существующего и при ревью.
Стек-агностичны: Django, FastAPI, чистый Python. Покрывают production-код,
не тесты (тесты — `testing-rules`).

## Принципы

1. **Fail-fast в prod.** Обязательные env-переменные читаются БЕЗ default — ошибка при старте сервиса лучше, чем молчаливая неправильная конфигурация в рантайме.
2. **Явное > неявное.** Type hints, именованные константы, explicit returns — код читается без знания контекста.
3. **UUID как PK для публично адресуемых сущностей.** Sequential int раскрывает бизнес-метрики и открывает IDOR-угадывание.
4. **Время — всегда UTC timezone-aware.** `datetime.now(UTC)`, не `utcnow()`, не naive. Граница принимает только aware datetime.
5. **Деньги — `Decimal`, не `float`.** Никогда. Потеря центов незаметна в тестах, видна в балансах.
6. **Пути — `pathlib.Path`, не string concat.** Читаемость, кроссплатформенность, встроенная обработка частей пути.
7. **Логи структурированные.** Без `print()` в продакшн-коде. Секреты никогда в лог.
8. **Никаких TODO без ссылки на BACKLOG-NNN.** Голый `# TODO` — технический долг без адреса. Исчезает из внимания через неделю.

---

## Правила по категориям

### 1. Идентификаторы

#### UUID как PK для публично адресуемых сущностей

Sequential int в URL раскрывает бизнес-метрики (`/orders/42` — у вас 42 заказа)
и открывает IDOR-угадывание. UUID устраняет обе проблемы.

ПЛОХО:
```python
import random

order_id = random.randint(1, 1000)          # угадываемый
user_url = f"/users/{user.id}"              # последовательный int
```

ХОРОШО:
```python
import uuid

order_id = uuid.uuid4()                     # /orders/a1b2-c3d4-...
user_url = f"/users/{user.uuid}"
```

Исключение: внутренние справочники без публичного URL (типы почв, роли, статусы)
можно оставлять с sequential int — они не адресуемы снаружи.

#### Никогда не раскрывай sequential ID в публичных ответах API

Даже если PK внутри `int` — API должен отдавать UUID или slug.

ПЛОХО:
```python
def to_dict(self):
    return {"id": self.pk, "name": self.name}   # pk=42 утекает наружу
```

ХОРОШО:
```python
def to_dict(self):
    return {"id": str(self.uuid), "name": self.name}
```

---

### 2. Время

#### `datetime.now(UTC)` — всегда timezone-aware

`datetime.utcnow()` возвращает naive datetime без tzinfo, выглядит как UTC
но не помечен — сравнение с aware-объектами упадёт в рантайме.
`datetime.now()` без аргументов — локальное время машины, ещё хуже.

ПЛОХО:
```python
from datetime import datetime

created_at = datetime.utcnow()      # naive — потеряет при сравнении с aware
updated_at = datetime.now()         # локальное время, не UTC
```

ХОРОШО:
```python
from datetime import datetime, UTC

created_at = datetime.now(UTC)      # Python 3.11+ — явный UTC, aware
```

Для Python < 3.11:
```python
from datetime import datetime, timezone

created_at = datetime.now(timezone.utc)
```

#### Граница принимает только aware datetime

На любой внешней границе (API endpoint, форма, Celery task) — валидировать
что входящий datetime является aware. Naive datetime внутри сервиса — ошибка.

ПЛОХО:
```python
def schedule_task(run_at: datetime):
    # run_at может быть naive — сравнение взорвётся позже
    if run_at > datetime.now():
        ...
```

ХОРОШО:
```python
from datetime import datetime, UTC

def schedule_task(run_at: datetime):
    if run_at.tzinfo is None:
        raise ValueError(f"run_at must be timezone-aware, got naive: {run_at}")
    if run_at > datetime.now(UTC):
        ...
```

#### ISO-8601 для сериализации datetime

При передаче datetime через API или сохранении в текстовом виде — всегда ISO-8601.
Никаких кастомных форматов.

ПЛОХО:
```python
payload = {"timestamp": dt.strftime("%d.%m.%Y %H:%M")}   # нечитаемо для API-клиентов
```

ХОРОШО:
```python
payload = {"timestamp": dt.isoformat()}    # "2026-04-24T10:30:00+00:00"
```

### 3. Деньги и числа с финансовым смыслом

#### `Decimal`, не `float` для денег

`float` имеет бинарное представление — `0.1 + 0.2 != 0.3`. Для сумм, курсов,
процентов это означает накапливающиеся ошибки округления, видимые в итогах.

ПЛОХО:
```python
price = 9.99
tax = 0.20
total = price * (1 + tax)      # 11.988000000000001 — не то
```

ХОРОШО:
```python
from decimal import Decimal

price = Decimal("9.99")
tax = Decimal("0.20")
total = price * (1 + tax)      # Decimal("11.988") — точно
```

#### `Decimal("0.1")`, не `Decimal(0.1)`

`Decimal(0.1)` создаёт Decimal из float — наследует ошибку бинарного представления.
`Decimal("0.1")` — из строки, точно.

ПЛОХО:
```python
Decimal(0.1)    # Decimal('0.1000000000000000055511151231257827021181583404541015625')
```

ХОРОШО:
```python
Decimal("0.1")  # Decimal('0.1')
```

#### Явный `quantize()` при округлении

Никаких `round()` для денег — `quantize()` с явным режимом округления.

ПЛОХО:
```python
result = round(total, 2)            # встроенный round — banker's rounding
```

ХОРОШО:
```python
from decimal import Decimal, ROUND_HALF_UP

result = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

---

### 4. Пути и файлы

#### `pathlib.Path` вместо `os.path` и строкового concat

`os.path.join(base, "subdir", "file.txt")` громоздко и платформо-зависимо
в крайних случаях. `pathlib` — читаемо, безопасно, поддерживает `/` оператор.

ПЛОХО:
```python
import os

config_path = os.path.join(os.path.dirname(__file__), "config", "settings.ini")
full_path = base_dir + "/" + "uploads" + "/" + filename   # хрупко
```

ХОРОШО:
```python
from pathlib import Path

config_path = Path(__file__).parent / "config" / "settings.ini"
full_path = base_dir / "uploads" / filename
```

#### Явный `encoding` при открытии файлов

Без явного `encoding` поведение зависит от локали ОС — тихо ломается на
серверах с нестандартной локалью или при переносе между платформами.

ПЛОХО:
```python
with open("report.txt", "w") as f:     # кодировка — что получится
    f.write(content)
```

ХОРОШО:
```python
from pathlib import Path

Path("report.txt").write_text(content, encoding="utf-8")

# или стандартный open с явным encoding:
with open("report.txt", "w", encoding="utf-8") as f:
    f.write(content)
```

#### Запрет hardcoded абсолютных путей в коде

Абсолютный путь в коде — это путь к машине разработчика, не к production.

ПЛОХО:
```python
DATA_DIR = "/Users/vladimir/projects/myapp/data"    # только на одной машине
LOG_FILE = "/var/log/myapp/app.log"                 # hardcoded prod-путь
```

ХОРОШО:
```python
import os
from pathlib import Path

DATA_DIR = Path(os.environ["DATA_DIR"])             # из env — fail-fast если нет
LOG_FILE = Path(__file__).parent.parent / "logs" / "app.log"  # относительный
```

### 5. Обработка ошибок

#### Запрет bare `except:` и `except Exception:` без re-raise

Bare `except` перехватывает `KeyboardInterrupt`, `SystemExit` и другие
системные исключения — программа не реагирует на Ctrl+C. `except Exception`
без re-raise прячет ошибки, превращая сбои в молчаливые отказы.

ПЛОХО:
```python
try:
    result = process(data)
except:                         # перехватывает всё, включая SystemExit
    pass                        # ошибка исчезла — никто не узнает

try:
    result = process(data)
except Exception:               # широкий catch без re-raise
    logger.error("failed")      # нет traceback, нет контекста
```

ХОРОШО:
```python
try:
    result = process(data)
except ValueError as exc:       # конкретное исключение
    logger.error("Invalid data: %s", exc)
    raise                       # re-raise — не проглатываем

try:
    result = process(data)
except Exception as exc:        # широкий catch допустим только если есть явный re-raise
    logger.exception("Unexpected error in process()")
    raise
```

#### `raise ... from err` для сохранения причины

При перехвате и перебрасывании исключения с другим типом — явно указывать
исходную причину через `from`. Без этого traceback теряет оригинальный контекст.

ПЛОХО:
```python
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    raise ValueError("Invalid payload")    # причина потеряна
```

ХОРОШО:
```python
try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    raise ValueError("Invalid payload") from exc    # traceback сохранён
```

#### Custom exceptions для доменных ошибок

Исключения с именами из домена задачи — говорят что пошло не так без чтения
traceback. Базовый класс модуля упрощает catch на верхнем уровне.

ПЛОХО:
```python
raise ValueError("order not found")     # generic, неотличимо от других ValueError
raise Exception("insufficient funds")  # слишком широко
```

ХОРОШО:
```python
class AppError(Exception):
    """Базовый класс для доменных ошибок приложения."""

class OrderNotFoundError(AppError):
    pass

class InsufficientFundsError(AppError):
    pass

raise OrderNotFoundError(f"Order {order_id} not found")
```

---

### 6. Логирование

#### Модульный logger, не корневой

`logging.getLogger(__name__)` даёт логгер с именем модуля — фильтрацию и
маршрутизацию можно настроить по иерархии модулей. Корневой logger или
именованный вручную — теряет контекст происхождения.

ПЛОХО:
```python
import logging

logging.info("Processing started")     # корневой logger — нет контекста модуля
logger = logging.getLogger("myapp")   # захардкоженное имя
```

ХОРОШО:
```python
import logging

logger = logging.getLogger(__name__)  # имя модуля автоматически

logger.info("Processing started")
```

#### Запрет `print()` в продакшн-коде

`print()` нельзя фильтровать, перенаправлять или структурировать. В prod
лог уходит в stdout/stderr мимо log-системы.

ПЛОХО:
```python
print(f"Processing order {order_id}")
print("ERROR: something went wrong")
```

ХОРОШО:
```python
logger.info("Processing order %s", order_id)
logger.error("Processing failed for order %s", order_id, exc_info=True)
```

#### Lazy formatting для логов

f-string вычисляется всегда, даже если уровень лога выключен. `%s`-форматирование
в `logger.info(...)` вычисляется только при реальной записи.

ПЛОХО:
```python
logger.debug(f"Full data: {expensive_repr(data)}")   # вычисляется всегда
```

ХОРОШО:
```python
logger.debug("Full data: %s", expensive_repr(data))   # вычисляется только при DEBUG
```

Исключение: если форматирование само по себе дешёво и f-string улучшает читаемость
— допустимо. Применяй lazy formatting там где аргумент дорогой.

#### Секреты никогда в логи

Токены, пароли, API-ключи, PII — не должны появляться в логах даже в DEBUG.

ПЛОХО:
```python
logger.info("Authenticating user %s with password %s", username, password)
logger.debug("API response: %s", response.json())  # response может содержать token
```

ХОРОШО:
```python
logger.info("Authenticating user %s", username)    # пароль не логируем
logger.debug("API response status: %s", response.status_code)  # только статус
```

### 7. Секреты и конфигурация

#### Никаких hardcoded secrets в коде

API ключи, пароли, токены, connection strings — не должны появляться в коде,
даже в тестах. Попадание в git-историю необратимо (rewrite не помогает,
если репо публичный или уже склонирован).

ПЛОХО:
```python
DATABASE_URL = "postgresql://admin:secret123@localhost/mydb"
API_KEY = "sk-1234567890abcdef"

# в тестах — тоже плохо:
client = SomeAPI(api_key="test-key-hardcoded")
```

ХОРОШО:
```python
import os

DATABASE_URL = os.environ["DATABASE_URL"]   # fail-fast если нет
API_KEY = os.environ["API_KEY"]
```

#### Fail-fast на обязательных переменных окружения

`os.environ.get("KEY", "default")` в production — тихий сбой при неправильной
конфигурации. Читай без default: если переменная обязательна — её отсутствие
должно остановить сервис при старте.

ПЛОХО:
```python
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")   # в prod "dev-secret" — дыра
DB_HOST = os.getenv("DB_HOST", "localhost")               # в prod может быть не то
```

ХОРОШО:
```python
import os

SECRET_KEY = os.environ["SECRET_KEY"]   # KeyError при старте — лучше, чем тихая дыра
DB_HOST = os.environ["DB_HOST"]
```

#### `.env.example` в репо, `.env` в `.gitignore`

ХОРОШО (структура репо):
```
.env.example    # в git — шаблон с пустыми значениями
.env            # в .gitignore — реальные секреты
```

```bash
# .env.example
DATABASE_URL=
SECRET_KEY=
API_KEY=
```

---

### 8. Типизация

#### Type hints на всех публичных функциях

Публичный API без аннотаций — это неявный контракт. Аннотации позволяют
mypy ловить ошибки статически, а IDE — давать автодополнение.

ПЛОХО:
```python
def process_order(order_id, user, amount):   # нет аннотаций
    ...

def get_user(pk):                            # неясно что возвращает
    ...
```

ХОРОШО:
```python
import uuid
from decimal import Decimal

def process_order(order_id: uuid.UUID, user_id: int, amount: Decimal) -> bool:
    ...

def get_user(pk: int) -> "User | None":     # явно — может вернуть None
    ...
```

#### `X | None` вместо `Optional[X]` (Python 3.10+)

`Optional[X]` — синоним `Union[X, None]`. В Python 3.10+ `X | None` чище и
читаемее. В 3.9 и ниже — `Optional[X]` или `from __future__ import annotations`.

ХОРОШО (Python 3.10+):
```python
def find_user(email: str) -> User | None:
    ...

def parse_date(raw: str) -> datetime | None:
    ...
```

#### `Any` — последнее средство с обоснованием

`Any` отключает проверку типов для этой переменной. Допустимо на границах
с нетипизированным кодом, но должно быть обосновано комментарием.

ПЛОХО:
```python
from typing import Any

def process(data: Any) -> Any:   # Any везде = нет типизации вообще
    ...
```

ХОРОШО:
```python
from typing import Any

def deserialize(raw: bytes) -> Any:
    # Any здесь потому что json.loads возвращает Union[dict, list, str, int, float, bool, None]
    # и caller должен сам проверить тип
    return json.loads(raw)
```

### 9. Импорты

_(заполняется в шаге 6)_

### 10. Строки и форматирование

_(заполняется в шаге 6)_

### 11. Константы и magic numbers/strings

_(заполняется в шаге 6)_

### 12. Документация кода

_(заполняется в шаге 7)_

### 13. TODO и технический долг

_(заполняется в шаге 7)_

---

## Anti-patterns — категорически НЕ делаем

_(заполняется в шаге 7)_

---

## Related skills

_(заполняется в шаге 7)_
