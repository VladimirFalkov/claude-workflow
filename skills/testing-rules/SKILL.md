---
name: testing-rules
description: Use whenever writing, modifying, or reviewing tests in any Python project (Django, FastAPI, pure Python). Applies to every TDD cycle (RED → GREEN → REFACTOR) and to code review. Enforces anti-cheating rules: no tautological assertions, no confidence tests, proper side-effect verification, mutation-resistance, enum constants over magic strings, security-test docstrings. Works in tandem with testing-django (Django-specific) or equivalent framework skills when present.
---

# Testing rules — правила написания тестов

Применяются всегда — при написании нового теста, правке существующего, и при ревью. Стек-агностичны: Django, FastAPI, чистый Python.

## Принципы

1. **1 инвариант = 1 тест.** Не пишем тесты ради coverage-метрики. Каждый тест ловит конкретный риск.
2. **Тест проверяет поведение, не реализацию.** Инвариант пользователя, а не формулу из кода.
3. **Тест должен ловить mutations.** Если можно сломать код так, что тест не заметит — тест слабый.
4. **Side effects обязательны.** Status code / return value — это не всё; проверяем DB state, audit, session, redirect target, внешние вызовы.
5. **Никаких magic strings.** Используем enum-константы (`User.Status.ACTIVE`, не `"active"`).
6. **RED должен быть правдивым.** Падение по AssertionError, не по ImportError/NameError.
7. **Когда меняется код — тесты падают.** Если изменил поведение и тесты не заметили — тесты слабые.
8. **Красная сьюта — проблема, не данность.** Тесты либо зелёные, либо явно помечены `@pytest.mark.skip` с причиной и записью в BACKLOG. Молча игнорировать упавший тест — значит соглашаться с тем, что инвариант который он защищал, больше не защищён.

## Broken-before tests

Упавший тест, доставшийся «по наследству» от предыдущих шагов или спринтов, **не безопасен**. Его статус в системе:

- **Красный без комментария** — шум. Маскирует сигнал «что-то сломал я», потому что красная сьюта уже привычна.
- **Красный с `@pytest.mark.skip` без причины** — хуже: вид честности, но инвариант тихо отключён.
- **Красный с `@pytest.mark.skip(reason="...")` + запись в BACKLOG** — приемлемо как временное состояние. Это технический долг, но он зафиксирован и виден.

Правило: если ты (Claude или разработчик) увидел упавший тест **не из своего скоупа**:
1. Диагностировать (прочитать traceback, понять почему упал).
2. Если починить локально — починить.
3. Если нет — **skip + BACKLOG запись в одном коммите**, никогда раздельно.

**Живой красный тест без плана починки — не сьюта, это руины.**

## Anti-patterns — категорически НЕ делаем

### ❌ Tautological test (тест копирует формулу из кода)

```python
# Код
def calculate_discount(price):
    return price * 0.9

# ПЛОХО: тест копирует формулу — при изменении коэффициента в коде
# кто-то скопирует формулу в тест и тест снова "пройдёт".
def test_discount():
    assert calculate_discount(100) == 100 * 0.9

# ХОРОШО: тест проверяет конкретный ожидаемый результат.
# Если коэффициент изменится — тест упадёт и заставит задуматься.
def test_discount():
    assert calculate_discount(100) == 90
```

### ❌ Confidence test (проверяет фикстуру, а не код)

```python
# ПЛОХО — проверяет что factory работает, не бизнес-логику
def test_user_created():
    UserFactory()
    assert User.objects.count() == 1

# ХОРОШО — проверяет инварианты создания
def test_user_created_with_default_active_status():
    user = UserFactory(email="x@y.com")
    assert user.email == "x@y.com"
    assert user.status == User.Status.ACTIVE
    assert user.company_fk is not None
```

### ❌ Shallow assertion (только status_code / truthy)

```python
# ПЛОХО
def test_login():
    response = client.post("/auth/login/", {...})
    assert response.status_code == 302

# ХОРОШО — проверяет куда редирект, сессию, audit
def test_login_creates_session_and_redirects_to_dashboard():
    response = client.post("/auth/login/", {...})
    assert response.status_code == 302
    assert response.url == reverse("dashboard")
    assert "_auth_user_id" in client.session
    log = AuditLog.objects.get(action=AuditLog.Action.LOGIN_SUCCESS)
    assert log.user_fk == user
```

