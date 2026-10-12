"""Long and bulk demo data for ``seed_demo.py`` — the texts and the numbers no hand-written spec reaches.

The hand-written set in ``seed_demo.py`` shows every state once; it does not show what a page does
with a 60 000-character note, a progress log at its cap, sixteen journal entries or a hundred rows in
a list. This module builds that: two more workspaces and a codex, as specs of the same shape
``seed_demo.py`` already seeds.

The texts are assembled, not typed: a library of real-sounding paragraphs, lists, tables and code is
composed into articles, references, changelogs and logs of a requested length. Every text is cut to
its field's limit on a paragraph boundary — a cap reached mid-word would look like a rendering bug.

The generator is seeded with a constant, so two runs produce the same texts: a layout problem found
on one run is still there on the next.
"""

from __future__ import annotations

import random

from src.modules.codex.constants import BODY_MAX as CODEX_BODY_MAX
from src.modules.codex.constants import DESCRIPTION_MAX as CODEX_DESCRIPTION_MAX
from src.modules.notes.constants import BODY_MAX as NOTE_BODY_MAX
from src.modules.tasks.constants import (
    BODY_MAX as STAGE_BODY_MAX,
    CONSTRAINTS_MAX,
    CONTEXT_MAX,
    CRITERIA_MAX,
    DESCRIPTION_MAX,
    EVIDENCE_MAX,
    JOURNAL_BODY_MAX,
    JOURNAL_DECISION,
    JOURNAL_FACT,
    JOURNAL_FINDING,
    JOURNAL_REMARK,
    PLAN_MAX,
    PRIORITY_BURNING,
    PRIORITY_FROZEN,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PROGRESS_MAX,
    RESOLUTION_MAX,
    RESULT_MAX,
    STATUS_BACKLOG,
    STATUS_CANCELED,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_IN_TEST,
    STATUS_PLANNED,
    TITLE_MAX,
    TYPE_EXTENDED,
    TYPE_SIMPLE,
    TYPE_STANDARD,
)
from src.modules.workspace.constants import DESCRIPTION_MAX as WORKSPACE_DESCRIPTION_MAX
from src.modules.workspace.constants import TITLE_MAX as WORKSPACE_TITLE_MAX

SEED = 20261011

# Under the caps on purpose: a field filled to the last character shows the cap, a field at 97 %
# shows what a person actually writes when the text is long.
NEAR = 0.97


# ── the library ───────────────────────────────────────────────────────────────

