# Bybit Testnet — procedimento

Objetivo: validar o percurso real das ordens (formato dos pedidos, `orderLinkId`, leitura da
execução, comissões, reconciliação) contra a API da **Bybit Testnet**, sem dinheiro real.
Não avalia rentabilidade: a liquidez e os preços da testnet não são representativos.

## Garantias implementadas (verificadas por testes, sem rede)

| Proteção | Onde |
|---|---|
| Modo `testnet` só aceita credenciais `is_testnet=True`; `live` recusa-as | `gateway_factory.create_trading_gateway` |
| Endpoint resolvido tem de ser **só** `api-testnet.bybit.com` (testnet) / `api.bybit.com` (live); verificado no gateway e outra vez na factory | `BybitGateway.__init__`, `_on_host` |
| Política de permissões por lista de autorização (ver abaixo); chave não só-leitura | `verify_api_key_permissions` |
| Conta **unificada (UTA)** obrigatória: numa conta clássica a quantidade de uma compra a mercado seria lida como USDT | idem (`uta == 1`) |
| `marketUnit=baseCoin` explícito em todas as ordens a mercado | `place_market_order` |
| Passo, mínimos (quantidade/valor) e **máximos** (quantidade a mercado/valor); entradas acima do máximo são reduzidas, saídas acima do máximo são divididas | `get_trading_rules`, `TradingRules.limit_quantity` |
| Escrita antes do envio, `clientOrderId` único, reconciliação (realtime + histórico), estado desconhecido nunca reenviado | `BotCycle` |
| `RiskGuard`, kill switch, `LIVE_TRADING_ENABLED=false` | worker |

## Política de permissões da API key (testnet e live)

Fonte: <https://bybit-exchange.github.io/docs/v5/user/apikey-info> e
<https://bybit-exchange.github.io/docs/v5/user/modify-master-apikey> (consultadas em 2026-10-10).

| Permissão | Decisão | Justificação |
|---|---|---|
| `Spot: SpotTrade` | **obrigatória** | única negociação usada pelo QuantFlow |
| `Derivatives: DerivativesTrade` | tolerada **só com `uta=1`** | documentada como "Permission of Unified account" e agrupada pela interface nas contas Unified. Não dá poderes ao bot: o cliente só carrega mercados spot (`fetchMarkets: spot`), e uma ordem para um símbolo de derivados é recusada antes de ser enviada (testado) |
| `Wallet` (`Withdraw`, `AccountTransfer`, `SubMemberTransfer`, `SubMemberTransferList`), `Fiat*`, `BitCard`, `Earn`, `Exchange` (convert), `Affiliate` | **recusadas** | movem fundos ou operam fora da negociação |
| `ContractTrade`, `Options`, `BlockTrade` | **recusadas** | outros produtos de negociação, não impostos pela conta Unified |
| `Stocks: StocksTrade` | **recusada** | não documentada pela Bybit (nem na página da chave, nem no changelog v5): não pode ser classificada com segurança |
| qualquer outro grupo/valor | **recusado** | desconhecido → recusa por defeito |

A mesma política aplica-se em testnet e live; não altera endpoints (testado).

**Instrumentos**: a Bybit lista ações tokenizadas como pares *spot* (`symbolType`
`xstocks`/`mstocks`; na testnet, em 2026-10-10: 31 `xstocks`, 3 `mstocks`, 40 `adventure`).
Por isso `SpotTrade` sozinho não impede negociar ações: o gateway só aceita pares spot com
`symbolType` vazio (cripto padrão) e recusa os restantes antes de qualquer pedido. A etiqueta da
testnet não é totalmente fiável (ex.: ZEC/USDT aparece como `xstocks`); a recusa por defeito
torna o erro seguro (bloqueia a mais, nunca a menos).

**Lista explícita de símbolos** (`TRADABLE_SYMBOLS`, por defeito `BTC/USDT,ETH/USDT`): só
estes símbolos podem ser dimensionados ou receber ordens, em todos os modos, e a recusa acontece
antes de qualquer pedido à exchange. É a proteção principal; o filtro `symbolType` é uma segunda
barreira. A reconciliação de ordens existentes nunca é bloqueada pela lista.

