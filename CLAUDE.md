# Contabilista de Bolso — instruções para o Claude Code

## O que é

Contabilista pessoal com IA para trabalhadores independentes em Portugal (recibos verdes): IRS, IVA e Segurança Social. Responde com fontes oficiais, pergunta o que falta antes de responder e nunca submete nada em nome de ninguém. É um projeto open-source de portefólio, com um só utilizador: o autor.

## Regras fixas

1. **O LLM nunca faz contas.** Valores, taxas, escalões e prazos vêm de código determinístico (a calculadora) e de regras versionadas por ano fiscal.
2. **Sem fonte não há afirmação fiscal.** Cada resposta cita a lei, o ofício ou a FAQ em vigor para o ano fiscal em causa. Sem fonte clara, para e pergunta; não inventes.
3. **O pipeline tem guardas em código:** um portão determinístico "falta dado crítico?" antes de responder; um verificador de um fornecedor diferente do redator, que nunca vê o raciocínio do redator e devolve JSON (`aprovado` | `corrigir` | `perguntar`), com no máximo 2 voltas.
4. **Dados pessoais nunca entram no repositório:** nem em código, testes, fixtures, exemplos, commits, logs ou issues. Usa só valores inventados. NIF, nomes e IBAN são mascarados antes de qualquer chamada a uma API externa (D5). Faturas nunca vão para planos gratuitos de APIs.
5. **Nada é submetido.** O sistema prepara e o utilizador submete. Nunca guardar passwords dos portais (Portal das Finanças, Segurança Social Direta).
6. **Segredos só no `.env` local (fora do git) e nos secrets da Azure.** Nunca pedir chaves na conversa, nunca as escrever em ficheiros versionados, nunca as imprimir em logs.
7. **Textos para o utilizador em PT-PT**, nunca PT-BR.

## Decisões

O plano completo, com o passo a passo de cada bloco, está em `docs/plano.md`. Lê-o no início de cada sessão.

Esse ficheiro é uma cópia do doc onde o plano é editado: não o alteres. Se algo no plano estiver errado ou desatualizado, diz ao utilizador. Está no `.gitignore`.

| # | Tema | Decisão |
|---|---|---|
| D1 | Base de dados | Postgres com pgvector na VPS (Hetzner), para registos e vetores |
| D2 | Open-source e dados | Um só repositório público; dados pessoais só na base de dados e em pastas no `.gitignore` |
| D3 | Licença | Apache-2.0 |
| D4 | Corpus no repositório | Só os scripts de ingestão e os links, nunca os documentos |
| D5 | Dados enviados a APIs | Mascarar NIF, nomes e IBAN e enviar só o necessário |
| D6 | Extração de faturas | Código QR (ATCUD) primeiro; o LLM só quando não houver QR |
| D7 | Frontend | Next.js com o Schrico DS |
| D8 | Autenticação | Só o autor, com a autenticação da Azure Container Apps; `user_id` em todas as tabelas |
| D9 | Observabilidade | Langfuse Cloud, região UE, plano gratuito, traces mascarados; custo, modelo e latência também numa tabela própria no Postgres |
| D10 | IVA | Só a isenção do art. 53.º e a saída dela, por enquanto |
| D11 | Deduções pessoais | Fora da v1 |
| D12 | Alertas | Email ou Telegram via n8n |
| D13 | Chaos monkey | Pontos de injeção desde o Bloco 0 e cenários em cada bloco |
| D14 | Modelos | Comerciais e abertos lado a lado desde o Bloco 1, trocáveis por configuração |
| D15 | Nome | Contabilista de Bolso |
| D16 | Ligação Azure → base de dados | Rede privada com Tailscale: o Postgres só escuta no IP do Tailscale da VPS (nunca em `0.0.0.0`), `pg_hba.conf` só aceita `100.64.0.0/10` com `scram-sha-256`; na Azure o `tailscaled` corre em modo userspace com um reencaminhador local (`socat` + `tailscale nc`) para `localhost:5432`; ACL: só `tag:app` fala com `tag:db` na porta 5432 |

## Stack

- Python 3.13 com uv; FastAPI; LangGraph; LiteLLM como biblioteca dentro da app (não como servidor)
- Postgres com pgvector; migrações com Alembic
- Tailscale entre a Azure e a VPS (D16)
- pytest e ruff; pre-commit com gitleaks e um verificador próprio de NIF e IBAN (o mesmo verificador corre no CI)
- Docker; GitHub Actions → GitHub Container Registry → Azure Container Apps (plano Consumption, OIDC sem passwords)
- Langfuse Cloud (UE)
- Modelos: Google AI Studio, OpenRouter, OpenAI, Anthropic e Ollama local, todos através do LiteLLM
- Frontend (Bloco 2): Next.js com o Schrico DS

## Estrutura

```
api/      FastAPI: rotas e autenticação
graph/    grafo LangGraph e cliente de LLM
ingest/   scripts de ingestão do corpus
corpus/   só links e metadados (D4)
evals/    perguntas de avaliação e métricas
chaos/    wrappers de falhas injetadas, desligados por defeito
db/       migrações Alembic
infra/    Docker, VPS e Azure
web/      frontend Next.js (Bloco 2)
ferramentas/  ferramentas do repositório (verificador de NIF e IBAN do pre-commit e do CI)
tests/    testes pytest
dados/    privado: no .gitignore, nunca versionado
docs/     plano.md: cópia do plano (no .gitignore)
```

## Comandos

```sh
uv sync                                   # instala o Python 3.13 e as dependências
uv run pytest                             # testes
uv run ruff check . && uv run ruff format --check .
uv run pre-commit install                 # uma vez por clone: gitleaks + verificador de NIF/IBAN
uv run pre-commit run --all-files
uv run python -m ferramentas.verificar_dados_pessoais --todos   # o mesmo verificador que corre no CI
```

O CI (`.github/workflows/verificacoes.yml`) corre ruff, pytest, o verificador com `--todos` e o gitleaks sobre o histórico todo. Uma linha que tenha mesmo de levar um NIF ou IBAN público (por exemplo o de uma entidade) leva o marcador `dados-pessoais: permitido`. Por fazer: `docker compose up -d db` (Fase 4).

## Como trabalhar

- Um passo do plano por sessão. Antes de escrever código, apresenta um plano curto e espera aprovação.
- Commits pequenos, um por passo, num branch com pull request para a `main`.
- Regras fiscais e o verificador de NIF/IBAN levam testes antes do código.
- Comandos na VPS ou na Azure: prepara-os e explica-os; o utilizador corre os que pedem `sudo`, login ou permissões.
- Nada fica público (push, repositório, imagem) sem o utilizador aprovar.
- No fim de cada passo: o que mudou, como testar e o que falta.

## Estado atual

O estado de cada passo está nas caixas `[x]` / `[ ]` de `docs/plano.md`. Se a data no topo desse ficheiro for antiga, ou o estado não bater certo com o que está no repositório, pede ao utilizador para sincronizar o plano antes de continuar.