PARAGRAPHS = [
    "Переезд на новую схему начался не с кода, а с инвентаризации: кто читает таблицу, кто пишет в неё "
    "и в какие часы. Оказалось, что кроме API в таблицу заглядывают ночной отчёт, выгрузка для "
    "бухгалтерии и одна забытая админка, которую последний раз открывали полгода назад. Каждый из "
    "этих читателей получил строку в списке, владельца и дату, после которой старая колонка для него "
    "перестаёт существовать.",

    "Двойная запись выглядит дорого только на бумаге. На деле это одна функция-зеркало, которая после "
    "каждой записи в новую таблицу повторяет её в старой, и один тест, сверяющий обе таблицы после "
    "прогона всего набора. Зато откат перестаёт быть событием: достаточно переключить чтение обратно, "
    "и ни один платёж за прошедшие сутки не теряется.",

    "Медленный тестовый стенд партнёра диктует архитектуру сильнее, чем их документация. Восемь секунд "
    "на запрос означают, что синхронный обмен из обработчика HTTP невозможен в принципе: пользователь "
    "уйдёт раньше, чем придёт ответ. Поэтому всё, что касается их системы, уходит в очередь, а "
    "интерфейс показывает состояние заявки, а не результат вызова.",

    "Идемпотентность по их идентификатору заказа решает сразу две проблемы. Повторная доставка того же "
    "заказа после сетевого сбоя больше не создаёт дубликат, а ручной перезапуск очереди оператором "
    "становится безопасным действием, которое не нужно согласовывать. Цена — уникальный индекс по "
    "внешнему ключу и аккуратная обработка конфликта при вставке.",

    "Тёмная тема ломается не там, где её делали, а там, где о ней не думали. Токены цвета покрывают "
    "кнопки и фон, но граница карточки бралась из отдельной переменной, которую никто не переопределил. "
    "В светлой теме она давала тонкую серую линию, в тёмной совпала с фоном до третьего знака, и "
    "карточки слились в одно поле.",

    "Каждое правило в кодексе должно отвечать на вопрос «почему», иначе через месяц его начнут обходить. "
    "Запрет на сырые запросы в обработчиках выглядит придиркой, пока не объяснишь, что сервисный слой — "
    "единственное место, где проверяются права и пишется журнал изменений. Правило без причины "
    "держится на авторитете, правило с причиной держится само.",

    "Миграция, которая работает на SQLite и падает на PostgreSQL, — обычное дело, если типы колонок "
    "выбраны по привычке. SQLite не проверяет ширину строк, хранит числа с плавающей точкой там, где "
    "ждали десятичные, и молча принимает значения не того типа. Поэтому каждая миграция прогоняется на "
    "обоих провайдерах до того, как попадёт в основную ветку.",

    "Регрессионный тест на исправленную ошибку пишется до исправления, а не после. Он должен упасть на "
    "старом коде с понятным сообщением, и только потом зеленеть. Тест, написанный после, слишком часто "
    "проверяет то, что код уже делает, а не то, что он должен делать, и пропускает ровно тот случай, "
    "ради которого его писали.",

    "Журнал задачи — не дневник, а память для того, кто откроет задачу через месяц. В нём остаются "
    "решения с причинами, измеренные факты с цифрами и находки, которые не относятся к задаче, но "
    "жалко потерять. Всё остальное — ход работы — живёт в отдельном поле и переписывается по мере "
    "движения, а журнал только дополняется.",

    "Релиз 2.0 убирает поддержку Python 3.9, и это решение далось не сразу. Четыре процента загрузок — "
    "немного, но за ними стоят конкретные люди на старых серверах, которые обновятся не скоро. Поэтому "
    "ветка 1.9 ещё полгода получает исправления безопасности, а в списке изменений есть отдельный "
    "раздел с инструкцией по переходу.",

    "Ревью внешнего вклада — это переговоры, а не проверка. Автор потратил вечера на код, которого от "
    "него никто не просил, и первое замечание задаёт тон всему разговору. Поэтому сначала обсуждается "
    "форма API, потом реализация, и каждое требование сопровождается готовым фрагментом кода, а не "
    "формулировкой «здесь нужен тест».",

    "Очередь без наблюдаемости — чёрный ящик, в который однажды упадёт важный заказ. На каждой заявке "
    "хранятся число попыток, время последней, текст последней ошибки и следующий запланированный "
    "запуск. Этого достаточно, чтобы оператор ответил клиенту без похода к разработчику и без чтения "
    "логов на сервере.",

    "Экспоненциальная задержка между повторами защищает не нас, а партнёра. Если их стенд лёг, сотня "
    "наших воркеров, долбящих его раз в секунду, не даст ему подняться. Задержка растёт от двух секунд "
    "до десяти минут, к ней добавляется случайный сдвиг, чтобы повторы разных заявок не совпадали по "
    "времени.",

    "Поиск по кириллице на SQLite требует отдельного внимания: встроенная функция lower знает только "
    "латиницу. Запрос, который на PostgreSQL находит «Проверку» по слову «проверка», на SQLite молча "
    "возвращает пустой список. Поэтому регистр сворачивается в Python, а в SQL уходит уже готовое "
    "значение или выборка без условия по тексту.",

    "Версия приложения живёт в одном месте — в pyproject.toml, вместе с датой релиза. Копии в "
    "package.json фронтенда и в uv.lock сверяет тест, и рассинхронизация ловится до того, как попадёт "
    "в сборку. Раньше версия правилась в трёх местах вручную, и раз в квартал одно из них забывали.",

    "Пустое состояние страницы — такой же интерфейс, как и полное. Человек, впервые открывший "
    "пространство без задач, должен понять, что здесь будет и с чего начать. Пустой список без "
    "подсказки читается как ошибка загрузки, и в половине случаев человек просто перезагружает "
    "страницу.",

    "Горячие клавиши в меню строки — буквы по смыслу, а не цифры по порядку. Цифра означает «n-й "
    "пункт» и сдвигается, когда меню меняет состав; буква означает действие и запоминается один раз "
    "для всех экранов. Сопоставление идёт по физической клавише, поэтому E работает и в русской "
    "раскладке, где на ней написана «У».",

    "Мягкое удаление дешевле, чем кажется, и дороже, чем хочется. Каждый запрос получает условие на "
    "пустую отметку удаления, каждый уникальный индекс становится частичным, а восстановление требует "
    "проверки, не занят ли за это время освободившийся слаг. Зато человек, удаливший не то, может "
    "вернуть его сам, без похода к администратору с бэкапом.",

    "Блокировки в SQLite устроены проще, чем в PostgreSQL, и именно поэтому коварнее. Транзакция, "
    "начатая на чтение и затем пытающаяся писать, может получить отказ посреди работы, если параллельно "
    "кто-то уже пишет. Пишущий код открывает транзакцию сразу с немедленной блокировкой — тогда "
    "конкуренция решается на входе, а не в середине.",

    "Документация к библиотеке читается в обратном порядке: сначала пример, потом сигнатура, потом "
    "описание. Поэтому каждая страница справочника начинается с минимального рабочего фрагмента, "
    "который можно скопировать и запустить, и только ниже объясняет параметры и исключения. "
    "Пример, который не запускается, хуже отсутствия примера.",

    "Протокол созвона пишется в тот же день, пока договорённости не обросли интерпретациями. В нём "
    "только решения и сроки, без пересказа обсуждения: кто что делает и к какому числу. Протокол "
    "отправляется всем участникам, и молчание в течение суток считается согласием — это оговорено "
    "заранее.",

    "Отчёт для клиента собирается из журнала задачи, а не из памяти. Каждый этап — что сделано, чем "
    "подтверждено, какие числа получены на их стенде. Клиент не читает код, но читает цифры: сколько "
    "заказов прошло, сколько повторов понадобилось, сколько времени занял самый медленный обмен.",

    "Секрет в логе — инцидент, даже если лог никто не читал. Ключ партнёра ротируется в тот же день, "
    "без выяснения, видел ли его кто-нибудь, а в логгер добавляется фильтр, вырезающий значения "
    "заголовков авторизации. Отдельный тест пишет в лог запрос с ключом и проверяет, что ключа в "
    "выводе нет.",

    "Ширина колонок в миграции записывается числом на дату миграции, а не ссылкой на константу. "
    "Константа может измениться, а миграция должна воспроизводить схему ровно такой, какой она была. "
    "Согласованность моделей со схемой проверяет отдельный тест, сравнивающий метаданные с "
    "результатом прогона всей цепочки.",

    "Дерево заметок ограничено четырьмя уровнями, считая сам кодекс. Глубже дерево перестаёт читаться "
    "из оглавления, а желание добавить пятый уровень почти всегда означает, что кодекс пора делить на "
    "два. Перенос ветки проверяет высоту целиком: нельзя обойти ограничение, переместив глубокое "
    "поддерево под заметку второго уровня.",

    "Счёт в черновике не уходит клиенту, но уже резервирует номер. Это решение бухгалтерии: номера "
    "идут подряд без пропусков, и удалённый черновик оставляет дыру, которую потом придётся объяснять "
    "налоговой. Поэтому черновик нельзя удалить, только аннулировать, и аннулированный счёт остаётся "
    "в списке с пометкой.",

    "Сборка фронтенда начинается с проверки типов, и ошибка типа валит сборку целиком. Это дороже на "
    "минуту при каждом запуске, но дешевле на час при каждой ошибке, которая иначе доехала бы до "
    "пользователя. Собранный результат лежит в репозитории, и обновление установки — это просто "
    "git pull без node на сервере.",

    "Перед каждым обновлением установка копирует базу целиком, и только потом применяет миграции. "
    "Копия лежит рядом с базой под именем с датой и номером ревизии, и при неудачной миграции откат — "
    "это переименование файла. На PostgreSQL то же самое делает дамп, но с оговоркой о размере и "
    "времени.",

    "Процессы установки находятся по собственному реестру, а не по имени. Команда, убивающая всё, в "
    "чьей командной строке есть app.py, убьёт заодно и агента, и соседнюю установку, и MCP-мост. "
    "Реестр хранит идентификатор, аргументы и рабочую папку каждого запущенного процесса, и остановка "
    "трогает только свои записи.",

    "Хорошая формулировка критерия готовности проверяется командой или наблюдением. «Тесты зелёные» — "
    "критерий, «работает хорошо» — пожелание. Если критерий нельзя проверить без автора задачи, он "
    "переписывается до начала работы, иначе в конце выяснится, что исполнитель и автор понимали готовность "
    "по-разному.",

    "Длинные поля в интерфейсе ломаются по-разному: заголовок переносится и сдвигает иконки, описание "
    "обрезается многоточием посреди слова, а тело заметки в сто тысяч символов заставляет редактор "
    "думать по секунде на каждое нажатие. Демонстрационные данные с длинными текстами нужны именно "
    "для того, чтобы увидеть всё это до пользователя.",

    "Поле «ход работы» переписывается, а не дополняется: в нём текущее состояние и следующий шаг, а не "
    "история. История остаётся в журнале и в коммитах. Если ход работы разросся до нескольких экранов, "
    "это сигнал, что задача слишком велика и её пора делить на подзадачи с собственными брифами.",
]

