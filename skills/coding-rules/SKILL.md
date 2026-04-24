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

_(заполняется в шаге 2)_

### 2. Время

_(заполняется в шаге 2)_

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
