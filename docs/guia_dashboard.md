# Guia de montagem do dashboard

Público-alvo: diretores/gestores. Regra: poucos visuais por página, título
de cada página e de cada visual enuncia a conclusão (não descreve o dado),
poucos filtros, foco em decisão. Os números abaixo ("X%", "produto Y") são
placeholders — substitua pelos valores reais que aparecerem no seu `.pbix`
depois de montar as medidas (os padrões estão plantados nos dados, então a
direção da conclusão não deve mudar, só o número exato).

---

## Página 1 — Visão Executiva

**Título da página:** "Carteira estável em volume, mas a inadimplência está
piorando" (ajustar conforme o que os dados mostrarem na sua tela).

**Filtro no topo (slicer):** um único slicer de **Ano/Mês** (campo
`dim_calendario[MêsAno]`), afetando toda a página. Não adicionar mais
slicers aqui — é a página de "olhar e decidir", não de explorar.

**Linha de cards (KPIs), da esquerda para a direita:**
1. `Saldo da Carteira`
2. `% Inadimplência 90+`
3. `Var. Inadimplência 90+ (M/M)` — formatar com seta/cor condicional
   (vermelho se positivo = piorando, verde se negativo = melhorando)
4. `Volume Concedido`
5. `Ticket Médio`
6. `Contratos Ativos`

**Visual 1 (abaixo dos cards, à esquerda) — gráfico de linha:**
Eixo X = `dim_calendario[MêsAno]`, Valor = `% Inadimplência 90+`.
Título do visual: "Inadimplência 90+ sobe de forma consistente desde abril".
Isso é o padrão 3 plantado nos dados (piora gradual abr–set/2026) — a linha
deve mostrar uma inclinação clara de subida nesse trecho.

**Visual 2 (abaixo dos cards, à direita) — gráfico de colunas:**
Eixo X = `dim_calendario[Mês]` (todos os anos agregados ou um ano específico
via filtro), Valor = `Volume Concedido`.
Título do visual: "Concessão de crédito concentra em novembro e dezembro".
Isso é o padrão 4 plantado (sazonalidade) — novembro/dezembro devem aparecer
claramente mais altos que os demais meses.

---

## Página 2 — Detalhamento de Risco

**Título da página:** "O risco está concentrado em um produto e dois PAs"
(ou o que os dados confirmarem).

**Filtro no topo (slicer):** um único slicer de **Produto** OU **PA** (não
os dois) — escolha o que fizer mais sentido na narrativa ao vivo; o outro
eixo já aparece dentro dos próprios visuais.

**Visual 1 (esquerda) — gráfico de barras horizontais:**
Eixo Y = `dim_produto[nome_produto]`, Valor = `% Inadimplência 90+`,
ordenado decrescente.
Título: "Crédito Pessoal tem inadimplência muito acima dos demais produtos"
— padrão 1 plantado; essa barra deve se destacar visivelmente das outras.

**Visual 2 (direita) — gráfico de barras horizontais:**
Eixo Y = `dim_pa[nome_pa]`, Valor = `Saldo em Atraso 90+`, ordenado
decrescente.
Título: "PA Industrial e PA Centro concentram a maior parte do saldo em
atraso" — padrão 2 plantado; essas duas barras devem se destacar das outras
seis.

**Visual 3 (linha inferior, largura total) — matriz ou gráfico de colunas
empilhadas:**
Linhas = `dim_produto[nome_produto]`, Colunas/Legenda =
`fato_parcela[Status Parcela]` (filtrado só pelas 4 faixas de atraso, sem
"Paga"/"A vencer"), Valor = `Saldo em Atraso Total` (ou a soma de
`valor_parcela` direta).
Título: "Dentro de Crédito Pessoal, o atraso já é predominantemente 90+" (ou
o padrão que aparecer).

**Card isolado (canto, pequeno):** `% Concentração Top 10 Cooperados`.
Título: "10 cooperados concentram cerca de Xx% do saldo da carteira" —
padrão 5 plantado.

---

## Formatação geral (para as duas páginas)

- Moeda em Real (R$), separador de milhar `.`, decimal `,` — formato de
  número do Power BI configurado para `pt-BR` no nível do modelo (Arquivo →
  Opções → Regional, ou formato de cada medida individualmente).
- Percentuais com 1 casa decimal.
- Fundo neutro, sem gradientes fortes — o destaque deve vir dos dados (a
  barra do produto de risco, a linha subindo), não de cor decorativa.
- Nenhum visual de "tabela crua" nas duas páginas principais — se quiser uma
  página 3 de detalhe tabular para perguntas ao vivo tipo "me mostra os
  contratos do cooperado X", pode criar, mas fora do fluxo de apresentação
  principal.

## Perguntas que a apresentação deve responder sem precisar de pergunta extra

1. Onde está o risco? → produto + PA (página 2).
2. Está piorando ou melhorando? → linha de tendência + variação M/M (página 1).
3. Isso é um problema concentrado em poucos cooperados ou disperso? →
   concentração top 10 (página 2).

Se, ao montar, qualquer um dos 5 padrões não aparecer claramente no visual,
o problema está na medida ou no filtro aplicado — os dados foram validados
por query direta no SQLite antes da entrega (ver seção de validação no
README) e os 5 padrões estão confirmados na base.
