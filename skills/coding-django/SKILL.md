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

#### `CompanyScopedQuerySet` — обязательный паттерн для tenant-scoped моделей

Каждая модель с `company` FK должна иметь QuerySet с методом `.for_company()`.
Это единственный легальный entry point для получения записей tenant'а.
`.objects.all()` в production-коде на tenant-scoped модели — нарушение изоляции.

```python
from django.db import models


class OrderQuerySet(models.QuerySet):
    def for_company(self, company):
        return self.filter(company=company)

    def active(self):
        return self.filter(status=OrderStatus.ACTIVE)

    def with_related(self):
        return self.select_related("company", "created_by").prefetch_related("items")


class OrderManager(models.Manager):
    def get_queryset(self):
        return OrderQuerySet(self.model, using=self._db)

    def for_company(self, company):
        return self.get_queryset().for_company(company)


class Order(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="orders")
    ...
    objects = OrderManager()
```

#### `.for_company()` — единственный entry point в views и services

ПЛОХО:
```python
# view или service
orders = Order.objects.filter(status="active")          # нет tenant-scope
orders = Order.objects.all()                            # все компании
orders = Order.objects.filter(company_id=company.id)   # дублирует логику filter
```

ХОРОШО:
```python
orders = Order.objects.for_company(request.user.company).active()
orders = Order.objects.for_company(company).with_related()
```

#### N+1: `select_related` и `prefetch_related` в QuerySet, не во view

Добавляй связанные объекты через методы QuerySet — не внутри цикла в template
или view. Метод `.with_related()` в QuerySet документирует ожидаемые join'ы.

ПЛОХО:
```python
# view
orders = Order.objects.for_company(company)
# В template: {{ order.company.name }} — N+1 запросов

# или в view явно:
for order in orders:
    print(order.created_by.email)   # N+1
```

ХОРОШО:
```python
class OrderQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("company", "created_by").prefetch_related("items")

# в view:
orders = Order.objects.for_company(company).with_related()
```

### 4. Services layer

#### Service принимает доменные объекты, не `request`

Service — это чистая бизнес-логика. Он не знает об HTTP. Принимает модели
и примитивы, возвращает модели или выбрасывает исключения. View передаёт
в service только то, что нужно — не весь request.

ПЛОХО:
```python
# service.py
def create_order(request):
    company = request.user.company          # service знает о HTTP
    data = request.POST.get("amount")       # parsing тоже в service
    ...
```

ХОРОШО:
```python
# service.py
from django.core.exceptions import ValidationError

def create_order(company, user, amount: Decimal, notes: str = "") -> Order:
    """Создать заказ. Raises ValidationError если данные некорректны."""
    if amount <= 0:
        raise ValidationError("Сумма заказа должна быть положительной.")
    order = Order.objects.create(company=company, created_by=user, amount=amount, notes=notes)
    return order

# view.py — тонкий
def order_create_view(request):
    form = OrderForm(request.POST)
    if form.is_valid():
        order = create_order(
            company=request.user.company,
            user=request.user,
            **form.cleaned_data,
        )
        return redirect("orders:detail", pk=order.pk)
```

#### `transaction.atomic` на service-уровне

Если service делает несколько write-операций — они должны быть атомарны.
Декоратор `@transaction.atomic` проще чем контекстный менеджер, но
контекстный менеджер точнее ограничивает границу транзакции.

```python
from django.db import transaction

@transaction.atomic
def fulfill_order(order: Order, fulfilled_by) -> Order:
    order.status = OrderStatus.FULFILLED
    order.fulfilled_by = fulfilled_by
    order.save(update_fields=["status", "fulfilled_by", "updated_at"])

    # Аудит — тоже в транзакции
    AuditLog.objects.create(
        company=order.company,
        action="order_fulfilled",
        actor=fulfilled_by,
        object_id=order.pk,
    )
    return order
```

Для отложенных эффектов (отправка email, вебхуки) — `transaction.on_commit()`:

```python
@transaction.atomic
def fulfill_order(order: Order, fulfilled_by) -> Order:
    ...
    transaction.on_commit(lambda: send_fulfillment_email.delay(order.pk))
    return order
```

#### `ValidationError` для пользователя, `PermissionError` для доступа

Разные типы ошибок — разные исключения. View знает как их перехватить.

```python
from django.core.exceptions import ValidationError, PermissionDenied

def cancel_order(order: Order, cancelled_by) -> Order:
    if order.company != cancelled_by.company:
        raise PermissionDenied("Нет доступа к этому заказу.")
    if order.status == OrderStatus.FULFILLED:
        raise ValidationError("Выполненный заказ нельзя отменить.")
    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order
```

### 5. Views

#### CBV предпочтительнее FBV для CRUD

CBV (`CreateView`, `UpdateView`, `ListView`) устраняет boilerplate и даёт
стандартный lifecycle (get/post/form_valid). FBV допустим для одноразовой
логики без стандартного CRUD.

ХОРОШО:
```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView
from django.urls import reverse_lazy

class OrderCreateView(LoginRequiredMixin, CreateView):
    model = Order
    form_class = OrderCreateForm
    template_name = "orders/order_form.html"
    success_url = reverse_lazy("orders:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = self.request.user.company   # tenant через kwargs
        return kwargs

    def form_valid(self, form):
        # form_valid — тонкий: только вызов service
        try:
            create_order(
                company=self.request.user.company,
                user=self.request.user,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        return super().form_valid(form)
```

---

### 6. Forms

#### `company_fk` / `user_fk` — никогда из `request.POST`

Ownership-поля в `Meta.fields` — IDOR: пользователь может подменить
`company_id` на чужой в POST-запросе. Эти поля передаются через `__init__`
из view-контекста, не из данных формы.

ПЛОХО:
```python
class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["company", "amount", "notes"]   # company из POST — IDOR
```

ХОРОШО:
```python
class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["amount", "notes"]   # company НЕ в полях формы

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company          # получаем из view, не из POST

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.company = self.company  # устанавливаем в save
        if commit:
            instance.save()
        return instance
```

#### `clean_<field>()` для cross-field валидации

ХОРОШО:
```python
class OrderCreateForm(forms.ModelForm):
    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Сумма должна быть положительной.")
        return amount

    def clean(self):
        cleaned = super().clean()
        # cross-field: amount + currency должны быть согласованы
        return cleaned
```

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
