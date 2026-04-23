---
name: testing-django
description: Use whenever writing tests for Django code in this project. Django-specific patterns on top of global testing-rules. Covers @pytest.mark.django_db usage, RequestFactory + middleware chains, tenant isolation patterns (cross-company tests, threadlocal cleanup), client.force_login vs session, refresh_from_db invariants, AuditLog assertions with .get() and metadata checks, @pytest.mark.parametrize for permission matrices, factory_boy usage. Always applied together with global testing-rules skill.
---

# Testing Django — специфика этого проекта

Дополнение к `testing-rules` (global). Читается **вместе** с ним. Django-специфика: pytest-django, factory_boy, middleware, tenant isolation, AuditLog.

## Стек

- pytest-django, factory_boy
- CompanyScopedQuerySet + TenantMiddleware (threadlocal `company_id`)
- AuditLog с user_fk, company_fk, metadata (JSON)
- Кастомная User модель (status, role enums)

## Маркеры pytest

### `@pytest.mark.django_db` — когда нужен

**Нужен:**
- Любой тест который пишет/читает БД
- Тесты form.is_valid() если форма делает DB-запросы (ModelForm, queryset validation)
- Тесты request.session.save() (session хранится в БД)
- Тесты factory-фикстур которые создают записи

**НЕ нужен:**
- Тесты чистых функций без ORM
- Тесты template render с передачей `context` без Model instances
- Unit-тесты сервисов с полностью мокнутым ORM

```python
# ПЛОХО — упадёт с RuntimeError "Database access not allowed"
def test_login_creates_session(client, user):
    client.force_login(user)  # ← пишет в БД

# ХОРОШО
@pytest.mark.django_db
def test_login_creates_session(client, user):
    client.force_login(user)
```

### `@pytest.mark.django_db(transaction=True)` — когда нужен

**Нужен когда тест проверяет transactional behavior:**
- Тест что `@transaction.atomic` откатывает при исключении
- Тест race condition (параллельные запросы)
- Тест signals on_commit

**НЕ нужен для обычных тестов.** `transaction=True` медленнее в 3-5 раз (реальные commits вместо savepoint rollback).

## RequestFactory + middleware chain

Для интеграционных тестов template rendering, сессий, messages:

```python
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages import add_message, SUCCESS, get_messages

@pytest.mark.django_db
def test_messages_rendered_in_base_template():
    factory = RequestFactory()
    request = factory.get("/")

    # Middleware chain ДОЛЖЕН идти в правильном порядке:
    # session → messages (messages зависит от session)
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    MessageMiddleware(lambda r: None).process_request(request)

    add_message(request, SUCCESS, "Всё хорошо")
    html = render_to_string("base.html", {"messages": get_messages(request)})

    assert "Всё хорошо" in html
```

**Не делай самодельный `messages = [SimpleMessage(...)]`** — это тестирует шаблон, а не интеграцию с messages framework.

## Client — выбор способа логина

### `client.force_login(user)` — по умолчанию
Быстро, без проверки пароля, устанавливает session напрямую. Используй когда auth **не** является предметом теста.

```python
@pytest.fixture
def admin_client(admin_user):
    c = Client()
    c.force_login(admin_user)
    return c
```

### `client.post("/auth/login/", {...})` — когда auth является предметом теста
Проходит через реальный LoginView, проверяет пароль, rate-limit, lockout, audit. Используй в тестах `test_auth_views.py`.

### `Client()` без логина — для anonymous тестов
Используй для negative-tests: «anonymous redirect на login».

```python
@pytest.mark.parametrize("method,url_name,kwargs", [
    ("get", "accounts:link_list", {}),
    ("post", "accounts:user_approve", {"pk": 1}),
])
@pytest.mark.django_db
def test_anonymous_redirected_to_login(method, url_name, kwargs):
    client = Client()
    response = getattr(client, method)(reverse(url_name, kwargs=kwargs))
    assert response.status_code == 302
    assert "login" in response.url
```

## Tenant isolation — паттерны

### Cross-tenant тесты — обязательные компоненты

Для каждого tenant-scoped endpoint — тест что admin компании A **не может** трогать ресурсы компании B.

