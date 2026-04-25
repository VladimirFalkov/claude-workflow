---
name: coding-django
description: Django coding patterns — applied when CLAUDE.md stack declares `backend: django`. Covers multi-tenant models (company_fk, CompanyScopedQuerySet), services layer, transaction boundaries, AuditLog pattern, CBV conventions, form security (IDOR protection), Django URL namespacing, signal discipline, migration best practices. Works with testing-django on the testing side and extends coding-rules.
type: skill
---

# Coding Django — паттерны для Django-приложений

Применяется когда `CLAUDE.md` объявляет `backend: django`. Расширяет `coding-rules`
Django-специфичными конвенциями. Правила из `coding-rules` (UUID PK, UTC datetime, Decimal,
pathlib и др.) здесь не повторяются — применяются вместе.

## Принципы

1. **Multi-tenancy через `company_fk` + `CompanyScopedQuerySet`.** Никогда `.objects.all()` на tenant-scoped модели в production-коде — только `.for_company(company)`.
2. **Services layer для бизнес-логики.** Views — тонкие: принять request, вызвать service, вернуть response. ORM-вызовы и бизнес-инварианты — в сервисах.
3. **`transaction.atomic` на публичных сервисах** где нужна all-or-nothing семантика. Вложенные atomic — через `savepoint`.
4. **AuditLog через централизованный паттерн**, не руками в каждой view. Вызывается из service, не из view.
5. **Signals — крайний случай**, только для денормализации и cache invalidation. Никакой бизнес-логики в signals.
6. **CBV over FBV** для стандартных CRUD-операций. FBV — для одноразовой логики без стандартного lifecycle.
7. **Security в forms:** `company_fk`, `user_fk` и любые ownership-поля — **никогда** из `request.POST`. Только из request-контекста или kwargs.

---

## Правила по разделам

### 1. Структура приложения

#### Convention: `apps/<name>/` с разделением по слоям

Каждое Django-приложение — отдельная директория с фиксированной структурой.
`services/` — пакет (не один файл), `views/` тоже пакет если логики много.

ХОРОШО:
```
apps/
└── orders/
    ├── __init__.py
    ├── models.py
    ├── managers.py          ← QuerySet scoping
    ├── forms.py
    ├── urls.py
    ├── permissions.py
    ├── views/               ← пакет если много views
    │   ├── __init__.py
    │   ├── order_views.py
    │   └── report_views.py
    ├── services/            ← пакет, по одному модулю на домен
    │   ├── __init__.py      ← re-export через __all__
    │   ├── create.py
    │   ├── fulfill.py
    │   └── audit.py
    └── migrations/
```

`services/__init__.py` собирает публичный API сервисного слоя:
```python
from .create import create_order
from .fulfill import fulfill_order, cancel_order

__all__ = ["create_order", "fulfill_order", "cancel_order"]
```

#### `settings/` — split-конфигурация

Одного `settings.py` на все окружения — ошибка. Split позволяет держать
prod-специфику отдельно и не тащить dev-зависимости в production.

ХОРОШО:
```
config/
└── settings/
    ├── __init__.py     ← пусто или re-export base
    ├── base.py         ← общие настройки
    ├── dev.py          ← from .base import * + DEBUG = True
    ├── prod.py         ← from .base import * + prod-overrides
    └── test.py         ← from .base import * + TEST DB
```

---

### 2. Модели

#### `BaseModel` — единственный абстрактный базовый класс

Все tenant-scoped модели наследуют от `BaseModel`. Он добавляет UUID PK,
временные метки и `deleted_at` для soft-delete. Не изобретаем для каждой
модели своё — единый паттерн.

```python
import uuid
from django.db import models

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
```

#### Обязательные поля для tenant-scoped моделей

Каждая модель, принадлежащая компании/организации, должна иметь `company`
FK с `on_delete=PROTECT`. `CASCADE` на company опасен — случайное удаление
tenant'а уничтожит все его данные.

ПЛОХО:
```python
class Order(models.Model):
    # нет company_fk — данные не изолированы между tenant'ами
    number = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
```

ХОРОШО:
```python
from apps.accounts.models import Company

class Order(BaseModel):
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,      # не CASCADE
        related_name="orders",
    )
    number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=OrderStatus.choices)

    class Meta:
        indexes = [
            models.Index(fields=["company", "status"]),
        ]
        ordering = ["-created_at"]
```

#### Enum через `models.TextChoices` / `models.IntegerChoices`

Magic strings в `choices` — антипаттерн. `TextChoices` даёт доступ к константам
через `OrderStatus.PENDING`, автодополнение, безопасное сравнение.

ПЛОХО:
```python
STATUS_CHOICES = [("pending", "Pending"), ("active", "Active")]
status = models.CharField(choices=STATUS_CHOICES, ...)

if order.status == "pending":   # magic string
```

ХОРОШО:
```python
class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE  = "active",  "Active"
    CLOSED  = "closed",  "Closed"

status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)

if order.status == OrderStatus.PENDING:   # константа, не строка
```

### 3. QuerySets и Managers

_(заполняется в шаге 3)_

### 4. Services layer

_(заполняется в шаге 4)_

### 5. Views

_(заполняется в шаге 5)_

### 6. Forms

_(заполняется в шаге 5)_

### 7. AuditLog pattern

_(заполняется в шаге 6)_

### 8. URLs

_(заполняется в шаге 6)_

### 9. Signals

_(заполняется в шаге 7)_

### 10. Миграции

_(заполняется в шаге 7)_

### 11. Middleware

_(заполняется в шаге 7)_

---

## Anti-patterns — категорически НЕ делаем

_(заполняется в шаге 8)_

---

## Related skills

_(заполняется в шаге 8)_
