# Dicionário de dados

Todas as tabelas abaixo existem no banco `database/cooperativa_horizonte_sul.db`
(e no `.sql` equivalente). Dados 100% sintéticos, gerados por
`scripts/gerar_dados.py`.

## dim_cooperado

| Coluna | Tipo (SQLite) | Descrição | Observação |
|---|---|---|---|
| cooperado_id | INTEGER | Identificador do cooperado | **Sem PRIMARY KEY/UNIQUE de propósito** — há 25 ids duplicados na tabela (ver catálogo de inconsistências) |
| nome | TEXT | Nome completo | Caixa alta/baixa e espaços extras inconsistentes |
| documento | TEXT | CPF (pessoa física) ou CNPJ (pessoa jurídica) | Fictício, formatos diferentes (com/sem pontuação) |
| data_nascimento | TEXT | Data de nascimento | Formatos mistos: `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY` |
| telefone | TEXT | Telefone de contato | Formatos mistos; ~5% nulo |
| email | TEXT | E-mail | ~10% nulo |
| sexo | TEXT | M/F | Caixa mista; nulo em alguns registros |
| cidade | TEXT | Cidade do cooperado | Caixa alta/baixa e espaços extras inconsistentes |
| uf | TEXT | Estado (sempre SC no cenário) | — |
| data_associacao | TEXT | Data de entrada na cooperativa | Mesmos formatos mistos de data_nascimento |

Linhas: 2.025 (2.000 cooperados únicos + 25 duplicados).

## dim_pa

| Coluna | Tipo | Descrição |
|---|---|---|
| pa_id | INTEGER (PK) | Identificador do posto de atendimento |
| nome_pa | TEXT | Nome do PA |
| cidade | TEXT | Cidade do PA |
| uf | TEXT | Estado do PA |

Linhas: 8. PA Centro e PA Industrial concentram carteira e atraso (padrão plantado).

## dim_produto

| Coluna | Tipo | Descrição | Observação |
|---|---|---|---|
| produto_id | INTEGER (PK) | Identificador do produto de crédito | — |
| nome_produto | TEXT | Nome do produto | — |
| categoria | TEXT | Categoria do produto | Caixa alta/baixa e espaços extras inconsistentes (ex.: "CONSIGNADO", "agro ", " Consignado") |

Linhas: 7. "Crédito Pessoal" é o produto com inadimplência bem acima dos demais (padrão plantado).

## fato_contrato

| Coluna | Tipo | Descrição | Observação |
|---|---|---|---|
| contrato_id | INTEGER (PK) | Identificador do contrato | — |
| cooperado_id | INTEGER (FK → dim_cooperado) | Cooperado titular | — |
| pa_id | INTEGER (FK → dim_pa) | PA onde o contrato foi originado | — |
| produto_id | INTEGER (FK → dim_produto) | Produto contratado | — |
| data_contratacao | TEXT (ISO) | Data de assinatura do contrato | — |
| data_vencimento_final | TEXT (ISO) | Data da última parcela prevista | Usada na relação inativa com dim_calendario |
| prazo_meses | INTEGER | Prazo do contrato em meses | 12, 18, 24, 36 ou 48 |
| taxa_juros_am | REAL | Taxa de juros ao mês (%) | ~2% dos registros nulo |
| valor_contratado | **TEXT** | Valor total contratado | Formato BR como texto, ex.: `"15.000,50"` — precisa de conversão no Power Query |
| valor_parcela | REAL | Valor de cada parcela do contrato | Numérico, já limpo |

Linhas: 3.000.

## fato_parcela

| Coluna | Tipo | Descrição | Observação |
|---|---|---|---|
| parcela_id | INTEGER (PK) | Identificador da parcela | — |
| contrato_id | INTEGER (FK → fato_contrato) | Contrato ao qual a parcela pertence | **50 parcelas órfãs** com contrato_id inexistente |
| numero_parcela | INTEGER | Número sequencial da parcela dentro do contrato | — |
| data_vencimento | TEXT (ISO) | Data de vencimento da parcela | — |
| valor_parcela | REAL | Valor da parcela | — |
| data_pagamento | TEXT (ISO) ou NULL | Data em que a parcela foi paga | NULL = ainda não paga; **15 registros** têm data_pagamento anterior a data_contratacao do contrato (erro de integridade proposital) |
| valor_pago | REAL ou NULL | Valor pago | NULL quando data_pagamento é NULL |

Linhas: 82.386.

## Relacionamentos (visão rápida — detalhe em `modelagem_relacionamentos.md`)

```
dim_cooperado (1) ──< (N) fato_contrato (N) >── (1) dim_pa
                              │
                              v (1)
                        dim_produto
                              │
                              v (1)
                        fato_parcela (N)

dim_calendario (1) ──< (N) fato_contrato   [via data_contratacao, ativa]
dim_calendario (1) ··< (N) fato_contrato   [via data_vencimento_final, inativa]
dim_calendario (1) ──< (N) fato_parcela    [via data_vencimento, ativa]
```
