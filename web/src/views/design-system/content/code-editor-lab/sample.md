# Как сервис принимает заказ: десять фрагментов одной системы

Небольшая система принимает заказы, складывает их в базу и показывает статус. Она собрана из частей на разных языках, и ниже — по одному фрагменту от каждой части. Каждый фрагмент нарочно насыщен разными токенами: ключевыми словами, строками, числами, комментариями, типами и аннотациями. Так сразу видно, что подсветка различает, а что сливается в один цвет.

## Модель заказа (Java)

Ядро домена. Здесь пакет и импорты, аннотация, record, enum, generic, лямбда, тернарный оператор и javadoc.

```java
package com.example.orders;

import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

/**
 * A customer's order. Immutable: a change produces a new instance.
 */
public record Order(long id, long customerId, List<OrderItem> items, Status status) {

    public static final int MAX_ITEMS = 50;

    public enum Status { PENDING, PAID, SHIPPED, CANCELED }

    public Order {
        Objects.requireNonNull(items, "items");
        if (items.size() > MAX_ITEMS) {
            throw new IllegalArgumentException(items.size() + " items, the limit is " + MAX_ITEMS);
        }
    }

    @Override
    public String toString() {
        return "Order#" + id + " [" + status + "]";
    }

    public BigDecimal total() {
        return items.stream()
                .map(item -> item.price().multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public boolean isFinal() {
        return status == Status.SHIPPED || status == Status.CANCELED ? true : false;
    }
}
```

## HTTP-шлюз (Go)

Принимает запрос и отдаёт его дальше. Здесь структура с тегами, метод с получателем, множественный возврат, обработка ошибки, defer и горутина.

```go
package gateway

import (
	"encoding/json"
	"log"
	"net/http"
	"time"
)

const requestTimeout = 5 * time.Second

type CreateOrderRequest struct {
	CustomerID int64    `json:"customer_id"`
	Items      []string `json:"items"`
	Express    bool     `json:"express,omitempty"`
}

type Handler struct {
	queue chan<- CreateOrderRequest
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()

	var req CreateOrderRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}
	// Очередь развязывает шлюз и обработчик: шлюз отвечает сразу, не дожидаясь базы
	go func() { h.queue <- req }()

	w.WriteHeader(http.StatusAccepted)
	log.Printf("queued order for customer %d, %d items", req.CustomerID, len(req.Items))
}
```

## Обработчик очереди (Python)

Забирает заказ из очереди, проверяет и пишет в базу. Здесь декоратор, аннотации типов, f-строка, async/await, исключение и комментарий.

```python
from dataclasses import dataclass, field
from decimal import Decimal

MAX_ITEMS = 50


@dataclass(frozen=True)
class OrderItem:
    sku: str
    quantity: int
    price: Decimal = Decimal("0.00")


@dataclass
class Order:
    customer_id: int
    items: list[OrderItem] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((item.price * item.quantity for item in self.items), Decimal(0))


class OrderRejected(ValueError):
    pass


async def accept_order(order: Order, repo: "OrderRepository") -> int | None:
    # Пустой заказ отклоняется до записи в базу, иначе в базе останется строка без позиций
    if not order.items:
        raise OrderRejected("order has no items")
    if len(order.items) > MAX_ITEMS:
        raise OrderRejected(f"{len(order.items)} items, the limit is {MAX_ITEMS}")
    order_id = await repo.insert(order)
    print(f"accepted #{order_id}: total={order.total:.2f}, paid={True}, note={None}")
    return order_id
```

## Вебхук платёжной системы (PHP)

Платёжная система сообщает, что заказ оплачен. Здесь namespace, строгие типы, атрибут, свойства конструктора, match, интерполяция строки и nullsafe-оператор.

```php
<?php

declare(strict_types=1);

namespace App\Webhook;

use App\Orders\OrderRepository;
use Psr\Log\LoggerInterface;

#[Route('/webhook/payment', methods: ['POST'])]
final class PaymentWebhook
{
    private const SIGNATURE_HEADER = 'X-Signature';

    public function __construct(
        private readonly OrderRepository $orders,
        private readonly LoggerInterface $logger,
        private readonly string $secret = '',
    ) {}

    public function __invoke(array $payload, array $headers): int
    {
        // Подпись проверяется первой: без неё любой может отметить заказ оплаченным
        if (!hash_equals(hash_hmac('sha256', json_encode($payload), $this->secret), $headers[self::SIGNATURE_HEADER] ?? '')) {
            return 403;
        }

        $order = $this->orders->find((int) $payload['order_id']);
        $status = match ($payload['event']) {
            'payment.succeeded' => 'paid',
            'payment.refunded'  => 'canceled',
            default             => null,
        };

        $this->logger->info("order {$order?->id} moved to {$status}");
        return $status === null ? 422 : 200;
    }
}
```

## Виджет статуса (JavaScript)

Показывает покупателю статус заказа и обновляет его сам. Здесь класс, приватное поле, async/await, деструктуризация, шаблонная строка, регулярное выражение и optional chaining.

