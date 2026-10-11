<p align="center">
  <img src="https://www.python.org/static/img/python-logo-large.c36dccadd999.png?1576869008" alt="Python Logo" width="120" />
</p>

<h1 align="center">QuantFlow</h1>

<p align="center">
  Plataforma de negociação financeira para explorar análise algorítmica,<br />
  automação de mercados e estratégias quantitativas.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker" />
</p>

---

## Sobre o projeto

**QuantFlow** é um ecossistema digital concebido para combinar estratégias quantitativas, inteligência artificial e simulação de dados de mercado. O objetivo é testar e ilustrar operações de trading automatizado num ambiente controlado, com foco em boas práticas de engenharia de software.

O backend segue **Clean Architecture** e **Domain-Driven Design (DDD)**, organizado por módulos de domínio, para evoluir de forma modular à medida que novas capacidades (contas, estratégias, dados de mercado, execução) forem introduzidas.

### Estado atual

| Módulo    | Descrição |
| --------- | --------- |
| `account` | Utilizadores, autenticação (JWT em cookie + refresh) e credenciais de exchange (API key e secret cifrados com Fernet) |
| `trader`  | Bots, worker de execução, estratégia RSI, gestão de risco, trades e backtesting |
| `wallet`  | Sincronização de saldos e snapshots diários (só leitura na exchange) |
| `shared`  | Entidades base, value objects, infraestrutura de BD, API, criptografia e logging |
| `ml`      | Dados históricos, características, rótulos, treino, artefactos JSON, inferência, avaliação walk-forward e shadow |

> **IA/ML: implementada, avaliada e NÃO validada.** Na avaliação walk-forward (18 meses fora da amostra — 6 trimestres × BTC/ETH, 1h) nenhum modelo mostrou vantagem estável depois de custos; corre apenas em **modo shadow** (regista previsões, não decide). A estratégia RSI perdeu em 10 de 12 janelas. Ver *IA/ML*.

---

## Stack tecnológica

| Camada        | Tecnologia                          |
| ------------- | ----------------------------------- |
| API           | FastAPI, Uvicorn                    |
| Dados         | PostgreSQL, SQLAlchemy (async)      |
| Análise       | pandas, NumPy                       |
| Segurança     | bcrypt, PyJWT, passlib              |
| Configuração  | pydantic-settings, python-dotenv    |
| Containers    | Docker, Docker Compose              |

---

## Arquitetura

O código vive em `src/` e separa responsabilidades por camadas (DDD / Clean Architecture):

```
src/
├── account/   domain · application · infra (api, db)
├── trader/
│   ├── domain/        Bot, Trade (máquina de estados), estratégias, interfaces de gateway
│   ├── application/   bot_cycle (decisão e execução), risk_guard, backtest_engine, use cases
│   └── infra/         gateway (Bybit, paper, fábrica), worker, api, db
├── wallet/
├── ml/
│   ├── data/          OHLCV: download público, normalização, relatório de qualidade
│   ├── features/      pipeline v1 (mesma função no treino e na inferência)
│   ├── labels.py      objetivo: retorno líquido de comprar em t+1 e vender em t+12
│   ├── models/        artefactos JSON + inferência numpy, aprovação humana
│   ├── training/      dataset, candidatos, seleção, treino do artefacto
│   ├── inference/     MLSignalStrategy, ShadowRecordingStrategy
│   └── evaluation/    walk-forward e avaliação do shadow
└── shared/
```

### Fluxo do worker

A cada 10 s o worker carrega os bots ativos **e** os bots inativos que ainda têm um trade ativo, e executa um `BotCycle` por bot:

1. **Reconcilia** trades pendentes (`PENDING_OPEN` / `PENDING_CLOSE`) pela `client_order_id` na exchange.
2. Com posição aberta: verifica o saldo real (testnet/live), avalia stop-loss / take-profit e o sinal `SELL`.
3. Sem posição (e só se o bot estiver ativo): decide sobre a **última vela fechada**, aplica o `RiskGuard`, arredonda ao lote da exchange e verifica mínimos e saldo.
4. Toda a ordem é **registada e commitada antes de ser enviada**. Se o resultado for desconhecido, o trade fica pendente e é reconciliado — nunca é reenviado às cegas. Um índice único garante no máximo um trade ativo por bot.

### Observabilidade e operação

