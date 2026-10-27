# Tabela de datas (dim_calendario)

## O que é e por que existe

Uma tabela de dimensão só com datas, contígua (sem buracos), cobrindo todo o
período em que há dados: **01/10/2023 a 30/09/2026** (data de corte do
cenário, mais uma margem até o final do ano de 2026 para cobrir contratos
que vencem no futuro).

Ela existe porque os fatos têm **três colunas de data diferentes** espalhadas
em duas tabelas (`fato_contrato.data_contratacao`,
`fato_contrato.data_vencimento_final`, `fato_parcela.data_vencimento`) e, sem
uma tabela central, qualquer segmentação por "mês" ou "ano" teria que ser
feita coluna por coluna, sem padronização entre elas e sem suporte a funções
de inteligência de tempo (`DATEADD`, `SAMEPERIODLASTYEAR` etc., que exigem uma
tabela de datas marcada como tal no modelo).

## Como foi criada

DAX (New Table), para que o calendário fique vivo no modelo em vez de
depender de uma consulta externa:

```dax
dim_calendario =
ADDCOLUMNS (
    CALENDAR ( DATE(2023,10,1), DATE(2026,12,31) ),
    "Ano", YEAR ( [Date] ),
    "Mês", FORMAT ( [Date], "MMMM" ),
    "MêsAno", FORMAT ( [Date], "MM/YYYY" ),
    "NúmeroMês", MONTH ( [Date] ),
    "Trimestre", "T" & FORMAT ( [Date], "Q" )
)
```

Depois de criada:
1. Marcar a tabela como **Table Date** (clique direito na tabela →
   "Mark as Date Table" → selecionar a coluna `Date`). Sem isso, `DATEADD` e
   outras funções de inteligência de tempo não funcionam corretamente.
2. Ordenar a coluna `Mês` pela coluna `NúmeroMês` (Column Tool → Sort by
   Column), para os meses aparecerem em ordem cronológica nos visuais, não
   em ordem alfabética.

## As duas relações com fato_contrato (ativa e inativa)

`fato_contrato` tem duas datas relevantes: quando o contrato foi assinado
(`data_contratacao`) e quando ele termina de vencer (`data_vencimento_final`).
Um modelo só pode ter **uma relação ativa por vez entre duas tabelas** — a
segunda precisa ficar inativa e ser acionada manualmente via
`USERELATIONSHIP` dentro da medida que precisar dela.

- **Relação ativa:** `dim_calendario[Data] → fato_contrato[data_contratacao]`.
  É a relação "padrão" porque a maioria das análises do projeto é "o que foi
  concedido quando" (volume concedido, sazonalidade, ticket médio por mês).
- **Relação inativa:** `dim_calendario[Data] → fato_contrato[data_vencimento_final]`.
  Acionada pela medida `Volume a Vencer (por Vencimento Final)` (ver
  `dax/medidas_dax.txt`), que responde a uma pergunta diferente: "quanto da
  carteira atual vence em cada mês", útil para projeção de caixa futuro.

`fato_parcela[data_vencimento]` tem sua própria relação simples e ativa com
`dim_calendario` — não há ambiguidade aqui porque é a única data de
`fato_parcela` relacionada ao calendário (`data_pagamento` não é relacionada
à dimensão de datas; ela só é usada dentro da lógica de `Status Parcela`,
calculada no Power Query).
