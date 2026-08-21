# ResearchOps

Локальный, API-free слой для работы Codex с научными статьями. Он не пишет
статью вместо Codex и не вызывает отдельную LLM. Его задача — подготовить
небольшой проверяемый пакет доказательств, получить библиографические метаданные
и запустить существующий предsubmission-аудит.

## Зачем он нужен

- **Меньше токенов:** Codex читает не весь корпус, а ограниченный `EVIDENCE_PACK.md`.
- **Нет отдельной оплаты:** базовый режим не использует OpenAI API и не требует ключа.
- **Нет скрытых фоновых задач:** тяжёлые операции запускаются только явно, по одной,
  с лимитом размера и таймаутом.
- **Проверяемость:** извлечённый текст хранит SHA-256 исходника, а OpenAlex-запросы
  сохраняются как компактный JSON.

## Компоненты

| Компонент | Роль | По умолчанию |
|---|---|---|
| Python CLI | init, status, evidence pack, audit | включён, без зависимостей |
| Docling | PDF/DOCX/XLSX → Markdown | опционален, запускается явно |
| PyAlex | бесплатный поиск метаданных OpenAlex | опционален, запускается явно |
| PaperQA2 | LLM-RAG по корпусу | выключен: требует отдельного LLM-провайдера |
| Codex skill | выбирает только нужный режим | автоматический, но лёгкий |

PaperQA2 намеренно не включён в первую версию. Его основную полезную функцию для
нашего процесса — отбор небольшого набора релевантных фрагментов — выполняет
детерминированная команда `pack`, не расходующая API-токены.

## Быстрый запуск без установки

```bash
PYTHONPATH=ResearchOps/src python3 -m researchops init path/to/article
PYTHONPATH=ResearchOps/src python3 -m researchops extract path/to/article source.md
PYTHONPATH=ResearchOps/src python3 -m researchops pack path/to/article \
  --query "main mechanism and empirical evidence"
PYTHONPATH=ResearchOps/src python3 -m researchops audit path/to/article \
  path/to/article/manuscript.md
```

Проверка режима и расходов:

```bash
PYTHONPATH=ResearchOps/src python3 -m researchops status path/to/article
```

Поле `api_token_spend` должно быть `0`.

## Опциональные интеграции

Устанавливать только при реальной необходимости:

```bash
python3 -m pip install -e 'ResearchOps[documents]'
python3 -m pip install -e 'ResearchOps[discovery]'
```

После установки:

```bash
researchops extract path/to/article source.pdf
researchops discover path/to/article --query "AI state capacity" --limit 10
```

## Связь с текущей системой

Команда `audit` автоматически ищет соседний
`ACADEMIC_PUBLICATION_QA/manuscript_qc.py` и сохраняет Markdown/JSON-отчёты в
`<article>/.researchops/reports/`. Исходная рукопись не изменяется.

Codex-навык находится в `.agents/skills/researchops/`. Для общей рабочей папки
его копия устанавливается в `/Проекты/.agents/skills/researchops`, поэтому при
работе над статьями Codex видит маршрутизатор автоматически.

Подробнее: [архитектура](docs/architecture.md),
[контроль стоимости и нагрузки](docs/cost-control.md),
[интеграции](docs/integrations.md).