- **Logs JSON** (`LOG_FORMAT=json`) com `cycle_id`, `bot_id`, `trade_id`, `client_order_id`; campos com nomes sensíveis são apagados.
- **Heartbeat** em `worker_status` (um registo por processo): ciclos, erros, falhas consecutivas, maior intervalo entre ciclos, última atualização de mercado, contagem de resultados, última auditoria.
- `GET /health` (público, mínimo) e `GET /ops/worker-status` (autenticado; apenas estado e contagens operacionais — sem `last_error`, detalhes de auditoria nem contagens de resultados, que revelariam atividade de outros utilizadores; esses detalhes ficam nos logs e no `soak_report`). Healthcheck de contentor: `python -m trader.infra.worker.healthcheck`.
- **Alertas** (logger `quantflow.alerts`, webhook opcional `ALERT_WEBHOOK_URL`, deduplicação 15 min): falhas consecutivas, dados de mercado parados, `POSITION_MISMATCH`/`INCONSISTENT`/`EXIT_REJECTED`/`EXIT_BELOW_MINIMUM`, `RECONCILE_FAILED`, problemas de auditoria.
- **Auditoria contabilística** a cada 5 min: invariantes dos trades, pendentes presos, e em paper a correspondência exata entre execuções simuladas e trades gravados.
- Encerramento gracioso (SIGTERM/SIGINT), `pool_pre_ping` para sobreviver a reinícios da base de dados.
- Teste prolongado: ver [docs/PAPER_SOAK_TEST.md](docs/PAPER_SOAK_TEST.md).
- **Esquema**: só as migrações Alembic criam/alteram tabelas (o arranque da API não cria nada). `alembic upgrade` usa um lock consultivo do PostgreSQL, por isso backend e worker podem migrar ao mesmo tempo sem conflito.
- Os contentores usam `exec`: o processo da aplicação é o PID 1 e recebe o SIGTERM (paragem graciosa).
- **Bybit Testnet**: stack isolada e procedimento em [docs/TESTNET.md](docs/TESTNET.md).

### Modos de trading (`TRADING_MODE`)

| Modo | Comportamento |
| ---- | ------------- |
| `paper` (defeito) | Dados de mercado reais (endpoints públicos da Bybit), execução **simulada** ao ask/bid com slippage e comissão. Gateway sem chaves: não é possível enviar ordens. |
| `testnet` | Ordens na testnet da Bybit; recusa credenciais de mainnet. Preços e liquidez da testnet não são os do mercado real. |
| `live` | Ordens reais. Exige também `LIVE_TRADING_ENABLED=true` e uma credencial de mainnet. |

Em `testnet`/`live`, a API key é verificada antes de ser usada: chaves com permissões `Wallet` (levantamentos ou transferências), só de leitura ou sem `SpotTrade` são recusadas.

### Controlo de risco

Aplicado antes de cada **entrada** (as saídas nunca são bloqueadas):

| Controlo | Variável |
| -------- | -------- |
| Paragem global de entradas | `TRADING_HALTED` |
| Paragem por utilizador | `POST /bots/halt` |
| Perda diária máxima por bot (% do capital) | `MAX_DAILY_LOSS_PCT` |
| Drawdown máximo do PnL realizado | `MAX_DRAWDOWN_PCT` |
| Exposição máxima por utilizador (USDT) | `MAX_USER_EXPOSURE_USDT` |
| Stop-loss máximo por bot | `MAX_STOP_LOSS_PCT` |

### Backtesting

`POST /backtests` simula a mesma lógica do worker: decisão na vela fechada, execução no open seguinte com slippage e comissão de taker, stop-loss/take-profit intrabar (se ambos forem tocados na mesma vela conta o stop), indicadores aquecidos com a mesma janela do live. Devolve retorno, drawdown, win rate, profit factor, expectativa por trade, buy & hold com os mesmos custos, exposição, comissões e a lista de trades.

Um backtest positivo **não** prova rentabilidade: avalie vários períodos e regimes de mercado e compare com o buy & hold.

---

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha os valores. Principais variáveis:

