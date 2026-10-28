# Transformações no Power Query

Conexão: **Obter Dados → ODBC**, selecionando o DSN do SQLite (ver seção de
pré-requisitos no README), modo **Importar**. Cada tabela do banco entra como
uma consulta separada (`dim_cooperado`, `dim_pa`, `dim_produto`,
`fato_contrato`, `fato_parcela`, `meta_mensal`).

Abaixo, os passos de cada consulta na ordem em que devem ser aplicados, com o
código M equivalente (Editor Avançado) para colar direto quando for mais
rápido que repetir clique por clique ao vivo.

---

## dim_cooperado

Passos (em "Transformar Dados"):
1. `Trim` em `nome` e `cidade` (remove espaços nas pontas).
2. `Capitalize Each Word` em `nome` e `cidade` (resolve caixa alta/baixa; em
   `cidade` isso não resolve a falta de acento, ver nota abaixo).
3. Coluna customizada `Documento Normalizado` = só dígitos do CPF/CNPJ (para dedup).
4. Coluna customizada `Tipo Pessoa Padronizado` = `"PF"` ou `"PJ"`, resolvendo
   as 6 variantes de escrita (`"PF"`, `"pf"`, `"Pessoa Fisica"`, `"PJ"`,
   `"pj"`, `"Pessoa Juridica"`).
5. Coluna customizada `Data Nascimento` convertendo os 3 formatos de data em
   tipo Date.
6. `Remove Duplicates` em `cooperado_id` (mantém a primeira ocorrência) —
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
    ComTipoPessoaPadronizado = Table.AddColumn(ComDocumentoNormalizado, "Tipo Pessoa Padronizado",
        each
            let
                texto = Text.Upper(Text.Trim([tipo_pessoa]))
            in
                if Text.StartsWith(texto, "PF") or Text.Contains(texto, "FISICA")
                then "PF"
                else "PJ",
        type text),
    ComDataNascimento = Table.AddColumn(ComTipoPessoaPadronizado, "Data Nascimento",
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

> **`faixa_renda` e `porte` não precisam de transformação.** São
> mutuamente exclusivos por desenho: todo cooperado PF tem `faixa_renda`
> preenchida e `porte` nulo, todo PJ tem o inverso. Carregar como estão;
> usar `Tipo Pessoa Padronizado` para decidir qual dos dois exibir num
> visual (ex.: medida condicional, não transformação de tabela).

> **Acentos em `cidade` não são tratados aqui de propósito.** Duas cidades
> da base ("São Bento do Vale", "Águas Claras do Sul") perdem o acento em
> parte dos registros. `Text.Proper` não devolve o acento que já foi
> removido na origem — isso exigiria uma tabela de mapeamento cidade→forma
> canônica. Fica fora de escopo porque não afeta nenhuma medida (cidade do
> cooperado não entra em relacionamento nem em cálculo, só em texto livre
> de apoio); documentado aqui para não parecer esquecimento.

---

## dim_pa

Nenhuma sujeira foi plantada nesta tabela (nome, cidade, uf e regiao vêm
limpos da origem). O único passo é garantir os tipos corretos antes de
marcar a tabela como dimensão no modelo.

```m
let
    Origem = dim_pa,
    TiposDeColuna = Table.TransformColumnTypes(Origem, {
        {"pa_id", Int64.Type},
        {"nome_pa", type text},
        {"cidade", type text},
        {"uf", type text},
        {"regiao", type text}
    })
in
    TiposDeColuna
```

> `regiao` agrupa os 8 PAs em 4 regionais. Serve de nível acima de PA em
> hierarquias de visual (ex.: matriz Regional → PA), não precisa de
> tratamento porque não tem variação de escrita.

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
3. Coluna customizada `Garantia Padronizada` — resolve as 6 variantes de
   escrita de `garantia` (`"Com garantia"`, `"COM GARANTIA"`,
   `"com garantia "`, `"Sem garantia"`, `"SEM GARANTIA"`, `" sem Garantia"`).

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
    }),
    ComGarantiaPadronizada = Table.AddColumn(TiposDeData, "Garantia Padronizada",
        each
            if Text.StartsWith(Text.Upper(Text.Trim([garantia])), "COM")
            then "Com garantia"
            else "Sem garantia",
        type text)
in
    ComGarantiaPadronizada
```

> **`score_risco` e `nivel_risco` não precisam de transformação de
> limpeza** — já chegam como número (0-1000) e letra (A-E). O único ponto
> de atenção é `nivel_risco` nulo em 60 contratos (~2%): é ausência real de
> classificação, não um erro de escrita, então não deve ser preenchido com
> uma letra "média". Em medidas de taxa de inadimplência por nível de
> risco, os nulos ficam de fora do agrupamento por nível (comportamento
> padrão do Power BI) e aparecem separados se for necessário expor a
> contagem de contratos sem classificação. Se o visual pedir um rótulo
> em vez de branco, usar uma coluna só de exibição:
> `Table.ReplaceValue(ComGarantiaPadronizada, null, "Sem classificação", Replacer.ReplaceValue, {"nivel_risco"})`
> — aplicada em uma coluna separada, nunca sobrescrevendo `nivel_risco`.

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

## meta_mensal

Tabela de metas, uma linha por mês × PA (36 × 8 = 288 linhas). `mes` já
vem no banco como texto ISO sempre no primeiro dia do mês (ex.:
`"2026-09-01"`), sem variação de formato — só precisa virar tipo Date.

```m
let
    Origem = meta_mensal,
    TiposDeColuna = Table.TransformColumnTypes(Origem, {
        {"mes", type date},
        {"pa_id", Int64.Type},
        {"meta_saldo", type number},
        {"meta_volume_concedido", type number},
        {"teto_inadimplencia_90", type number}
    })
in
    TiposDeColuna
```

> **`meta_saldo` é meta de estoque, `meta_volume_concedido` é meta de
> fluxo** — não trocar uma pela outra em medida nenhuma (detalhe de
> modelagem, não de Power Query, mas registrado aqui porque nasce nesta
> consulta): `meta_saldo` só pode ser comparada ao saldo realizado no
> mesmo mês (nunca somada ao longo de vários meses); `meta_volume_concedido`
> pode ser somada ao longo dos meses e comparada ao volume originado no
> período. A forma como esta tabela se relaciona com `dim_calendario`
> (ela é mensal, o calendário é diário) é decidida na etapa 4, não aqui.

---

## Resumo do que cada transformação resolve

| Consulta | Problema original | Resolvido por |
|---|---|---|
| dim_cooperado | nome/cidade sujos, datas mistas, documento (CPF/CNPJ) em formatos diferentes, tipo_pessoa em 6 variantes de escrita, ids duplicados | Trim + Proper + coluna de tipo de pessoa padronizado + parser de data customizado + Remove Duplicates |
| dim_pa | nenhum (tabela limpa) | só ajuste de tipos |
| dim_produto | categoria escrita de formas diferentes | Trim + Proper |
| fato_contrato | valor monetário como texto BR, garantia em 6 variantes de escrita, nivel_risco nulo em parte dos contratos | Replace "." e "," + conversão para number; coluna de garantia padronizada; nulo mantido (ausência real, não erro) |
| fato_parcela | status/atraso não existem nos dados crus | Coluna customizada com a regra de negócio completa |
| meta_mensal | nenhuma sujeira, só tipo de dado | ajuste de tipos (mes → Date) |