HEADINGS = [
    "Контекст", "Что уже известно", "Ограничения", "Как воспроизвести", "Причина", "Решение",
    "Альтернативы, которые отвергли", "Риски", "Миграция данных", "Обратная совместимость",
    "Наблюдаемость", "Производительность", "Безопасность", "Тесты", "Откат", "Открытые вопросы",
    "Что дальше", "Числа", "Схема", "Порядок работ", "Договорённости", "Замечания ревьюера",
    "Пограничные случаи", "Что не входит", "Зависимости", "Сроки", "Итоги", "Глоссарий",
]

BULLETS = [
    "проверить поведение на пустом списке",
    "добавить индекс по внешнему ключу до включения двойной записи",
    "согласовать формат ответа с их тимлидом",
    "переписать фикстуру на фабрику",
    "убрать чтение старой колонки из ночного отчёта",
    "замерить время ответа на сотне запросов, взять медиану и 95-й перцентиль",
    "проверить откат миграции на копии боевой базы",
    "вынести текст ошибки в переводы",
    "закрыть старую ветку после слияния",
    "описать пограничный случай в журнале как находку",
    "добавить тест на повторную доставку того же заказа",
    "проверить тёмную тему на всех страницах со списками",
    "обновить скриншоты в документации",
    "спросить бухгалтерию про нумерацию аннулированных счетов",
    "проверить поиск по кириллице на SQLite",
    "снять двойную запись после недели без расхождений",
    "убедиться, что ключ партнёра не попадает в лог",
    "прогнать полный набор тестов на 3.13",
    "проверить перенос длинного заголовка в карточке",
    "добавить пустое состояние с подсказкой",
    "проверить горячие клавиши в русской раскладке",
    "зафиксировать версию зависимости до выхода исправления",
    "развести права агента по подключениям кодекса",
    "проверить восстановление ветки заметок из корзины",
]

QUOTES = [
    "Переноса не будет: приёмка 30-го, и это записано в договоре.",
    "Не трогайте выгрузку до конца месяца, бухгалтерия сверяет по старому коду.",
    "Если тест нельзя написать, значит, непонятно, что именно мы исправляем.",
    "Это не наша зона, но их команде стоит об этом знать.",
    "Сначала форма API, потом реализация — иначе ревью превращается в переписывание.",
    "Восемь секунд на запрос — это их стенд, на боевом обещают полсекунды.",
    "Правило без причины держится на авторитете, правило с причиной держится само.",
    "Мы не пишем в их боевую среду с наших машин. Никогда.",
]

