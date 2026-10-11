# Plano experimental — Fase 6 (pré-registo)

Registado em 2026-10-10, **antes** de qualquer destas variantes ser implementada ou testada.
Hipóteses, parâmetros e critérios de rejeição ficam fixos neste documento; alterá-los depois
de ver resultados invalida o experimento (regista-se como novo experimento, com nova data).

O ML continua em modo shadow. Nenhum experimento envia ordens, em paper ou noutro modo.

## 0. Porquê um pré-registo

As variantes do RSI (secções 1–2) nasceram do diagnóstico de 2026-10-10 sobre
**BTC/USDT e ETH/USDT, 1h, 2025-02-01 → 2026-08-01** (6 trimestres de teste walk-forward).
Esse período, e todo o intervalo 2023-10-11 → 2026-10-10 usado no treino/validação do ML,
está **contaminado** para estas hipóteses: não pode servir de prova.

### Conjuntos de avaliação (por ordem de prioridade)

| Id | Dados | Estado |
|---|---|---|
| H1 — histórico não usado | BTC/USDT, ETH/USDT 1h **antes de 2023-10-11** (até onde a Bybit spot tiver dados; confirmar cobertura no download, sem olhar para resultados) | nunca usado |
| H2 — ativos não usados | SOL/USDT, XRP/USDT, BNB/USDT 1h, 2023-10-11 → 2026-10-10 | nunca usados; correlacionados com BTC/ETH (regimes comuns), por isso são evidência mais fraca que H1 |
| H3 — futuro | BTC/USDT, ETH/USDT 1h **a partir de 2026-10-11T00:00Z** (paper/shadow) | acumula ~2 200 velas por trimestre; avaliação final só após ≥ 2 trimestres |

Cada hipótese é avaliada **uma única vez** em H1 e H2. H3 confirma o que passar.

## Convenções comuns (fixas)

- Motor: `trader.application.backtest_engine.run_backtest` sem alterações às regras de execução
  (decisão no fecho, execução na abertura seguinte, stop ao pior preço, stop prioritário).
- Custos: comissão 0,10 %/lado + slippage 5 bps/lado. **Teste de stress**: 2× custos.
- Capital: 1 000 por ativo, 100 % alocado por trade, só long, spot.
- Janelas: trimestres civis; carteira 50/50 (ou 1/N) entre ativos **por trimestre**, composta
  entre trimestres (convenção corrigida em `walk_forward.aggregate`).
- Referências em todas as tabelas: **sem operações (0 %)**, buy & hold com os mesmos custos,
  RSI atual 14/30/70 SL 2 %/TP 4 %.
- Métricas: retorno por trimestre (média, mediana, composto), pior drawdown, profit factor,
  nº de trades, taxa de acerto, exposição, retorno/exposição, Sharpe anualizado, IC 95 %
  bootstrap da média trimestral, contribuição do melhor trimestre.

### Critérios de rejeição (comuns — basta falhar um)

1. Retorno médio por trimestre ≤ 0 depois de custos.
2. Limite inferior do IC 95 % bootstrap da média trimestral ≤ 0 (vs. sem operações).
3. Profit factor < 1,10.
4. Com 2× custos, retorno médio < 0.
5. Menos de 30 trades no conjunto (evidência insuficiente → "inconclusivo", não "aprovado").
6. O melhor trimestre explica > 50 % do PnL total.
7. Pior drawdown de trimestre pior que o do buy & hold no mesmo trimestre **e** retorno inferior.

Comparações múltiplas: são 4 hipóteses principais; o IC do critério 2 usa 1 − 0,05/4
(≈ 98,75 %) para controlar falsos positivos.

---

## 1. RSI com período de espera após stop

1. **Hipótese**: o prejuízo do RSI vem sobretudo de reentradas imediatas depois de um stop em
   tendência de queda (57 % das entradas, ~78 % da perda no diagnóstico). Bloquear novas entradas
   após um stop elimina essa perda sem remover as entradas com informação.
2. **Dados**: OHLCV 1h (H1, H2, H3).
3. **Regras**: RSI 14, compra ≤ 30, venda ≥ 70, SL 2 %, TP 4 % (inalterados). Após uma saída
   `STOP_LOSS`, nenhuma entrada durante **24 velas** (2× o horizonte de 12 velas do rótulo ML;
   fixado a priori, sem procura). O mesmo bloqueio tem de existir no worker para paper.
4. **Custos/execução**: comuns.
5. **Métricas**: comuns + nº de entradas bloqueadas e o PnL que essas entradas teriam tido
   (contrafactual, só descritivo).
6. **Rejeição**: comuns. Além disso: se a variante não melhorar o RSI base em ≥ 50 % dos
   trimestres, a hipótese do mecanismo é rejeitada mesmo que o retorno seja positivo.
7. **Validação**: H1 e H2, uma vez; depois H3.
8. **Risco de sobreajuste**: alto — a variante foi desenhada a ver o período de teste.
   Mitigação: parâmetro único fixado aqui, avaliado só em dados não vistos. Sensibilidade
   (12 e 48 velas) é **reportada**, nunca usada para escolher.

