# Teste prolongado de paper trading (24–48 h)

Objetivo: demonstrar, com evidência recolhida, que o worker corre continuamente em
`TRADING_MODE=paper` sem ordens duplicadas, sem divergências contabilísticas e com
recuperação correta após reinícios. **Não** avalia rentabilidade.

## 1. Preparação (ambiente isolado)

A stack `docker-compose.paper.yml` usa uma base de dados própria (volume `paper_pg_data`,
porta `127.0.0.1:55433`) e um worker bloqueado em `TRADING_MODE=paper`. Não toca na base
de desenvolvimento.

```bash
# Segredos exclusivos desta stack, escritos diretamente no ficheiro (ignorado pelo git),
# nunca impressos. Só gerar uma vez: o volume guarda a password do primeiro arranque.
python -c "import secrets; from cryptography.fernet import Fernet; open('.env.paper','x').write(
f'PAPER_POSTGRES_PASSWORD={secrets.token_urlsafe(24)}\nPAPER_ENCRYPTION_KEY={Fernet.generate_key().decode()}\nPAPER_JWT_SECRET_KEY={secrets.token_urlsafe(48)}\n')"
# opcional: acrescentar ALERT_WEBHOOK_URL=https://... ao .env.paper

# --env-file: a stack nunca lê o .env de desenvolvimento (o nome de projeto quantflow_paper
# está fixado no ficheiro compose; as imagens não contêm .env, ver .dockerignore).
alias qfp='docker compose --env-file .env.paper -f docker-compose.paper.yml'
# --since tem de ser ANTERIOR ao arranque do primeiro worker: o relatório só conta
# processos com started_at >= --since (registado depois, perdia o primeiro processo).
date -u +%Y-%m-%dT%H:%M:%SZ   # guarde: é o --since do relatório
qfp up -d --build
qfp exec paper_worker python -m trader.infra.ops.seed_paper_bot --symbol BTC/USDT --symbol ETH/USDT
```

O seed recusa correr fora de `TRADING_MODE=paper`. A credencial criada é um marcador:
o modo paper nunca a decifra nem a usa.

Opcional (shadow): montar um artefacto em `/app/artifacts/models/...` e definir
`ML_MODEL_PATH`. O modelo apenas regista previsões; não altera decisões.

## 2. Durante o teste

| Quando | Ação | Verificação |
|---|---|---|
| Contínuo | `qfp logs -f paper_worker` (JSON) | sem `Traceback`, alertas `ALERT` investigados |
| ~6 h | **Exercício de falha do worker**: `docker kill quantflow_paper-paper_worker-1` (sem graceful) | o contentor reinicia (`restart: unless-stopped`); `soak_report` mostra 1 reinício com indisponibilidade < 300 s |
| ~12 h | **Exercício de base de dados**: `docker restart quantflow_paper-paper_db-1` | sem perda de estado; erros transitórios só durante o reinício |
| ~18 h | **Paragem graciosa**: `qfp stop paper_worker` e `qfp start paper_worker` | log `Received SIGTERM`, `BotWorker stopped.`; `stopped_at` preenchido |
| Qualquer momento | `qfp exec paper_worker python -m trader.infra.worker.healthcheck` (esta stack não tem backend/API) | `healthy: heartbeat age …`, código 0 |

### Exercícios sem supervisão

`scripts/paper_soak_drills.sh <since> <início> 24` executa os três exercícios às +6/+12/+18 h,
regista estado de hora a hora e gera o relatório às +24 h, em `artifacts/reports/soak/run_<início>/`
(`drills.log`, `status.log`, `soak_report.json`, `log_summary.txt`). Só atua sobre
`quantflow_paper-*`. Uma recuperação automática falhada fica registada como falha.

No Windows, a suspensão por inatividade pára o Docker e invalida `cycle_continuity`:
correr `scripts/keep_awake.ps1 -Hours 25` (não altera definições; fechar a tampa continua a
suspender) e manter o portátil ligado à corrente.

> **Execução iniciada a 2026-10-10T16:59:08Z**: o contentor foi criado antes da correção
> `exec` (o `sh -c` era o PID 1 e não reencaminhava o SIGTERM). Nesta execução, a paragem das
> ~18 h termina em SIGKILL após 30 s, sem `Received SIGTERM`/`stopped_at`; conta como reinício
> (≤ 300 s), mas não demonstra a paragem graciosa. A correção foi validada à parte (stack
> testnet: paragem em 1 s, código 0, `Received SIGTERM`, `BotWorker stopped.`, `stopped_at`).

## 3. Avaliação objetiva

```bash
qfp exec paper_worker \
    python -m trader.infra.ops.soak_report --since <início> --min-hours 24 --out /tmp/soak.json
qfp cp paper_worker:/tmp/soak.json artifacts/reports/soak/
```

PASS exige **todos** os critérios (código de saída 0):

| Critério | Limite |
|---|---|
| `duration` | ≥ 24 h de heartbeats (48 h recomendado) |
| `worker_alive_at_report` | último heartbeat ≤ 60 s, worker não parado |
| `cycle_continuity` | maior intervalo entre ciclos ≤ 120 s |
| `restart_recovery_time` | indisponibilidade entre processos ≤ 300 s |
| `restart_drill_performed` | ≥ 1 reinício observado |
| `cycle_error_rate` | ≤ 1 % de ciclos com erro |
| `no_ongoing_failures` | 0 falhas consecutivas no fim |
| `no_manual_review_outcomes` | 0 `POSITION_MISMATCH`, `INCONSISTENT`, `EXIT_REJECTED`, `EXIT_BELOW_MINIMUM` |
| `market_data_fresh` | última atualização de mercado ≤ 120 s |
| `periodic_ledger_audits_clean` | auditoria ≤ 15 min e 0 problemas em todos os processos |
| `ledger_audit_at_report` | auditoria final sem problemas |

Checklist manual (anexar ao relatório): exercício de reinício da base de dados executado,
nenhuma exceção não tratada parou o worker, todas as linhas `BotWorker started` indicam
`TRADING_MODE=paper`.

Se a estratégia não gerar sinais durante o período, o teste valida a fiabilidade mas **não**
o percurso das ordens; isso está coberto pelos testes de integração e deve ser registado.

## 4. Evidência já recolhida (validação do procedimento, não do teste de 24 h)

2026-10-10, ~19 min, base descartável, 2 bots (BTC/USDT, ETH/USDT), dados públicos reais:
queda forçada do worker com recuperação em 27 s, ligações à base de dados terminadas sem
erros, 0 erros em 96 ciclos, auditorias limpas. Com `--min-hours 0.25`: PASS; com os
limites de 24 h: FAIL em `duration` (como esperado). Nenhum trade (RSI sem sinal).