```python
@pytest.mark.django_db
def test_approve_user_from_other_company_returns_404(client_a, company_b):
    """Approve endpoint returns 404 for cross-tenant user.

    Returns 404 (not 403) deliberately: 403 would leak existence of
    users in other companies. 404 is indistinguishable from "not found".
    """
    pending_user_b = UserFactory(pending=True, company_fk=company_b)
    audit_count_before = AuditLog.objects.count()

    response = client_a.post(
        reverse("accounts:user_approve", kwargs={"pk": pending_user_b.pk})
    )

    # 1. HTTP — 404, не 403
    assert response.status_code == 404

    # 2. State unchanged — user не одобрен
    pending_user_b.refresh_from_db()
    assert pending_user_b.status == User.Status.PENDING_APPROVAL

    # 3. No audit leak — попытка не утекает в audit чужой компании
    assert AuditLog.objects.count() == audit_count_before
```

### Threadlocal cleanup — `get_current_company_id() is None`

TenantMiddleware ставит `company_id` в threadlocal/contextvar на request. **Обязателен тест что после запроса threadlocal очищен** — иначе следующий запрос в том же процессе унаследует чужой контекст.

```python
from apps.core.tenant import get_current_company_id

@pytest.mark.django_db
def test_request_cleans_up_tenant_context(client_a):
    """Tenant context must not leak to subsequent requests in same process."""
    client_a.get(reverse("accounts:link_list"))
    assert get_current_company_id() is None
```

**Это security-критичный тест.** Без него регрессия threadlocal leak уйдёт в прод незамеченной.

### IDOR-защита — проверка что company_fk из request.user, не из POST

Для каждого create-endpoint — тест что admin не может подделать POST data для создания ресурса в чужой компании.

```python
@pytest.mark.django_db
def test_created_resource_belongs_to_requesting_user_company(
    client_a, admin_a, company_a, company_b
):
    """Resource company must come from request.user, not POST data (IDOR protection)."""
    response = client_a.post(
        reverse("accounts:link_create"),
        {"max_uses": 10, "company_fk": company_b.pk},  # attempt to inject
    )
    created = RegistrationLink.objects.filter(creator_fk=admin_a).first()
    assert created is not None, "Resource must be created"
    assert created.company_fk == company_a, (
        "Resource company must come from request.user, not POST data"
    )
```

## AuditLog — паттерн проверки

Всегда `.get()` с явными assert полей:

```python
# ХОРОШО
log = AuditLog.objects.get(action=AuditLog.Action.USER_APPROVED)
assert log.user_fk == admin          # кто сделал
assert log.company_fk == pending.company_fk  # в какой компании
assert log.ip_address is not None    # IP записан
assert log.metadata["approved_user_id"] == str(pending.pk)  # ключевые данные
```

### Secrets в metadata — проверка отсутствия

Для audit-записей где передаются токены / пароли / секреты — проверить что **полного секрета в metadata нет**:

```python
log = AuditLog.objects.get(action=AuditLog.Action.REGISTRATION_COMPLETED_PENDING)
# Token stored as prefix only — full token is a live credential
assert "token" not in log.metadata or len(log.metadata["token"]) < 16
```

### Audit не пишется при отказе — обязательная проверка

Для negative-тестов (403/404/validation error) — явно проверить `count == before`:

```python
audit_count_before = AuditLog.objects.count()
response = client.post(url, invalid_data)
assert response.status_code == 403
assert AuditLog.objects.count() == audit_count_before  # никаких утечек
```

## factory_boy — использование

### Factories в `tests/factories/<app>.py`

```python
class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    company_fk = factory.SubFactory(CompanyFactory)
    status = User.Status.ACTIVE
    role = User.Role.COMPANY_USER

    class Params:
        pending = factory.Trait(status=User.Status.PENDING_APPROVAL)
        blocked = factory.Trait(status=User.Status.BLOCKED)
        admin = factory.Trait(role=User.Role.COMPANY_ADMIN)
```

### Использование

```python
user = UserFactory()                              # default: active + company_user
pending = UserFactory(pending=True)               # trait
admin_a = UserFactory(admin=True, company_fk=company_a)  # trait + override
```

**Правило:** traits именуются по состоянию (`pending`, `blocked`, `admin`), а не по действию (`create_pending_user` — плохо).

### НЕ обходи factory_boy ручными вызовами