### ❌ `.exists()` / `.count() > 0` без проверки полей

```python
# ПЛОХО — зафиксирует только что "что-то создалось"
assert AuditLog.objects.filter(action=LOGIN_SUCCESS).exists()

# ХОРОШО — ловит записи с неверным user/company/metadata
log = AuditLog.objects.get(action=AuditLog.Action.LOGIN_SUCCESS)
assert log.user_fk == user
assert log.company_fk == user.company_fk
assert log.ip_address == "127.0.0.1"
```

**Правило:** `.get()` когда ожидается ровно одна запись. `.filter()` допустим только когда явно проверяется множество (с `.count()` и iteration).

### ❌ Magic strings вместо enum-constants

```python
# ПЛОХО — при переименовании enum молча сломается
assert user.status == "pending_approval"
assert user.role == "company_admin"

# ХОРОШО — IDE/линтер ловит опечатки, рефакторинг безопасен
assert user.status == User.Status.PENDING_APPROVAL
assert user.role == User.Role.COMPANY_ADMIN
```

### ❌ 404/403 тест без проверки state unchanged

```python
# ПЛОХО — упадёт только если статус не тот
def test_forbidden_returns_404():
    response = client.post(url)
    assert response.status_code == 404

# ХОРОШО — ловит "404 но перед этим успел что-то сделать"
def test_forbidden_does_not_modify_resource():
    response = client.post(url)
    assert response.status_code == 404
    resource.refresh_from_db()
    assert resource.status == Resource.Status.PENDING
    assert AuditLog.objects.filter(action=FORBIDDEN_ACTION).count() == 0
```

### ❌ Многоцелевой тест («и X и Y и Z»)

```python
# ПЛОХО — упал тест, непонятно что именно сломалось
def test_login_and_logout_and_session_and_audit():
    ...

# ХОРОШО — точная диагностика
def test_login_creates_session(): ...
def test_login_writes_audit(): ...
def test_logout_clears_session(): ...
```

Правило: если в имени теста 2+ «и» (`and`) — разбивай.

### ❌ Trivial passthrough test

```python
# ПЛОХО — тест пройдёт даже с пустой реализацией
def test_create():
    obj = create_thing()
    assert obj is not None
```

## Обязательные проверки по типу теста

### Endpoints с side-effects (POST / PUT / DELETE)

Минимум 3 assert'а:
1. **HTTP response:** status_code + target URL редиректа
2. **DB state:** что изменилось / НЕ изменилось (через `refresh_from_db()`)
3. **Audit / events:** `.get()` с проверкой полей если должен писать, `.count() == 0` если не должен

### Security-инварианты (permissions, cross-tenant, IDOR, CSRF, auth)

Для security-тестов обязательно:
1. **Negative case** — доступ отсутствует у того кто не должен иметь
2. **State assertion** — данные НЕ модифицированы при отказе (refresh_from_db)
3. **No audit leak** — факт попытки не утекает в audit другой компании/пользователя
4. **Docstring с security reasoning** — почему 404 (не 403), почему redirect (не 403), почему empty list (не explicit denial)

Без последнего пункта через 3 месяца другой разработчик изменит 404→403 «для ясности» → security regression.

### Forms / request schemas (валидация)

Для каждой формы или pydantic schema:
1. Happy path — валидные данные → is_valid
2. Каждое обязательное поле — отсутствие → NOT valid + field in errors
3. Edge / boundary values — `max_uses=0`, пустая строка, очень длинная строка
4. **Security-поля** (company_id, user_id, role) — НЕ принимаются из request даже если переданы (IDOR-защита)

### Models / ORM (constraints)

1. Happy path создания
2. UNIQUE constraint — попытка создать дубль → IntegrityError
3. Каждое NOT NULL / non-optional поле — попытка без → IntegrityError
4. Методы модели (`is_active()`, `is_valid()`, `can_do_X()`) — все ветки true/false
5. Кастомные `clean()` / validators — все ветки ValidationError

### Services / бизнес-логика (без HTTP)

