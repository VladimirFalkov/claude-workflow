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

_(заполняется в шаге 2)_

### 2. Модели

_(заполняется в шаге 2)_

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
