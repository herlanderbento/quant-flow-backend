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

### Estado atual (MVP)

| Módulo   | Descrição                                      |
| -------- | ---------------------------------------------- |
| `account` | Gestão de utilizadores (domínio e casos de uso) |
| `shared`  | Entidades base, repositórios, infraestrutura DB |

A API expõe um endpoint de saúde; os casos de uso de utilizador estão implementados na camada de aplicação e prontos para serem ligados à camada HTTP.

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

O código vive em `src/` e separa responsabilidades por camadas:

```
src/
├── account/                 # Bounded context: contas de utilizador
│   ├── domain/              # Entidades, value objects, repositórios (interfaces)
│   └── application/         # Casos de uso (create, get, list, update, delete)
└── shared/                  # Kernel partilhado
    ├── domain/              # Entity, AggregateRoot, notificações, paginação
    ├── application/         # Contratos de use case, DTOs paginados
    └── infra/               # DB, criptografia, modelos ORM
```

**Padrões e princípios aplicados:**

- **DDD** — bounded contexts, agregados e value objects
- **Clean Architecture** — dependências apontam para o domínio
- **SOLID** — inversão de dependência nos repositórios e use cases
- **CQS** — comandos e queries separados nos casos de uso

## Variáveis de ambiente

Copie o ficheiro de exemplo e preencha os valores locais:

```bash
cp .env.example .env          # Linux / macOS
copy .env.example .env        # Windows CMD
```

| Variável         | Obrigatória | Descrição |
| ---------------- | ----------- | --------- |
| `DATABASE_URL`   | Não*        | URL PostgreSQL. O default aponta para `localhost:6000` (Docker). Aceita `postgresql://` ou `postgresql+asyncpg://`. |
| `ENCRYPTION_KEY` | Não*        | Chave Fernet para credenciais de exchanges. Gerar antes de usar em produção. |
| `ENV`            | Não         | `development` ou `production`. Usado pelo Docker Compose. |

\* Existem valores por defeito em desenvolvimento; em produção defina sempre valores próprios e seguros.

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

## Estrutura do repositório

```
quantflow/
├── main.py
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── Dockerfile
├── docker-compose.yml
├── tests/
│   ├── unit/            # Casos de uso e domínio (mocks)
│   ├── api/             # Endpoints FastAPI (httpx)
│   └── integration/     # Repositórios + Postgres (planeado)
└── src/
    ├── account/
    └── shared/
```

---

## Testes

O projeto segue a **pirâmide de testes**: muitos testes unitários rápidos, menos testes de integração e poucos end-to-end.

| Camada        | Pasta              | O que valida                          |
| ------------- | ------------------ | ------------------------------------- |
| Unitário      | `tests/unit/`      | Use cases e regras de domínio (mocks) |
| API           | `tests/api/`       | Rotas HTTP com `httpx` + ASGI         |
| Integração    | `tests/integration/` | Repositórios com Postgres real (a adicionar) |

### Instalar dependências de desenvolvimento

```bash
pip install -r requirements-dev.txt
```

### Executar a suíte

```bash
# Todos os testes
pytest

# Com relatório verboso
pytest -v

# Apenas unitários
pytest tests/unit/

# Apenas API
pytest tests/api/
```

### Exemplo incluído

- `tests/unit/account/test_create_user.py` — criação de utilizador com repositório e criptografia mockados
- `tests/api/test_health.py` — endpoint `GET /`

> **Nota:** Os testes de API que dependem do `lifespan` (sincronização com a base de dados) exigem Postgres acessível ou mocks adicionais. Expanda `tests/integration/` quando a camada de infraestrutura de `account` estiver implementada.

---

## Roadmap

Funcionalidades previstas para evolução da plataforma:

- [ ] Exposição HTTP dos casos de uso de `account`
- [ ] Autenticação e autorização (JWT / OAuth)
- [ ] Ingestão e simulação de dados de mercado
- [ ] Motor de estratégias quantitativas
- [ ] Backtesting e paper trading
- [ ] Integração com filas de mensagens e observabilidade
- [ ] CI/CD (GitHub Actions)
- [x] Estrutura inicial de testes (pytest)

---

## Aviso legal

Este projeto tem fins **educacionais e experimentais**. Não constitui aconselhamento financeiro nem garante resultados em mercados reais. Utilize por sua conta e risco.

---

## Licença

Consulte o ficheiro de licença do repositório (se aplicável).