Слой сервисов тестируется отдельно от transport layer:
1. Happy path
2. Все ветки if/else внутри сервиса
3. Каждое `raise` — явно проверить что исключение брошено в нужных условиях
4. **Transactional boundary** — если сервис atomic, проверить что при ошибке НИЧЕГО не сохранилось (через фейковое исключение на последнем шаге)

## Mutation testing — самопроверка

После написания любого значимого теста — задай 3 вопроса:

1. **Что если я удалю реализацию полностью?** Тест падает? (ожидаемо — да)
2. **Что если я инвертирую условие (`if x` → `if not x`)?** Тест падает? (должен)
3. **Что если я закомментирую `record_event(...)` / `save()` / другие side-effects?** Тест падает? (если нет — тест не проверяет side-effects)

Ответ «тест всё равно пройдёт» на любой вопрос → тест слабый, переделать.

**Применяй это правило особенно к:**
- Audit / logging тестам
- Transactional тестам
- Security тестам

## RED phase — правдивый vs фальшивый

Когда тест падает в RED-фазе TDD, проверь **причину**:

✅ **Правдивый RED (код выполнился, поведение отсутствует):**
- `AssertionError: expected X, got Y`
- `DoesNotExist: matching query does not exist`
- `404 instead of 302`

❌ **Фальшивый RED (код не выполнился):**
- `ImportError: cannot import name 'X'`
- `NameError: name 'X' is not defined`
- `AttributeError: module has no attribute 'X'`

Фальшивый RED — тест не запустился. После написания skeleton класса тест пройдёт **даже с пустой реализацией** — ты не проверил ничего.

Правило: **после падения теста — прочитать traceback, убедиться что причина в поведении, а не в отсутствии имени**.

## Структурные правила

### Один тест — один инвариант

- 2+ `and` в имени теста → разбивай
- Множественные `assert` допустимы когда они проверяют **одно поведение с нескольких сторон** (status + state + audit), но не когда они проверяют **разные фичи**

### Имя теста = инвариант в единственном времени

```python
# ПЛОХО
def test_login(): ...
def test_test_user_login_working(): ...

# ХОРОШО
def test_valid_credentials_create_session(): ...
def test_blocked_user_cannot_login(): ...
def test_locked_ip_returns_429(): ...
```

Читаешь имя — знаешь что гарантируется.

### Enum-константы — импорт в начале файла

```python
from apps.accounts.models import (
    AuditLog,
    RegistrationLink,
    User,
)

# Далее — User.Status.ACTIVE, AuditLog.Action.LOGIN, etc.
```

IDE/линтер ловит опечатки (`"actve"` vs `User.Status.ACTIVE`).

### Docstrings для security-тестов — обязательно

```python
def test_approve_cross_tenant_returns_404():
    """Approve endpoint returns 404 for cross-tenant user.

    Returns 404 (not 403) deliberately: 403 would reveal that the resource
    exists in another company. 404 makes the endpoint indistinguishable
    from "resource does not exist at all".
    """
```

Без docstring — security decision потеряется, через 3 месяца «улучшат» и сломают.

### Fixtures — в conftest.py, не копипаст

Если фикстура используется в 2+ тест-файлах — вынести в `tests/conftest.py` или `tests/<area>/conftest.py`. Не размножать `company_a = CompanyFactory(...)` по файлам.

**Исключение:** фикстура специфична для одного теста или группы — оставить в файле.

## Коммуникация при написании теста

Когда пишешь тест (в TDD RED-phase) и перед написанием кода:

1. **Сформулируй вслух** что тест гарантирует — одно предложение
2. **Перечитай свой assert** — ответь: «можно ли удалить этот assert и тест всё равно пройдёт?»
3. **Mutation check:** «если я закомментирую ключевую строку в коде который буду писать — этот тест это заметит?»

Если на шаге 2 или 3 ответ «да, пройдёт» / «нет, не заметит» — тест слабый, перепиши.

## Related skills

- `sprint-workflow` — вызывает эти правила в TDD-фазе каждого шага
- `testing-django` — Django-специфика (RequestFactory, middleware, tenant, @pytest.mark.django_db)
- `testing-fastapi` (если есть) — FastAPI-специфика
- `audit-cycle` — ручной аудит может дополнительно укрепить тесты