CODE_SAMPLES = [
    ("python", '''async def order_ack(order_id: str) -> AckResult:
    """Confirm an order on their side; a repeat is a success, not an error."""
    response = await client.post(f"/v2/orders/{order_id}/ack", timeout=10)
    if response.status_code == 409:
        return AckResult.ALREADY
    response.raise_for_status()
    return AckResult.DONE'''),
    ("python", '''def next_attempt(attempts: int, *, base: float = 2.0, cap: float = 600.0) -> float:
    delay = min(cap, base * 2 ** attempts)
    return delay + random.uniform(0, delay / 4)'''),
    ("sql", '''CREATE UNIQUE INDEX ux_exchange_order_external
    ON exchange_order (external_id)
    WHERE deleted_at IS NULL;'''),
    ("sql", '''SELECT p.code, p.amount_minor, count(i.code) AS invoices
FROM pricing_plan_v2 AS p
LEFT JOIN invoice AS i ON i.plan_code = p.code
WHERE p.archived_at IS NULL
GROUP BY p.code, p.amount_minor
ORDER BY invoices DESC;'''),
    ("typescript", '''export function sectionsOf(tasks: TaskRow[], groups: GroupRow[]): Section[] {
  const byGroup = Map.groupBy(tasks, (task) => task.group_code ?? NO_GROUP)
  return [...groups.map((group) => ({ group, tasks: byGroup.get(group.code) ?? [] })),
          { group: null, tasks: byGroup.get(NO_GROUP) ?? [] }]
}'''),
    ("bash", '''# copy the database before the chain runs
cp runtime/prod/app.sqlite3 "runtime/prod/app.$(date +%F).sqlite3"
uv run python src/app.py migrate upgrade'''),
    ("json", '''{
  "order_id": "A-20261002-0042",
  "status": "confirmed",
  "items": [{"sku": "PRO-12M", "qty": 1, "amount_minor": 1599000}],
  "confirmed_at": "2026-10-02T11:42:07Z"
}'''),
    ("yaml", '''jobs:
  test:
    strategy:
      matrix:
        python: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - run: uv run pytest --all'''),
    ("vue", '''<template>
  <VCard variant="outlined" rounded="lg" class="filter-panel mb-3">
    <TaskFilters v-model="filters" />
  </VCard>
</template>'''),
    ("python", '''@pytest.mark.db
async def test_redelivery_creates_no_duplicate(make_order):
    first = await exchange.accept(payload)
    second = await exchange.accept(payload)
    assert second.code == first.code
    assert await exchange.count() == 1'''),
]

TABLE_SUBJECTS = [
    ("Эндпоинт", "Медиана, мс", "p95, мс", "Ошибок"),
    ("Модуль", "Строк", "Тестов", "Покрытие"),
    ("Тариф", "Цена", "Период", "Активных"),
    ("Этап", "Начат", "Закрыт", "Подтверждение"),
]

ENDPOINT_NAMES = [
    "orders", "orders/{id}", "orders/{id}/ack", "orders/{id}/reject", "invoices", "invoices/{id}",
    "plans", "plans/{id}", "customers", "customers/{id}", "payments", "payments/{id}/refund",
    "webhooks", "reports/monthly", "exports/accounting", "health", "users", "users/{id}/roles",
    "sessions", "audit", "settings", "files", "files/{id}/download", "search",
]

PEOPLE = ["Анна", "Борис", "Вера", "Глеб", "Дарья", "Егор", "Жанна", "Илья", "Ксения", "Лев"]


# ── the composer ──────────────────────────────────────────────────────────────