| Variável | Descrição |
| -------- | --------- |
| `POSTGRES_PASSWORD` | Password do Postgres usada pelo docker-compose (obrigatória). Um volume existente mantém a password com que foi criado. |
| `DATABASE_URL` | URL PostgreSQL (`postgresql://` ou `postgresql+asyncpg://`). |
| `ENCRYPTION_KEY` | Chave Fernet para API keys e secrets das credenciais (a migração `c3d4e5f6a7b8` cifra as chaves existentes e precisa da mesma chave). |
| `JWT_SECRET_KEY` | Chave de assinatura dos JWT. |
| `COOKIE_SECURE` | `true` por defeito; `false` apenas em desenvolvimento local por http. |
| `TRADING_MODE` / `LIVE_TRADING_ENABLED` | Ver *Modos de trading*. |
| `PAPER_TAKER_FEE_RATE` / `PAPER_SLIPPAGE_BPS` | Custos usados no paper trading e no backtest. |
| Limites de risco | Ver *Controlo de risco*. |
| `SQL_ECHO` | Log das instruções SQL (os parâmetros nunca são registados). |
| `LOG_FORMAT` / `LOG_LEVEL` | `json` (defeito do worker) ou `text`. |
| `ALERT_WEBHOOK_URL` / `ALERT_COOLDOWN_SECONDS` | Webhook opcional de alertas e janela de deduplicação. |
| `WORKER_STALE_SECONDS` / `AUDIT_EVERY_CYCLES` | Heartbeat considerado parado; frequência da auditoria. |
| `ML_MODEL_PATH` | Artefacto JSON carregado uma vez no arranque do worker. |
| `ML_SHADOW_ENABLED` | Regista a opinião do modelo ao lado de cada decisão real (sem influência). |
| `ML_TRADING_ENABLED` | Permite que bots `ML_SIGNAL` usem um artefacto **aprovado** em paper/testnet. Nunca em live. |

Gerar uma chave `ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

O ficheiro `.env` está no `.gitignore` e **não deve ser commitado**.

---

## Pré-requisitos

- [Python 3.12+](https://www.python.org/downloads/)
- [Docker](https://www.docker.com/) e Docker Compose (recomendado)
- Git

---

## Como executar

### Opção 1 — Docker (recomendado)

Na raiz do repositório:

```bash
docker compose up -d --build
```

| Serviço  | URL / porta                          |
| -------- | ------------------------------------ |
| API      | http://localhost:8002                |
| Docs     | http://localhost:8002/docs           |
| Postgres | `localhost:6000` (user: `quantflow_admin`, db: `quantflow_db`) |

Verificar o estado:

```bash
curl http://localhost:8002/
```

Resposta esperada:

```json
{"status": "QuantFlow backend running successfully in Docker"}
```

Parar os serviços:

```bash
docker compose down
```

### Opção 2 — Ambiente local (sem Docker)

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (CMD)
.venv\Scripts\activate

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Copie `.env.example` para `.env` e ajuste `DATABASE_URL` se necessário. Depois execute:

```bash
# Na raiz do projeto (PYTHONPATH inclui src/)
set PYTHONPATH=src          # Windows CMD
# export PYTHONPATH=src     # Linux / macOS

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

A documentação interativa fica em http://localhost:8000/docs.

---

## Migrações

As migrações Alembic correm automaticamente ao arrancar os contentores (`alembic upgrade head`). Manualmente:

```bash
alembic upgrade head
```

Notas: `d3e9f0a1b204` falha (de forma atómica) se algum bot tiver mais de um trade `OPEN`; `c3d4e5f6a7b8` cifra as API keys existentes com `ENCRYPTION_KEY`. Todas as migrações foram testadas contra PostgreSQL real (base limpa, atualização, reversão).

---

## IA/ML

### Objetivo de previsão

Para cada vela fechada *t*: probabilidade de um long comprado no **open de t+1** e vendido no **fecho de t+12** (1h) ter **retorno líquido > 0** depois de comissão (0,1 %/lado) e slippage (5 bps/lado). Rótulos com janela futura incompleta ou com lacunas são descartados. Divisões temporais com **purga de 12 velas**.

### Pipeline

```bash
pip install -r requirements-ml.txt                       # treino/avaliação apenas
python -m ml.data.download --symbol BTC/USDT --symbol ETH/USDT --days 1095
python -m ml.evaluation.walk_forward --symbol BTC/USDT --symbol ETH/USDT \
    --out artifacts/reports/walk_forward                 # relatório JSON + Markdown
python -m ml.training.train --symbol BTC/USDT --symbol ETH/USDT \
    --walk-forward-report artifacts/reports/walk_forward/report.json
python -m ml.evaluation.shadow_report --since 2026-10-10T00:00:00Z
```

