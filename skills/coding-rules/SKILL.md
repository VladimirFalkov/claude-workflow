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

_(заполняется в шаге 3)_

### 4. Пути и файлы

_(заполняется в шаге 3)_

### 5. Обработка ошибок

_(заполняется в шаге 4)_

### 6. Логирование

_(заполняется в шаге 4)_

### 7. Секреты и конфигурация

_(заполняется в шаге 5)_

### 8. Типизация

_(заполняется в шаге 5)_

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