def fit_to(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` on the last paragraph boundary that fits, else on a sentence."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    for boundary in ("\n\n", "\n", ". "):
        at = head.rfind(boundary)
        if at > limit // 2:
            return head[: at + (1 if boundary == ". " else 0)].rstrip()
    return head[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:—") + "…"


def near(limit: int) -> int:
    return int(limit * NEAR)


class Writer:
    """Composes long markdown from the library; one instance per run, seeded once."""

    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)

    def paragraph(self) -> str:
        return self.rng.choice(PARAGRAPHS)

    def paragraphs(self, n: int) -> str:
        return "\n\n".join(self.rng.sample(PARAGRAPHS, n))

    def bullets(self, n: int, *, checks: bool = False) -> str:
        items = self.rng.sample(BULLETS, n)
        if checks:
            return "\n".join(f"- [{'x' if self.rng.random() < 0.5 else ' '}] {item}" for item in items)
        return "\n".join(f"- {item}" for item in items)

    def numbered(self, n: int) -> str:
        return "\n".join(f"{i}. {item[0].upper()}{item[1:]}" for i, item in enumerate(self.rng.sample(BULLETS, n), 1))

    def quote(self) -> str:
        return f"> {self.rng.choice(QUOTES)}"

    def code(self) -> str:
        lang, body = self.rng.choice(CODE_SAMPLES)
        return f"```{lang}\n{body}\n```"

    def table(self, rows: int) -> str:
        head = self.rng.choice(TABLE_SUBJECTS)
        lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
        for _ in range(rows):
            first = self.rng.choice(ENDPOINT_NAMES)
            nums = [str(self.rng.randint(1, 4000)) for _ in head[1:]]
            lines.append(f"| `{first}` | " + " | ".join(nums) + " |")
        return "\n".join(lines)

    def block(self) -> str:
        roll = self.rng.random()
        if roll < 0.45:
            return self.paragraph()
        if roll < 0.60:
            return self.bullets(self.rng.randint(3, 7), checks=self.rng.random() < 0.3)
        if roll < 0.72:
            return self.code()
        if roll < 0.82:
            return self.table(self.rng.randint(4, 12))
        if roll < 0.90:
            return self.quote()
        return self.numbered(self.rng.randint(3, 6))

    def article(self, target: int, limit: int, *, title: str | None = None, level: int = 2) -> str:
        """Sections of mixed blocks until ``target`` characters, cut to ``limit``."""
        parts = [f"# {title}", self.paragraph()] if title else [self.paragraph()]
        size = sum(len(p) for p in parts)
        hashes = "#" * level
        while size < target:
            section = [f"{hashes} {self.rng.choice(HEADINGS)}"]
            section += [self.block() for _ in range(self.rng.randint(2, 5))]
            if self.rng.random() < 0.4:
                section.append(f"{hashes}# {self.rng.choice(HEADINGS)}")
                section += [self.block() for _ in range(self.rng.randint(1, 3))]
            text = "\n\n".join(section)
            parts.append(text)
            size += len(text) + 2
        return fit_to("\n\n".join(parts), limit)

    def api_reference(self, limit: int) -> str:
        endpoints = list(ENDPOINT_NAMES)
        parts = [
            "# Справочник API обмена",
            self.paragraph(),
            "| Метод | Путь | Что делает |",
            "| --- | --- | --- |",
        ]
        rows = [f"| `{self.rng.choice(['GET', 'POST', 'PUT', 'DELETE'])}` | `/v2/{e}` | "
                f"{self.rng.choice(BULLETS)} |" for e in endpoints]
        parts[-1] += "\n" + "\n".join(rows)
        for name in endpoints * 3:
            method = self.rng.choice(["GET", "POST", "PUT", "DELETE"])
            parts += [
                f"## {method} /v2/{name}",
                self.paragraph(),
                "### Параметры",
                "| Имя | Тип | Обязателен | Описание |\n| --- | --- | --- | --- |\n"
                + "\n".join(f"| `{p}` | `{t}` | {o} | {self.rng.choice(BULLETS)} |" for p, t, o in [
                    ("id", "string", "да"), ("since", "datetime", "нет"), ("limit", "int", "нет"),
                    ("cursor", "string", "нет")][: self.rng.randint(1, 4)]),
                "### Ответ",
                f"```json\n{CODE_SAMPLES[6][1]}\n```",
                "### Ошибки",
                self.bullets(self.rng.randint(2, 4)),
            ]
            if sum(len(p) for p in parts) > limit:
                break
        return fit_to("\n\n".join(parts), limit)

    def changelog(self, limit: int, versions: int = 60) -> str:
        parts = ["# Список изменений", self.paragraph()]
        major, minor, patch = 2, 0, 0
        for i in range(versions):
            parts.append(f"## {major}.{minor}.{patch} — 2026-{(10 - i // 6) or 1:02d}-{28 - (i * 3) % 27:02d}")
            for kind in self.rng.sample(["Добавлено", "Изменено", "Исправлено", "Удалено", "Безопасность"], self.rng.randint(1, 3)):
                parts.append(f"### {kind}\n\n" + self.bullets(self.rng.randint(2, 6)))
            if self.rng.random() < 0.3:
                parts.append(self.paragraph())
            patch -= 1
            if patch < 0:
                minor, patch = (minor - 1, 9) if minor > 0 else (9, 9)
                if minor == 9:
                    major -= 1
            if major < 0:
                break
        return fit_to("\n\n".join(parts), limit)

    def meetings(self, limit: int, count: int = 40) -> str:
        parts = ["# Протоколы созвонов"]
        for i in range(count):
            people = ", ".join(self.rng.sample(PEOPLE, self.rng.randint(2, 5)))
            parts += [
                f"## {28 - i % 28:02d}.{9 - i // 28:02d} — синхронизация №{count - i}",
                f"**Участники:** {people}.",
                self.paragraph(),
                "**Решили:**\n\n" + self.numbered(self.rng.randint(2, 5)),
                "**Сделать до следующего созвона:**\n\n" + self.bullets(self.rng.randint(2, 5), checks=True),
            ]
            if self.rng.random() < 0.3:
                parts.append(self.quote())
        return fit_to("\n\n".join(parts), limit)

    def progress_log(self, limit: int) -> str:
        """Whole days only — a cut inside a day would leave a date with nothing under it."""
        days: list[str] = []
        day = 1
        while True:
            lines = [f"**{day:02d}.10**", ""]
            for _ in range(self.rng.randint(2, 6)):
                done = self.rng.choice(BULLETS)
                then = self.rng.choice(BULLETS)
                line = f"- {done[0].upper()}{done[1:]} → дальше: {then}."
                if self.rng.random() < 0.25:
                    line += " " + self.rng.choice(PARAGRAPHS)[:260].rsplit(" ", 1)[0] + "…"
                lines.append(line)
            block = "\n".join(lines)
            if days and len("\n\n".join(days)) + len(block) + 2 > limit:
                return "\n\n".join(days)
            days.append(block)
            day = day % 28 + 1

    def short(self, limit: int) -> str:
        """A paragraph-like line for a description field."""
        text = self.paragraph()
        while len(text) < limit:
            text += " " + self.paragraph()
        return fit_to(text, limit)


# ── the specs ─────────────────────────────────────────────────────────────────

MARK = "demo data"

LONG_TITLES = [
    "Перевести расчёт тарифов, счетов и возвратов на новую схему с копейками вместо NUMERIC и двойной записью на переходный период",
    "Обмен заказами с партнёром через их API версии 2.3: очередь, повторы с экспоненциальной задержкой, идемпотентность и отчёт",
    "Пройти все страницы со списками в тёмной теме, поправить токены границ, фона карточек и контраста подписей до 1.5:1 и выше",
    "Релиз 2.0 библиотеки: убрать 3.9 из матрицы, обновить синтаксис, вычистить устаревшее с 1.4 и написать раздел перехода",
    "Справочник API для внешних интеграторов с примерами на каждый эндпоинт, таблицами параметров и разделом об ошибках",
    "Разобрать поиск по кириллице на SQLite и PostgreSQL, выровнять поведение и закрепить случаи тестами на обоих провайдерах",
    "Перенести хранение секретов из .env в системное хранилище ключей с ротацией и тестом, что ключ не попадает ни в один лог",
    "Документация установки и обновления: пошаговый runbook с кодами выхода, откатом из копии базы и разбором типичных сбоев",
]


def _stages(w: Writer, n: int) -> list[dict]:
    statuses = [STATUS_DONE] * (n // 2) + [STATUS_IN_PROGRESS] + [STATUS_PLANNED] * (n - n // 2 - 1)
    stages = []
    for i, status in enumerate(statuses, 1):
        stage = {
            "title": fit_to(f"Этап {i}. {w.rng.choice(BULLETS)[0].upper()}{w.rng.choice(BULLETS)[1:]}", TITLE_MAX),
            "description": w.short(near(DESCRIPTION_MAX)),
            "status": status,
            "body": w.article(near(STAGE_BODY_MAX), STAGE_BODY_MAX),
        }
        if status == STATUS_DONE:
            stage["evidence"] = w.short(near(EVIDENCE_MAX))
        stages.append(stage)
    return stages


def _journal(w: Writer, n: int) -> list[dict]:
    kinds = [JOURNAL_DECISION, JOURNAL_FACT, JOURNAL_FINDING, JOURNAL_REMARK]
    entries = []
    for i in range(n):
        kind = kinds[i % len(kinds)]
        entry = {
            "type": kind,
            "title": fit_to(f"{w.rng.choice(BULLETS)[0].upper()}{w.rng.choice(BULLETS)[1:]} — {w.rng.choice(QUOTES)}", TITLE_MAX),
            "body": w.article(near(JOURNAL_BODY_MAX), JOURNAL_BODY_MAX),
        }
        # Every other one resolved: the journal shows both open and closed entries in volume.
        if kind == JOURNAL_FACT or i % 2 == 0:
            entry["resolution"] = w.short(near(RESOLUTION_MAX))
        entries.append(entry)
    return entries


def _long_notes(w: Writer) -> list[dict]:
    return [
        {"title": "Справочник API обмена — полная версия со всеми эндпоинтами",
         "description": w.short(near(DESCRIPTION_MAX)), "body": w.api_reference(near(NOTE_BODY_MAX))},
        {"title": "Протоколы всех созвонов с начала проекта",
         "description": w.short(near(DESCRIPTION_MAX)), "body": w.meetings(near(NOTE_BODY_MAX) // 2)},
        {"title": "Разбор архитектуры: очередь, повторы, наблюдаемость",
         "description": w.short(near(DESCRIPTION_MAX)), "body": w.article(30000, NOTE_BODY_MAX, title="Архитектура обмена")},
        {"title": "Список изменений с первой версии",
         "description": w.short(near(DESCRIPTION_MAX)), "body": w.changelog(near(NOTE_BODY_MAX) // 3)},
    ]


def long_reads_tasks(w: Writer) -> list[dict]:
    """Every content field near its cap, sixteen journal entries, ten long stages, notes up to 63 000."""
    priorities = [PRIORITY_BURNING, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_LOW,
                  PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_FROZEN]
    statuses = [STATUS_IN_PROGRESS, STATUS_IN_PROGRESS, STATUS_IN_REVIEW, STATUS_IN_TEST, STATUS_PLANNED,
                STATUS_DONE, STATUS_BACKLOG, STATUS_PLANNED]
    groups = ["Архитектура", "Архитектура", "Интерфейс", "Релизы", "Документация", "Данные", "Безопасность", "Документация"]
    tasks = []
    for i, title in enumerate(LONG_TITLES):
        task = {
            "title": title,
            "description": w.short(near(DESCRIPTION_MAX)),
            "group": groups[i],
            "type": TYPE_EXTENDED,
            "status": statuses[i],
            "priority": priorities[i],
            "deadline_days": w.rng.choice([None, -5, -1, 2, 7, 30]),
            "context": w.article(near(CONTEXT_MAX), CONTEXT_MAX),
            "constraints": "- разрешено: " + "\n- разрешено: ".join(w.rng.sample(BULLETS, 4))
                           + "\n- спросить: " + "\n- спросить: ".join(w.rng.sample(BULLETS, 4))
                           + "\n- никогда: " + "\n- никогда: ".join(w.rng.sample(BULLETS, 3))
                           + "\n\n" + w.paragraphs(2),
            "criteria": w.numbered(8) + "\n\n" + w.paragraphs(2),
            "plan": w.article(near(PLAN_MAX), PLAN_MAX),
            "progress": w.progress_log(near(PROGRESS_MAX)),
            "stages": _stages(w, 10 if i < 4 else 4),
            "journal": _journal(w, 16 if i < 3 else 6),
            "notes": _long_notes(w) if i < 2 else [
                {"title": "Заметка к задаче — длинный разбор",
                 "description": w.short(near(DESCRIPTION_MAX)),
                 "body": w.article(20000 + i * 4000, NOTE_BODY_MAX)},
            ],
        }
        task["constraints"] = fit_to(task["constraints"], CONSTRAINTS_MAX)
        task["criteria"] = fit_to(task["criteria"], CRITERIA_MAX)
        if task["status"] == STATUS_DONE:
            task["result"] = w.article(near(RESULT_MAX), RESULT_MAX)
        tasks.append(task)
    # A standard task at its caps too: its page lays out the brief without stages.
    tasks.append({
        "title": "Стандартная задача с полями на пределе: план прозой, без этапов, с длинным журналом и итогом",
        "description": w.short(near(DESCRIPTION_MAX)),
        "group": "Данные",
        "type": TYPE_STANDARD,
        "status": STATUS_IN_REVIEW,
        "priority": PRIORITY_NORMAL,
        "context": w.article(near(CONTEXT_MAX), CONTEXT_MAX),
        "constraints": fit_to(w.bullets(10) + "\n\n" + w.paragraphs(3), CONSTRAINTS_MAX),
        "criteria": fit_to(w.numbered(10) + "\n\n" + w.paragraphs(3), CRITERIA_MAX),
        "plan": w.article(near(PLAN_MAX), PLAN_MAX),
        "progress": w.progress_log(near(PROGRESS_MAX)),
        "result": w.article(near(RESULT_MAX), RESULT_MAX),
        "journal": _journal(w, 10),
    })
    # A simple task has only its context — at the cap.
    tasks.append({
        "title": "Простая задача: только контекст, зато на весь лимит поля",
        "description": w.short(near(DESCRIPTION_MAX)),
        "group": None,
        "type": TYPE_SIMPLE,
        "status": STATUS_BACKLOG,
        "priority": PRIORITY_LOW,
        "context": w.article(near(CONTEXT_MAX), CONTEXT_MAX),
    })
    return tasks


VOLUME_GROUPS = [
    ("Бэкенд", "sky", "server"), ("Фронтенд", "violet", "palette"), ("Данные", "teal", "database"),
    ("Инфраструктура", "slate", "cloud-computing"), ("Безопасность", "red", "shield-lock"),
    ("Документация", "green", "books"), ("Поддержка", "orange", "messages"), ("Исследования", "yellow", "flask"),
]

VERBS = ["Перевести", "Ускорить", "Разобрать", "Починить", "Описать", "Проверить", "Убрать", "Добавить",
         "Переписать", "Замерить", "Согласовать", "Вынести", "Закрепить тестом", "Упростить"]
OBJECTS = ["выгрузку в бухгалтерию", "список задач", "поиск по заметкам", "очередь обмена", "форму счёта",
           "миграцию тарифов", "ночной отчёт", "страницу настроек", "импорт из CSV", "дерево кодекса",
           "меню строки", "пустые состояния", "журнал изменений", "проверку прав", "обновление установки",
           "ротацию ключей", "сборку фронтенда", "матрицу CI", "кэш справочников", "ленту изменений"]
TAILS = ["", "", " на PostgreSQL", " в тёмной теме", " для мобильной вёрстки", " без простоя",
         " по замечаниям ревью", " до релиза 2.0", " на копии боевой базы", " в русской раскладке"]


def volume_tasks(w: Writer) -> list[dict]:
    """A hundred-odd tasks across eight groups: a list long enough to scroll, filter and paginate."""
    statuses = [STATUS_BACKLOG, STATUS_PLANNED, STATUS_IN_PROGRESS, STATUS_IN_TEST, STATUS_IN_REVIEW,
                STATUS_DONE, STATUS_DONE, STATUS_CANCELED]
    priorities = [PRIORITY_BURNING, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_FROZEN]
    types = [TYPE_SIMPLE, TYPE_SIMPLE, TYPE_STANDARD, TYPE_STANDARD, TYPE_EXTENDED]
    open_statuses = {STATUS_BACKLOG, STATUS_PLANNED, STATUS_IN_PROGRESS}
    tasks = []
    for i in range(110):
        kind = w.rng.choice(types)
        status = w.rng.choice(statuses)
        task = {
            "title": f"{w.rng.choice(VERBS)} {w.rng.choice(OBJECTS)}{w.rng.choice(TAILS)}",
            "description": w.short(w.rng.randint(60, near(DESCRIPTION_MAX))),
            "group": w.rng.choice(VOLUME_GROUPS + [(None, "", "")])[0],
            "type": kind,
            "status": status,
            "priority": w.rng.choice(priorities),
            "deadline_days": w.rng.choice([None, None, None, -10, -3, -1, 0, 1, 3, 7, 14, 45]),
            "context": w.article(w.rng.randint(300, near(CONTEXT_MAX)), CONTEXT_MAX),
        }
        if kind != TYPE_SIMPLE:
            task["criteria"] = fit_to(w.numbered(w.rng.randint(2, 6)), CRITERIA_MAX)
            task["plan"] = w.article(w.rng.randint(500, 5000), PLAN_MAX)
            if status not in (STATUS_BACKLOG, STATUS_PLANNED):
                task["progress"] = w.progress_log(w.rng.randint(400, 6000))
            task["journal"] = _journal(w, w.rng.randint(0, 5))
            if w.rng.random() < 0.3:
                task["notes"] = [{"title": f"Заметка {n}: {w.rng.choice(HEADINGS).lower()}",
                                  "description": w.short(w.rng.randint(40, 300)),
                                  "body": w.article(w.rng.randint(1500, 12000), NOTE_BODY_MAX)}
                                 for n in range(1, w.rng.randint(2, 4))]
        if kind == TYPE_EXTENDED:
            task["stages"] = [dict(s, body=fit_to(s["body"], w.rng.randint(400, 3000)))
                              for s in _stages(w, w.rng.randint(2, 6))]
        if status == STATUS_DONE and kind != TYPE_SIMPLE:
            task["result"] = w.article(w.rng.randint(200, near(RESULT_MAX)), RESULT_MAX)
        if status in open_statuses and i % 9 == 0:
            task["children"] = [{
                "title": f"{w.rng.choice(VERBS)} {w.rng.choice(OBJECTS)}",
                "description": w.short(120),
                "type": TYPE_SIMPLE,
                "status": w.rng.choice([STATUS_BACKLOG, STATUS_PLANNED, STATUS_DONE]),
                "priority": PRIORITY_NORMAL,
                "context": w.paragraph(),
            } for _ in range(w.rng.randint(2, 5))]
        # The trash in volume — never a task with subtasks, whose delete would be a different case.
        if i % 23 == 11 and "children" not in task:
            task["deleted"] = True
        tasks.append(task)
    return tasks


HANDBOOK_SECTIONS = [
    ("arch", "Архитектура", ["modules", "levels", "lifecycle", "mcp", "feed"]),
    ("data", "Данные и миграции", ["types", "soft-delete", "indexes", "alembic", "backup"]),
    ("api", "HTTP API", ["zones", "errors", "pagination", "versioning"]),
    ("ui", "Интерфейс", ["layout", "lists", "dialogs", "hotkeys", "empty-states", "dark-theme"]),
    ("ops", "Эксплуатация", ["install", "update", "processes", "logs"]),
    ("quality", "Качество", ["tests", "review", "benches"]),
    ("glossary", "Глоссарий", []),
    ("changelog", "История правил", []),
]


def handbook_codex(w: Writer) -> dict:
    """A codex sized like a real handbook: a long root, wide levels, leaves up to the body cap."""
    notes = []
    for segment, title, children in HANDBOOK_SECTIONS:
        if segment == "changelog":
            body = w.changelog(near(CODEX_BODY_MAX))
        elif segment == "glossary":
            body = "# Глоссарий\n\n" + "\n\n".join(
                f"**{h}** — {w.paragraph()}" for h in sorted(set(HEADINGS)))
            body = fit_to(body, CODEX_BODY_MAX)
        else:
            body = w.article(w.rng.randint(6000, 20000), CODEX_BODY_MAX)
        note = {
            "segment": segment,
            "title": title,
            "description": w.short(w.rng.randint(120, near(CODEX_DESCRIPTION_MAX))),
            "body": body,
            "children": [],
        }
        for child in children:
            # The fourth level — the depth limit, codex / section / topic / page.
            grandchildren = [
                {
                    "segment": f"{child}-{n}",
                    "title": f"{w.rng.choice(HEADINGS)}: {w.rng.choice(BULLETS)}"[:120],
                    "description": w.short(w.rng.randint(80, 400)),
                    "body": w.article(w.rng.randint(3000, 25000), CODEX_BODY_MAX),
                }
                for n in range(1, w.rng.randint(2, 5))
            ]
            note["children"].append({
                "segment": child,
                "title": f"{child.replace('-', ' ').capitalize()} — {w.rng.choice(HEADINGS).lower()}",
                "description": w.short(w.rng.randint(100, near(CODEX_DESCRIPTION_MAX))),
                "body": w.article(w.rng.randint(4000, 40000), CODEX_BODY_MAX),
                "children": grandchildren,
            })
        notes.append(note)
    # One leaf at the very cap of a codex note body.
    notes[0]["children"][0]["children"][0]["body"] = w.article(near(CODEX_BODY_MAX), CODEX_BODY_MAX)
    return {
        "segment": "handbook",
        "title": "Справочник разработчика — всё, что накопилось за три года работы над проектом и соседними",
        "description": w.short(near(CODEX_DESCRIPTION_MAX)),
        "color": "yellow",
        "icon": "books",
        "body": w.article(near(CODEX_BODY_MAX) // 2, CODEX_BODY_MAX),
        "notes": notes,
    }


def workspaces(w: Writer) -> list[tuple[dict, list[dict]]]:
    """The two bulk workspaces, each with its tasks — the ``(spec, tasks)`` pairs ``seed_demo`` seeds."""
    long_reads = {
        "title": fit_to("Demo: длинные тексты — каждое поле у предела, заметки до 60 000 символов", WORKSPACE_TITLE_MAX),
        "description": fit_to(f"Поля у лимитов, длинные журналы и этапы ({MARK}). " + w.paragraph(), WORKSPACE_DESCRIPTION_MAX),
        "color": "yellow",
        "icon": "article",
        "groups": [
            {"title": "Архитектура", "description": "Схемы, очереди, слои", "color": "sky", "icon": "sitemap"},
            {"title": "Интерфейс", "description": "Темы, списки, формы", "color": "violet", "icon": "palette"},
            {"title": "Релизы", "description": "Версии и переходы", "color": "green", "icon": "rocket"},
            {"title": "Данные", "description": "Поиск, типы, провайдеры", "color": "teal", "icon": "database"},
            {"title": "Безопасность", "description": "Секреты и ключи", "color": "red", "icon": "shield-lock"},
            {"title": fit_to("Документация с очень длинным названием группы, чтобы увидеть, как оно переносится в заголовке секции списка задач", TITLE_MAX),
             "description": fit_to("Группа с длинным названием и описанием на весь лимит поля описания группы задач в списке", 128),
             "color": "orange", "icon": "books"},
        ],
        "codexes": [{"segment": "handbook", "agent_can_edit": True}, {"segment": "python", "agent_can_edit": True},
                    {"segment": "writing", "agent_can_edit": False}],
    }
    volume = {
        "title": "Demo: объём — сотня задач",
        "description": f"Много строк: прокрутка, фильтры, пагинация ({MARK})",
        "color": "teal",
        "icon": "layers-linked",
        "groups": [{"title": t, "description": f"Группа «{t}»", "color": c, "icon": i} for t, c, i in VOLUME_GROUPS],
        "codexes": [{"segment": s, "agent_can_edit": e} for s, e in
                    [("handbook", False), ("python", True), ("vue", True), ("sql", False), ("git", False),
                     ("writing", True), ("security", False), ("shell", True)]],
    }
    return [(long_reads, long_reads_tasks(w)), (volume, volume_tasks(w))]


__all__ = ["Writer", "handbook_codex", "workspaces"]