## 2. Filtro de tendência

1. **Hipótese**: compras em sobrevenda só têm valor esperado positivo quando a tendência de
   fundo é ascendente; em tendência descendente, a sobrevenda prolonga-se.
2. **Dados**: OHLCV 1h.
3. **Regras**: RSI base (secção 1 sem período de espera) **e** só entra se fecho > SMA de 200
   velas (parâmetro clássico, não otimizado). Variante 2b = filtro + período de espera
   da secção 1 (conta como hipótese separada no controlo de comparações múltiplas).
4. **Custos**: comuns.
5. **Métricas**: comuns + exposição por regime (acima/abaixo da SMA).
6. **Rejeição**: comuns.
7. **Validação**: H1, H2, depois H3.
8. **Risco**: médio-alto (escolha do comprimento da SMA). Mitigação: 200 fixo; 100/400 apenas
   reportados.

## 3. Momentum simples (seguimento de tendência)

1. **Hipótese**: BTC/ETH apresentam momentum temporal a horizontes de semanas; um sinal lento,
   com poucas transações, sobrevive aos custos melhor que a reversão de curto prazo.
2. **Dados**: OHLCV 1h, decisão apenas no fecho da vela das 00:00 UTC (uma decisão por dia).
3. **Regras**: comprado se o retorno de 30 dias (720 velas) > 0, sem posição caso contrário;
   saída por sinal no fecho diário. Stop de catástrofe a 10 %; sem take-profit (TP = 1 000 %
   no motor, i.e. inativo). Sem otimização da janela.
4. **Custos**: comuns; reportar também o turnover anual.
5. **Métricas**: comuns + comparação de Sharpe e drawdown com o buy & hold (o objetivo é reduzir
   drawdown, não necessariamente bater o retorno do buy & hold em mercados de alta).
6. **Rejeição**: comuns, exceto o critério 7, que é substituído por: Sharpe ≤ Sharpe do buy &
   hold no mesmo conjunto **e** drawdown não inferior ao do buy & hold.
7. **Validação**: H1 (inclui ciclos 2021–2023 com regimes distintos), H2, H3.
8. **Risco**: baixo-médio (uma regra, um parâmetro), mas poucos trades → critério 5 pode
   tornar o resultado inconclusivo; nesse caso, não se aprova.

## 4. LightGBM com calibração de probabilidades

1. **Hipótese**: um modelo de árvores com boosting, com probabilidades calibradas e um limiar de
   custo explícito, extrai das características v1 um sinal que a regressão logística/RF/GB do
   scikit-learn não extraíram (AUC de teste atual 0,50–0,59 ± 0,06).
2. **Dados**: características v1 e rótulo atual (horizonte 12, custos incluídos) — sem
   alterações, para isolar o efeito do modelo.
3. **Regras**: walk-forward 12/3/3 meses com purga de 12 velas. Hiperparâmetros fixos:
   `num_leaves=15, learning_rate=0.05, n_estimators≤500 com early stopping na validação,
   min_child_samples=200, feature_fraction=0.8, bagging_fraction=0.8, lambda_l2=1.0`.
   Calibração isotónica no **último mês do treino** (purgado), nunca na validação nem no teste.
   Entrada só se a probabilidade calibrada implicar retorno líquido esperado > 2× custo de
   ida e volta (filtro de custos); limiar escolhido na validação como hoje.
4. **Custos**: comuns.
5. **Métricas**: comuns + AUC, log loss e Brier vs. taxa base no teste; curva de calibração;
   número efetivo de observações (n/12).
6. **Rejeição**: comuns **e** log loss de teste < taxa base em ≥ 4 de 6 trimestres **e** AUC
   com IC que exclua 0,5 em ≥ 3 trimestres. Falhando, o modelo fica em investigação; nunca é
   aprovado para decisões.
7. **Validação**: H1 é inviável para treino completo se a cobertura anterior a 2023-10 for curta;
   então H2 (pooled) e H3 (shadow, ≥ 2 trimestres).
8. **Riscos**: alto (capacidade do modelo vs. ~700 observações efetivas por janela de treino).
   Segurança: artefacto exportado com `Booster.dump_model()` para JSON e inferência numpy própria,
   com teste de equivalência; **sem pickle/joblib**; `lightgbm` só em `requirements-ml.txt`
   e auditado com `pip-audit`.

## Fora de âmbito nesta fase

LSTM/GRU/Transformers e Reinforcement Learning: sem justificação enquanto nenhum modelo
supervisionado simples mostrar vantagem fora da amostra; o volume de dados efetivo (centenas de
observações independentes por janela) não suporta modelos de alta capacidade.

## Ordem de execução proposta

1. Download H1/H2 e relatório de qualidade (sem calcular resultados).
2. Implementar 1, 2, 2b e 3 como estratégias + testes unitários (sem olhar para H1/H2).
3. Correr H1 e H2 **uma vez**; publicar tabela completa, incluindo rejeições.
4. LightGBM (4) só depois, com a sua própria revisão de dependências.
5. Variantes não rejeitadas → shadow/paper (H3) durante ≥ 2 trimestres.