```javascript
const POLL_INTERVAL_MS = 15_000
const ORDER_CODE = /^ORD-(\d{6})$/

export class OrderStatusWidget {
  #timer = null

  constructor(element, { orderCode, onFinal = () => {} } = {}) {
    if (!ORDER_CODE.test(orderCode)) {
      throw new TypeError(`bad order code: ${orderCode}`)
    }
    this.element = element
    this.orderCode = orderCode
    this.onFinal = onFinal
  }

  async refresh() {
    const response = await fetch(`/api/orders/${this.orderCode}`)
    const { status, updatedAt } = await response.json()
    this.element.textContent = `${status} · ${new Date(updatedAt).toLocaleString()}`
    this.element.dataset.status = status
    // Финальный статус больше не меняется, опрашивать дальше незачем
    if (['shipped', 'canceled'].includes(status)) {
      this.stop()
      this.onFinal?.(status)
    }
  }

  start() {
    this.refresh()
    this.#timer = setInterval(() => this.refresh(), POLL_INTERVAL_MS)
  }

  stop() {
    clearInterval(this.#timer)
    this.#timer = null
  }
}
```

## Оформление статусов (CSS)

Плашка статуса меняет цвет по состоянию заказа. Здесь пользовательские свойства, селектор атрибута, псевдоэлемент, медиазапрос, `@keyframes`, единицы и цвета в разных записях.

```css
:root {
  --status-radius: 999px;
  --status-pending: #b08800;
  --status-paid: rgb(26 127 55);
  --status-canceled: hsl(356deg 72% 47%);
}

.order-status {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 2px 10px;
  border-radius: var(--status-radius);
  font: 500 13px/1.4 system-ui, sans-serif;
}

/* Цвет плашки задаёт атрибут, который ставит виджет */
.order-status[data-status="pending"] { color: var(--status-pending); }
.order-status[data-status="paid"]    { color: var(--status-paid); }
.order-status[data-status="canceled"]::before {
  content: "✕";
  color: var(--status-canceled);
}

@keyframes pulse {
  from { opacity: 1; }
  to   { opacity: 0.4; }
}

@media (prefers-reduced-motion: no-preference) {
  .order-status[data-status="pending"] { animation: pulse 1.2s ease-in-out infinite alternate; }
}
```

## README сервиса (Markdown)

Описание для разработчика, который впервые открыл репозиторий. Здесь заголовки, выделение, списки, ссылка, картинка, цитата, таблица и встроенный код.

```markdown
# Orders service

**Orders** принимает заказы и отдаёт их статус. Документация — в [вики](https://wiki.example.com/orders).

![Схема сервиса](docs/schema.png)

## Запуск

1. Скопировать `.env.example` в `.env`.
2. Поднять базу: `docker compose up -d db`.
3. Запустить сервис — *без* флага `--debug` в проде.

> Миграции не применяются при старте сами — только командой `migrate`.

| Переменная | Назначение | По умолчанию |
| --- | --- | --- |
| `APP_PORT` | порт HTTP | `8080` |
| `DB_DSN` | строка подключения | — |

- [x] приём заказов
- [ ] возвраты
```

## Конфигурация сервиса (JSON)

Настройки лежат в одном файле. В нём есть все типы значений JSON: строки, числа, логические значения, `null`, массивы и вложенные объекты.

```json
{
  "service": "orders",
  "version": "1.4.2",
  "debug": false,
  "port": 8080,
  "timeout_seconds": 12.5,
  "fallback_region": null,
  "database": {
    "provider": "postgresql",
    "pool_size": 10,
    "replicas": ["db-1.internal", "db-2.internal"]
  },
  "features": {
    "express_delivery": true,
    "max_items_per_order": 50
  }
}
```

## Настройки PHP для вебхука (INI)

Вебхук работает под PHP-FPM, и его лимиты задаёт ini-файл. Здесь секции, ключи со значениями разных типов, комментарии двух видов и строка в кавычках.

```ini
; Лимиты для пула вебхуков: запросы короткие, память нужна небольшая
[PHP]
memory_limit = 128M
max_execution_time = 10
display_errors = Off
error_log = "/var/log/php/webhook.log"

[Date]
date.timezone = Europe/Moscow

# Сессии вебхуку не нужны
[Session]
session.auto_start = 0
session.use_strict_mode = 1
```

## Переменные окружения (env)

Секреты и адреса не лежат в репозитории, их задаёт `.env`. Здесь пары ключ–значение, комментарии, значения в кавычках и без, подстановка другой переменной и пустое значение.

```env
# Окружение и порт
APP_ENV=production
APP_PORT=8080
APP_DEBUG=false

# База: DSN собирается из частей ниже
DB_HOST=db-1.internal
DB_PORT=5432
DB_NAME=orders
DB_DSN="postgresql://orders@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# Платёжная система
PAYMENT_WEBHOOK_SECRET='s3cr3t-value-with-$-sign'
PAYMENT_SANDBOX=
```

## Что проверить

- В светлой и в тёмной теме у каждого блока видны разные цвета: ключевые слова, строки, числа, комментарии.
- JSON: ключи отличаются от строковых значений, а `true`, `false`, `null` и числа — от тех и других.
- Python: подсвечены декораторы, аннотации типов и f-строки.
- Markdown: подсветка внутри блока, а не отрисованная разметка.
- INI и env: секции, ключи и значения различаются; у env подсветка вообще есть.
- В режиме правки подсветка та же, что в просмотре.
