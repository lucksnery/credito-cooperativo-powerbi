# Modelagem e relacionamentos

Modelo em estrela: 4 dimensões (`dim_cooperado`, `dim_pa`, `dim_produto`,
`dim_calendario`) e 2 fatos (`fato_contrato`, `fato_parcela`), com
`fato_parcela` "pendurada" em `fato_contrato` (fato secundário).

## Relacionamentos

| De | Para | Cardinalidade | Direção do filtro | Ativa? |
|---|---|---|---|---|
| dim_cooperado[cooperado_id] | fato_contrato[cooperado_id] | 1:N | Único (dimensão → fato) | Sim |
| dim_pa[pa_id] | fato_contrato[pa_id] | 1:N | Único | Sim |
| dim_produto[produto_id] | fato_contrato[produto_id] | 1:N | Único | Sim |
| fato_contrato[contrato_id] | fato_parcela[contrato_id] | 1:N | Único | Sim |
| dim_calendario[Data] | fato_contrato[data_contratacao] | 1:N | Único | **Sim** |
| dim_calendario[Data] | fato_contrato[data_vencimento_final] | 1:N | Único | **Não** (via `USERELATIONSHIP`) |
| dim_calendario[Data] | fato_parcela[data_vencimento] | 1:N | Único | Sim |

## Por que cardinalidade 1:N e não N:N

Cada contrato pertence a exatamente um cooperado, um PA e um produto — e cada
parcela pertence a exatamente um contrato. O lado "1" (dimensão) precisa ter
valores únicos na coluna de relacionamento; é exatamente por isso que a
deduplicação de `dim_cooperado` (catálogo de inconsistências, item 8) é
obrigatória — sem ela, `cooperado_id` repete valores no lado "1" e o Power BI
não aceita a relação como 1:N.

## Por que direção única (não "Ambas")

Direção "Ambas" (filtro bidirecional) propagaria filtro de `fato_contrato`
de volta para `dim_cooperado`, por exemplo — útil em poucos cenários (como
"cooperados que têm contrato de um produto X"), mas aqui não é necessário e
aumenta o risco de ambiguidade quando há múltiplos caminhos entre tabelas
(como os dois caminhos de `fato_contrato` até `fato_parcela` via
`dim_calendario`, se a direção fosse dupla em ambas as pontas). Direção única,
da dimensão para o fato, é a prática padrão em modelo estrela e evita esse
risco.

## Por que fato_parcela não se relaciona direto com dim_cooperado/dim_pa/dim_produto

`fato_parcela` só tem `contrato_id` como chave — os atributos de cooperado,
PA e produto chegam a ela **por propagação de filtro** através de
`fato_contrato` (que já está relacionada a essas 3 dimensões). Criar relações
diretas de `fato_parcela` para essas dimensões seria redundante e abriria
caminhos múltiplos entre as mesmas tabelas (ambiguidade de filtro).

## Sobre as parcelas órfãs (catálogo de inconsistências, item 7)

As 50 linhas de `fato_parcela` com `contrato_id` inexistente em
`fato_contrato` **não geram erro de relacionamento** — no Power BI, linhas
do lado "N" sem correspondência no lado "1" simplesmente não recebem filtro
propagado da dimensão (ficam de fora de qualquer visual filtrado por
produto/PA/cooperado, mas continuam contadas em `COUNTROWS(fato_parcela)`).
É esse comportamento que torna necessária uma medida de auditoria separada
para não "escondê-las" silenciosamente (ver `dicionario_dados.md` e
`catalogo_inconsistencias.md`).
