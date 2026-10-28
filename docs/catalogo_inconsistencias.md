# Catálogo de inconsistências

Cada inconsistência abaixo foi plantada de propósito em `scripts/gerar_dados.py`
para ser tratada no Power Query. Formato: **onde está → qual o problema →
como tratar → por quê**.

---

### 1. Documento (CPF/CNPJ) em formatos diferentes
**Onde:** `dim_cooperado.documento` (CPF para pessoa física, CNPJ para pessoa
jurídica; coluna renomeada de `cpf` para `documento` para cobrir os dois casos).
**Problema:** mesmo documento aparece como `"123.456.789-00"`, `"12345678900"`
ou `" 123.456.789-00 "` (com espaços), e o CNPJ da pessoa jurídica tem a
mesma variação de formatação.
**Tratamento:** `Text.Trim` + `Text.Remove` (removendo `.`, `-` e `/`) para
obter uma versão só-números, mantida como coluna de chave de comparação/
deduplicação. O tamanho dessa versão (11 dígitos = CPF, 14 dígitos = CNPJ)
também serve para inferir o tipo de pessoa de forma independente da coluna
`tipo_pessoa` (que está suja de propósito, ver item 10 abaixo).
**Por quê:** documento é usado para identificar duplicidade de cooperado
(ver item 8); sem normalizar, dois formatos do mesmo documento não são
reconhecidos como iguais.

### 2. Telefone em formatos diferentes
**Onde:** `dim_cooperado.telefone`
**Problema:** `"(47) 99999-9999"`, `"47999999999"`, `"47 9999-9999"`, e ~5% nulo.
**Tratamento:** padronizar removendo caracteres não numéricos; nulos mantidos
como nulos (não é campo analítico, não entra em nenhuma medida).
**Por quê:** campo de cadastro, não de análise — tratamento é só de
apresentação/qualidade, não afeta KPIs.

### 3. Caixa alta/baixa e espaços extras
**Onde:** `dim_cooperado.nome`, `dim_cooperado.cidade`, `dim_produto.categoria`.
**Problema:** `"  JOÃO SILVA  "`, `"vale verde"`, `"CONSIGNADO"` vs `"consignado"`
vs `" Consignado"` — mesma categoria escrita de formas diferentes.
**Tratamento:** `Text.Trim` + `Text.Proper` (nomes/cidades) ou padronização
manual via `Table.ReplaceValue`/coluna condicional (categorias de produto,
onde "Proper Case" sozinho não resolve abreviações como "agro " vs "Agro").
**Por quê:** sem isso, agrupamentos (ex.: "carteira por categoria de produto")
fragmentam o mesmo grupo em várias linhas no visual.

### 4. Datas em formatos diferentes
**Onde:** `dim_cooperado.data_nascimento`, `dim_cooperado.data_associacao`.
**Problema:** mesma coluna com `YYYY-MM-DD`, `DD/MM/YYYY` e `DD-MM-YYYY`
misturados.
**Tratamento:** `Date.FromText` não resolve sozinho (ambíguo DD/MM vs MM/DD);
usar função customizada em Power Query que testa os três padrões por regex/
tamanho de token antes de converter para tipo Date.
**Por quê:** campo de cadastro — não entra em relacionamento nem em medida,
mas precisa virar tipo Date para qualquer segmentação por faixa etária/tempo
de associação.

### 5. Valores nulos
**Onde:** `dim_cooperado.email` (~10%), `dim_cooperado.telefone` (~5%),
`dim_cooperado.sexo` (parte), `fato_contrato.taxa_juros_am` (~2%).
**Tratamento:** mantidos como nulos onde são campos de cadastro sem impacto
analítico (email, telefone, sexo). Em `taxa_juros_am`, nulo é deixado fora de
qualquer média (o `AVERAGE` do DAX já ignora nulos por padrão).
**Por quê:** nulo aqui representa ausência real de informação (não um erro),
então não deve ser preenchido artificialmente com zero ou um valor "médio" —
isso distorceria qualquer indicador.