```python
# ПЛОХО — дублирует логику factory
def test_x():
    user = User.objects.create(
        email="x@y.com",
        company_fk=company,
        status="active",
        role="company_user",
        ...
    )

# ХОРОШО
def test_x():
    user = UserFactory()
```

Исключение — когда тест нужен именно **без** factory логики (например, проверка что модель создаётся с минимальными полями).

## `@pytest.mark.parametrize` — permission matrix

Для тестов permissions / ролей / методов — параметризуй, не копипасть:

```python
@pytest.mark.django_db
@pytest.mark.parametrize("role,expected_status", [
    (User.Role.COMPANY_USER, 403),
    (User.Role.COMPANY_ADMIN, 200),
    (User.Role.SUPERADMIN, 200),
])
def test_user_list_access_by_role(role, expected_status, company):
    user = UserFactory(role=role, company_fk=company)
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:user_list"))
    assert response.status_code == expected_status
```

Это **matrix-тест** — покрывает все роли одним блоком. Легко добавлять новые роли.

## `refresh_from_db()` — когда обязателен

После любого POST endpoint который должен изменить (или не изменить) модель:

```python
# Обязательно: ты проверяешь state, который мог измениться в view
response = client.post(reverse("accounts:user_approve", kwargs={"pk": user.pk}))
user.refresh_from_db()
assert user.status == User.Status.ACTIVE
```

**Без `refresh_from_db()`** Python-объект `user` остаётся с кэшированными полями из фикстуры — тест может пройти, а реальная БД быть в другом состоянии.

**Правило:** если после POST идёт `assert obj.<field> == ...` — перед assert всегда `obj.refresh_from_db()`.

## Templates — тесты наследования

Если в проекте есть `base.html` — параметризованный тест что все view-шаблоны extend его:

```python
AUTH_TEMPLATES = [
    "accounts/login.html",
    "accounts/register_by_link.html",
    # ...
]

@pytest.mark.parametrize("template_name", AUTH_TEMPLATES)
def test_auth_template_extends_base(template_name):
    """Each auth template must extend base.html (rendered HTML contains <!DOCTYPE>)."""
    html = render_to_string(template_name, _minimal_context(template_name))
    assert "<!DOCTYPE html>" in html  # приходит из base
```

## Migrations — тестирование

### `--dry-run` перед коммитом

В тестах миграций **не запускаем** `migrate`. Проверяем `makemigrations --check --dry-run`:

```python
# Нельзя: manage.py migrate внутри теста
# Правильная проверка — через CI: makemigrations --check не должен генерировать новые
```

### Data migrations — отдельный тест

Если миграция содержит `RunPython`, напиши тест который проверяет что `reverse_code` работает:

```python
@pytest.mark.django_db(transaction=True)
def test_data_migration_reversible(migrator):
    # использует pytest-django-migrations или django_test_migrations
    # проверяет forward + reverse
    ...
```

## Anti-patterns специфичные для Django

### ❌ Тест session без @pytest.mark.django_db
`client.session` пишется в БД (или cache которому нужна настройка). Без маркера — `DatabaseError`.

### ❌ Magic strings для status_code
```python
# ПЛОХО — цифры без контекста
assert response.status_code == 410

# ХОРОШО — через константы stdlib
from http import HTTPStatus
assert response.status_code == HTTPStatus.GONE
```

Не обязательно, но улучшает читаемость для нестандартных кодов (410, 429, 451).

### ❌ Проверка queryset через list() без порядка
```python
# ПЛОХО — тест хрупкий к изменению default ordering
users = list(User.objects.filter(company_fk=company))
assert users[0].email == "a@b.com"

# ХОРОШО — явный order_by или проверка множеством
users = User.objects.filter(company_fk=company).order_by("email")
# или:
emails = set(u.email for u in User.objects.filter(company_fk=company))
assert "a@b.com" in emails
```

### ❌ `request.user.is_authenticated` проверка без middleware
Если тест проверяет `LoginRequiredMixin` / `@login_required` — используй Client, а не RequestFactory. RequestFactory не прогоняет middleware, `request.user` будет `AnonymousUser` всегда.

## Related skills

- `testing-rules` (global) — общие anti-patterns и принципы
- `sprint-workflow` — запускает тесты в TDD цикле
- `audit-cycle` — ручной аудит