- **Características v1** (só velas ≤ t): retornos 1–72, RSI de Wilder (janela igual ao live), volatilidade e regime (vol12/vol168), amplitude, ATR, volume, desvios de médias. Lacunas invalidam a linha.
- **Candidatos**: regressão logística, Random Forest, Gradient Boosting. Seleção pelo *log loss* de validação, que tem de bater a taxa base; limiar escolhido na validação (retorno líquido médio > 0, ≥ 30 sinais). Sem vantagem → **sem modelo** (não opera).
- **Artefactos**: JSON com SHA-256, schema de características, proveniência (hash dos dados, períodos, métricas). O worker **nunca** carrega pickle/joblib; a inferência é numpy e reproduz o scikit-learn (testado). O runtime não precisa do scikit-learn.
- **Aprovação**: um artefacto só conduz decisões se tiver `approval.approved_for_trading` registado por uma pessoa (`python -m ml.models.approve`) **e** `ML_TRADING_ENABLED=true` **e** o modo não for live. Artefactos marcados `validation_failed` nunca podem ser aprovados.

### Fluxo em execução

Dados de mercado → características → previsão → decisão da estratégia → `RiskGuard`, saldo, mínimos, kill switch → execução paper → reconciliação → registo em `ai_predictions` (versão, timestamp das características, probabilidade, decisão, sinal usado, motivo de rejeição). Características atrasadas, em falta ou incompatíveis, ou modelo indisponível → **HOLD** (nunca abre posição). As saídas por stop-loss/take-profit continuam a funcionar com o ML desligado.

### Resultados (2026-10-10, fora da amostra: 6 trimestres × 2 ativos = 12 janelas, não independentes)

| Estratégia | Retorno médio/janela | Janelas positivas | Pior DD | Profit factor | Trades |
|---|---|---|---|---|---|
| ML | −0,84 % | 3/12 | −22,4 % | 0,94 | 138 |
| RSI | −15,31 % | 2/12 | −45,8 % | 0,65 | 398 |
| Buy & hold | −3,33 % | 3/12 | — | — | — |
| Sem operações | 0,00 % | — | 0 % | — | 0 |

AUC de teste 0,50–0,59; *log loss* de teste pior ou igual à taxa base em 4 de 5 janelas com modelo. **Conclusão: sem evidência de vantagem; o modelo atual é apenas de investigação (shadow).** RSI: perde também sem custos (−6,0 %/janela) e fica abaixo de entradas aleatórias com as mesmas saídas (−7,4 %); 68 % das saídas são stops e 57 % das entradas repetem-se ≤ 2 h após um stop (o worker não tem período de espera). Relatório completo em `artifacts/reports/walk_forward/` (gerado localmente, não versionado).

## Testes

```bash
pip install -r requirements-dev.txt
pytest                      # unitários + API (sem rede, sem base de dados)

# Integração com PostgreSQL real e descartável (tmpfs, porta 55432)
docker compose -f docker-compose.test.yml up -d --wait
QUANTFLOW_INTEGRATION_DB=postgresql://quantflow_test:quantflow_test@127.0.0.1:55432/postgres pytest
docker compose -f docker-compose.test.yml down

ruff check src tests main.py migrations
pip-audit -r requirements.txt
```

Cada teste de integração usa uma base nova (clonada de um template migrado). A suíte **recusa correr** contra um servidor que tenha `quantflow_db` ou esteja na porta 6000.

| Pasta | O que valida |
| ----- | ------------ |
| `tests/unit/trader/` | Ciclo de decisão e execução (idempotência, reconciliação, saídas parciais, mínimos), gateway Bybit com o parser real do ccxt, modo paper, risco, backtest, RSI |
| `tests/unit/account/` | Casos de uso de utilizador e autorização |
| `tests/api/` | Rotas HTTP: autorização, exposição de credenciais, refresh de sessão |
| `tests/unit/ml/` | Ausência de look-ahead nas características e rótulos, equivalência artefacto JSON ↔ scikit-learn, validação de artefactos, estratégia ML, seleção, avaliação shadow |
| `tests/integration/` | Migrações (limpa, atualização, falha atómica, reversão, cifra de chaves), restrições, corridas concorrentes reais, escrita antes do envio, reconciliação após reinício, worker (falhas, BD caída, paragem), estado/health, auditoria e alertas, ML shadow/ativo, API com BD real, scripts operacionais |

Os testes não usam rede, base de dados nem credenciais reais.

---

## Aviso legal

Este projeto tem fins **educacionais e experimentais**. Não constitui aconselhamento financeiro nem garante resultados em mercados reais. Utilize por sua conta e risco.

---

## Licença

Consulte o ficheiro de licença do repositório (se aplicável).