### 6. Valor monetário gravado como texto
**Onde:** `fato_contrato.valor_contratado`.
**Problema:** coluna `TEXT` com formato brasileiro, ex.: `"15.000,50"`
(ponto de milhar, vírgula decimal) — se convertida direto para número, o
Power Query interpreta como `15.00050` ou dá erro.
**Tratamento:** trocar `.` por nada e `,` por `.` (nessa ordem) antes de
`Table.TransformColumnTypes` para `type number`.
**Por quê:** é o único valor monetário da base gravado como texto —
plantado assim de propósito para checar se o candidato sabe que conversão
direta de texto BR para número quebra sem esse passo.

### 7. Parcelas órfãs
**Onde:** `fato_parcela.contrato_id` (50 linhas).
**Problema:** `contrato_id` que não existe em `fato_contrato`.
**Tratamento:** ao relacionar `fato_parcela` com `fato_contrato` (N:1), essas
linhas ficam sem correspondência — decisão: **mantidas no fato**, mas
excluídas de qualquer medida que dependa de atributos de `fato_contrato`
(produto, PA, cooperado) porque o `JOIN`/relacionamento não as traz. Elas só
aparecem em uma medida de auditoria (contagem de órfãs) usada para apontar o
problema de qualidade de dados — não para "corrigir" silenciosamente.
**Por quê:** representa um erro real de integridade referencial (parcela
criada sem o contrato correspondente, ou contrato apagado depois). Remover
sem registrar escartografia a existência do problema; manter e isolar é mais
honesto para um relatório de qualidade de dados.

### 8. Duplicidade de cooperado
**Onde:** `dim_cooperado.cooperado_id` (25 ids duplicados).
**Problema:** a tabela não tem `PRIMARY KEY`/`UNIQUE` em `cooperado_id` de
propósito — o mesmo cooperado foi "recadastrado" com pequenas variações de
texto (nome com caixa diferente, telefone diferente).
**Tratamento:** `Table.Distinct` em `dim_cooperado` usando `cooperado_id`
como critério (mantendo a primeira ocorrência), **antes** de criar o
relacionamento com `fato_contrato`.
**Por quê:** Power BI exige valores únicos no lado "1" de uma relação 1:N —
sem esse passo, a relação não pode ser criada (ou o Power BI força
cardinalidade N:N, que quebra o modelo em estrela). Essa é a inconsistência
mais crítica da base: **sem tratá-la, o modelo inteiro não funciona.**

### 9. Pagamento anterior à contratação
**Onde:** `fato_parcela.data_pagamento` (15 linhas).
**Problema:** `data_pagamento` anterior a `fato_contrato.data_contratacao` —
impossível na prática (pagou antes de contratar).
**Tratamento:** coluna de auditoria calculada (`data_pagamento < data_contratacao`)
que sinaliza essas linhas; elas são **excluídas** das medidas de inadimplência
(tratadas como erro de lançamento, não como pagamento válido), mas reportadas
em uma métrica de qualidade de dados separada.
**Por quê:** incluir um erro óbvio de integridade sem tratamento inflaria
artificialmente "pagamentos em dia"; a decisão de excluir (em vez de corrigir
a data) é defensável porque não há como saber qual das duas datas está errada.

---

## Decisão de escopo

As datas que alimentam o modelo e as relações (`data_contratacao`,
`data_vencimento_final`, `data_vencimento`, `data_pagamento`) são geradas em
formato ISO consistente — a inconsistência de formato de data fica restrita
aos campos cadastrais (nascimento, associação). Isso reflete um padrão comum
em sistemas reais: o sistema transacional grava datas de forma consistente,
mas dados cadastrais entram por canais diferentes (presencial, app, herança
de sistema antigo) e chegam sujos. Misturar formato de data nas colunas que
alimentam relacionamento adicionaria complexidade sem agregar ao que o
desafio avalia.
