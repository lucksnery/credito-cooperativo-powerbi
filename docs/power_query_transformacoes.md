# Transformações no Power Query

Conexão: **Obter Dados → ODBC**, selecionando o DSN do SQLite (ver seção de
pré-requisitos no README), modo **Importar**. Cada tabela do banco entra como
uma consulta separada (`dim_cooperado`, `dim_pa`, `dim_produto`,
`fato_contrato`, `fato_parcela`).

Abaixo, os passos de cada consulta na ordem em que devem ser aplicados, com o
código M equivalente (Editor Avançado) para colar direto quando for mais
rápido que repetir clique por clique ao vivo.

---

## dim_cooperado

Passos (em "Transformar Dados"):
1. `Trim` em `nome` e `cidade` (remove espaços nas pontas).
2. `Capitalize Each Word` em `nome` e `cidade` (resolve caixa alta/baixa).
3. Coluna customizada `Documento Normalizado` = só dígitos do CPF/CNPJ (para dedup).
4. Coluna customizada `Data Nascimento` convertendo os 3 formatos de data em
   tipo Date.
5. `Remove Duplicates` em `cooperado_id` (mantém a primeira ocorrência) —
   **passo crítico**, sem ele a relação 1:N com `fato_contrato` não fecha.

Código M (customizar conforme nomes exatos de coluna no seu Power Query):

```m
let
    Origem = dim_cooperado,
    TrimNomeCidade = Table.TransformColumns(Origem, {
        {"nome", Text.Trim, type text},
        {"cidade", Text.Trim, type text}
    }),
    Capitalizado = Table.TransformColumns(TrimNomeCidade, {
        {"nome", Text.Proper, type text},
        {"cidade", Text.Proper, type text}
    }),
    ComDocumentoNormalizado = Table.AddColumn(Capitalizado, "Documento Normalizado",
        each Text.Select([documento], {"0".."9"}), type text),
    ComDataNascimento = Table.AddColumn(ComDocumentoNormalizado, "Data Nascimento",
        each
            let
                texto = Text.Trim([data_nascimento])
            in
                if Text.Contains(texto, "/") then
                    Date.FromText(texto, "pt-BR")  // DD/MM/YYYY
                else if Text.Contains(texto, "-") and Text.Length(Text.BeforeDelimiter(texto, "-")) = 4 then
                    Date.FromText(texto)           // YYYY-MM-DD
                else
                    Date.FromText(
                        Text.Combine(List.Reverse(Text.Split(texto, "-")), "-")
                    ),                              // DD-MM-YYYY -> YYYY-MM-DD
        type date),
    SemDuplicados = Table.Distinct(ComDataNascimento, {"cooperado_id"})
in
    SemDuplicados
```

> Nota para a apresentação: se preferirem ver passo a passo clicando em vez
> do M colado, reproduza cada `Table.X` acima como um botão da faixa
> "Transformar" — a lógica é a mesma, só a forma de chegar lá muda.

---

## dim_produto

1. Coluna customizada `Categoria Padronizada` — trata `"CONSIGNADO"`,
   `"agro "`, `" Consignado"` etc.

```m
let
    Origem = dim_produto,
    ComCategoriaPadronizada = Table.AddColumn(Origem, "Categoria Padronizada",
        each Text.Proper(Text.Trim([categoria])), type text)
in
    ComCategoriaPadronizada
```

---

## fato_contrato

1. Coluna customizada `Valor Contratado` — converte o texto BR
   (`"15.000,50"`) em número.
2. Tipos: `data_contratacao` e `data_vencimento_final` → Date.

```m
let
    Origem = fato_contrato,
    ComValorContratado = Table.AddColumn(Origem, "Valor Contratado",
        each Number.FromText(
            Text.Replace(
                Text.Replace([valor_contratado], ".", ""),   // remove separador de milhar
                ",", "."                                      // vírgula decimal -> ponto
            )
        ), type number),
    TiposDeData = Table.TransformColumnTypes(ComValorContratado, {
        {"data_contratacao", type date},
        {"data_vencimento_final", type date}
    })
in
    TiposDeData
```

---

## fato_parcela

Esta é a consulta com a lógica mais importante do modelo: a coluna
`Status Parcela`, usada por quase todas as medidas DAX.

```m
let
    Origem = fato_parcela,
    TiposDeData = Table.TransformColumnTypes(Origem, {
        {"data_vencimento", type date},
        {"data_pagamento", type date}
    }),
    DataCorte = #date(2026, 9, 30),
    ComStatusParcela = Table.AddColumn(TiposDeData, "Status Parcela",
        each
            if [data_pagamento] <> null then
                if [data_pagamento] > [data_vencimento] then "Paga com atraso" else "Paga em dia"
            else if [data_vencimento] > DataCorte then
                "A vencer"
            else
                let
                    dias = Duration.Days(DataCorte - [data_vencimento])
                in
                    if dias <= 30 then "Em atraso 1-30"
                    else if dias <= 60 then "Em atraso 31-60"
                    else if dias <= 90 then "Em atraso 61-90"
                    else "Em atraso 90+",
        type text),
    ComDiasAtraso = Table.AddColumn(ComStatusParcela, "Dias de Atraso",
        each if [data_pagamento] = null and [data_vencimento] <= DataCorte
             then Duration.Days(DataCorte - [data_vencimento])
             else 0,
        Int64.Type)
in
    ComDiasAtraso
```

> **Importante:** `DataCorte` está fixo em código (`#date(2026,9,30)`) de
> propósito — é a mesma decisão da seção de premissas do projeto: o cenário
> tem uma data de corte fixa para os números não mudarem a cada reabertura
> do arquivo. Isso substitui qualquer uso de `DateTime.LocalNow()`.

Auditoria (não entra nas medidas de negócio, só documenta qualidade de dados):

```m
    ComFlagPagamentoInvalido = Table.AddColumn(ComDiasAtraso, "Pagamento Antes da Contratação",
        each [data_pagamento] <> null and [data_pagamento] < Date.From(RelatedContratoDataContratacao),
        type logical)
```
*(Esse último passo depende de mesclar com `fato_contrato` antes — opcional,
usado só se quiser expor a métrica de qualidade de dados no dashboard; não é
pré-requisito para os KPIs principais.)*

---

## Resumo do que cada transformação resolve

| Consulta | Problema original | Resolvido por |
|---|---|---|
| dim_cooperado | nome/cidade sujos, datas mistas, documento (CPF/CNPJ) em formatos diferentes, ids duplicados | Trim + Proper + parser de data customizado + Remove Duplicates |
| dim_produto | categoria escrita de formas diferentes | Trim + Proper |
| fato_contrato | valor monetário como texto BR | Replace "." e "," + conversão para number |
| fato_parcela | status/atraso não existem nos dados crus | Coluna customizada com a regra de negócio completa |