**`StocksTrade`** (devolvida como `Stocks: ["StocksTrade"]`, sem descrição na API nem na
documentação): continua **recusada**. Não é possível provar pela API que é apenas negociação.

## 1. Preparar (uma vez)

`.env.testnet` (ignorado pelo git) já contém os segredos próprios desta stack. Falta apenas
acrescentar as chaves criadas em <https://testnet.bybit.com> → *API Management*:
**System-generated**, permissões **Spot → Trade** apenas, **sem** *Wallet/Withdraw/Transfer*,
de preferência com restrição de IP. Nunca usar chaves de produção.

```bash
# editar .env.testnet e preencher BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET
alias qft='docker compose --env-file .env.testnet -f docker-compose.testnet.yml'
qft up -d --build --wait            # base própria (porta 55434) + worker TRADING_MODE=testnet
```

As chaves só chegam ao serviço `testnet_tools` (perfil `tools`), nunca ao worker: o worker lê a
credencial cifrada com a `TESTNET_ENCRYPTION_KEY` desta stack.

## 2. Validação só de leitura (sem escrever nada)

```bash
qft --profile tools run --rm testnet_tools \
    python -m trader.infra.ops.seed_testnet_bot --check --symbol BTC/USDT --symbol ETH/USDT
```

Esperado: `endpoint: api-testnet.bybit.com`, chave só com Spot Trade, conta unificada,
saldos e limites de cada instrumento. Qualquer falha → código ≠ 0 e nada é escrito.

## 3. Ordem de teste de valor mínimo

Só depois do passo 2 passar:

```bash
qft --profile tools run --rm testnet_tools \
    python -m trader.infra.ops.testnet_order_smoke --symbol BTC/USDT --confirm-testnet
```

Compra ≈ 1,2× o mínimo do instrumento, relê a execução por `clientOrderId`, vende a
quantidade efetivamente detida (líquida da comissão em BTC) e relê a venda. Não grava nada.

## 4. Percurso completo pelo worker

```bash
# guarda a credencial cifrada e cria bots INATIVOS
qft --profile tools run --rm testnet_tools \
    python -m trader.infra.ops.seed_testnet_bot --symbol BTC/USDT --capital 20
# ativar um bot (ou usar --activate no seed) e acompanhar
qft logs -f testnet_worker
```

Exercícios recomendados: `docker kill` ao worker com uma entrada pendente (reconciliação após
reinício), reinício da base, `qft stop testnet_worker` (deve registar `Received SIGTERM`).

## 5. Encerrar

`qft stop` (mantém dados) · `qft down` (remove contentores, mantém o volume). Revogar as chaves
na testnet quando deixarem de ser necessárias.

## Diagnóstico de falhas do `--check`

| Resposta | Causa provável | Ação |
|---|---|---|
| `retCode 10003` *API key is invalid* | A chave não existe na **testnet**: foi criada em bybit.com (produção) ou em *Demo Trading* (`api-demo.bybit.com`, outro ambiente) | Criar a chave em <https://testnet.bybit.com> com a conta da testnet; a stack só fala com `api-testnet.bybit.com` (produção está bloqueada por DNS) |
| `retCode 10004` *error sign* | Secret errado ou trocado com a key | Copiar de novo o par key/secret |
| `retCode 10010` *Unmatched IP* | Restrição de IP da chave | Acrescentar o IP público desta máquina ou remover a restrição |
| `clock skew` recusado | Relógio local > 3 s fora do servidor | Sincronizar a hora do Windows |
| `uta != 1` | Conta clássica | Atualizar a conta da testnet para Unified Trading Account |
| `outside the allow-list` | A chave tem permissões fora da política (ex.: `StocksTrade`, Contracts, Options) | Editar a chave e retirar essas permissões; `DerivativesTrade` pode ficar numa conta Unified |
| `can move funds or act outside trading` | Wallet/transferências/levantamentos, earn, convert, pagamentos | Retirar essas permissões |
| `balance USDT: 0.0` | Conta da testnet sem fundos, ou fundos na conta *Funding* | Em testnet.bybit.com → *Assets*: pedir moedas de teste e **transferir para a conta Unified Trading** (a chave do QuantFlow não tem, nem deve ter, permissão de transferência) |
