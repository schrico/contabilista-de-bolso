# Contabilista de Bolso

Contabilista pessoal com IA para trabalhadores independentes em Portugal (recibos verdes): IRS, IVA e Segurança Social.

> **Aviso: isto não é aconselhamento fiscal.** O Contabilista de Bolso é um projeto pessoal e open-source, que pode conter erros ou estar desatualizado. Confirma sempre as respostas nas fontes oficiais (Portal das Finanças, Segurança Social) ou com um contabilista certificado antes de tomares qualquer decisão.

## O que faz (e o que não faz)

- Responde a dúvidas fiscais citando a lei, o ofício ou a FAQ oficial em vigor para o ano fiscal em causa.
- Pergunta o que falta saber antes de responder, em vez de adivinhar.
- As contas são feitas por código testado, nunca pelo modelo de linguagem.
- **Nunca submete nada em teu nome:** o sistema prepara e tu submetes.

## Estado

Em construção: Bloco 0 (fundações). Ainda não há nada para usar.

## Desenvolvimento

Requer [uv](https://docs.astral.sh/uv/) (o Python 3.13 é gerido pelo uv).

```sh
uv sync
uv run pytest
uv run ruff check .
```

## Licença

[Apache-2.0](LICENSE)
