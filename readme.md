# Risco de Crédito — Cooperativa Horizonte Sul (projeto fictício)

Projeto de BI de ponta a ponta em Power BI: geração de base sintética em
SQLite, conexão via ODBC, tratamento no Power Query, modelagem em estrela,
tabela de datas com relações ativa/inativa e medidas DAX para análise de
risco de crédito.

> **Dados 100% sintéticos.** "Cooperativa Horizonte Sul" é um nome fictício,
> não corresponde a nenhuma instituição real. Todos os cooperados, CPFs,
> contratos e parcelas foram gerados por script (`scripts/gerar_dados.py`),
> sem qualquer relação com dados reais ou pessoas reais.

## Pergunta de negócio

> Onde está concentrado o risco de inadimplência da carteira de crédito, e
> como ele evolui no tempo?

## Status do projeto

| Etapa | Status |
|---|---|
| 1. Banco de dados (SQLite) | ✅ Gerado e validado |
| 2. Conexão e transformação (Power Query) | 📋 Documentado — a executar no Power BI Desktop |
| 3. Modelagem e relacionamentos | 📋 Documentado — a executar no Power BI Desktop |
| 4. Tabela de datas | 📋 Documentado — a executar no Power BI Desktop |
| 5. Medidas DAX | 📋 Escritas e prontas para colar |
| 6. Dashboard | 📋 Blueprint pronto — a montar no Power BI Desktop |

As etapas 2-6 dependem do Power BI Desktop, que **não está instalado nesta
máquina** (verificado durante a montagem deste projeto). Ver pré-requisitos
abaixo antes de abrir o `.pbix`.

---

## 1. Pré-requisitos

- **Python 3.10+** — usado só para gerar a base (já instalado e testado
  neste ambiente: Python 3.12.10).
- **Power BI Desktop** — [https://powerbi.microsoft.com/desktop/](https://powerbi.microsoft.com/desktop/)
  (gratuito). **Verificar a arquitetura instalada (32 ou 64 bits)** em
  Arquivo → Ajuda → Sobre — isso define qual driver ODBC baixar no passo 2.
  A versão mais comum hoje é 64 bits.
- **Driver ODBC do SQLite** (ver seção 2).

## 2. Instalação do driver ODBC do SQLite

1. Baixar o driver em [http://www.ch-werner.de/sqliteodbc/](http://www.ch-werner.de/sqliteodbc/)
   — escolher o instalador **da mesma arquitetura do Power BI Desktop**
   (32 ou 64 bits; o nome do arquivo costuma trazer `sqliteodbc_w64` ou
   `_w32`).
2. Instalar normalmente (Next, Next, Finish).
3. Abrir o **Administrador de Fontes de Dados ODBC** — no Windows, buscar
   por "ODBC Data Sources" e abrir a versão de **64 bits** (ou 32, igual ao
   driver instalado).
4. Aba **Drivers**: confirmar que "SQLite3 ODBC Driver" aparece na lista.
5. Aba **User DSN** → **Add** → selecionar o driver SQLite3 → em
   "Database Name", apontar para
   `database/cooperativa_horizonte_sul.db` (caminho completo) → nomear o
   DSN, por exemplo `cooperativa_horizonte_sul` → **Test** → deve retornar
   sucesso. Esse nome de DSN é o que será usado na conexão do Power BI.

> Se o teste falhar: a causa mais comum é arquitetura do driver diferente
> da do Power BI Desktop (um é 64 bits, o outro 32). Reinstalar o driver na
> arquitetura correta resolve.

## 3. Geração dos dados

```bash
python scripts/gerar_dados.py
```

O script:
- cria `database/cooperativa_horizonte_sul.db` (apaga e recria se já existir);
- exporta o conteúdo equivalente em `database/cooperativa_horizonte_sul.sql`
  (`CREATE TABLE` + `INSERT`), para reconstruir o banco em qualquer SQLite
  vazio sem depender do arquivo binário;
- imprime um resumo de contagem de linhas e das principais inconsistências
  propositais (duplicidade, órfãs).

Para recriar o banco a partir do `.sql` em vez do script Python:
```bash
sqlite3 novo_banco.db < database/cooperativa_horizonte_sul.sql
```

**Volume gerado:** 2.025 linhas em `dim_cooperado` (2.000 cooperados únicos +
25 duplicados de propósito), 8 PAs, 7 produtos, 3.000 contratos, 82.386
parcelas. O número de parcelas ficou acima da estimativa inicial de "~60 mil"
porque os prazos de contrato (12 a 48 meses) geram, na média, mais parcelas
por contrato do que a estimativa original previa — sem impacto no tamanho do
repositório (banco: ~4 MB; `.sql`: ~7,7 MB).

**Padrões plantados e validados por query direta no banco** (ver também
`docs/guia_dashboard.md`):
1. Produto "Crédito Pessoal" concentra a maior inadimplência 90+ (1.248
   parcelas em atraso 90+, contra 294-336 nos demais produtos).
2. PA Industrial e PA Centro concentram a maior inadimplência 90+ (1.208 e
   1.090 parcelas, contra 116-162 nos demais PAs).
3. Inadimplência mensal (parcelas não pagas na data de corte) sobe de 7,0%
   em janeiro/2026 para 33,1% em setembro/2026, com piora mais acentuada a
   partir de abril.
4. Concessão de contratos tem pico claro em novembro e dezembro (544 e 565
   contratos, contra ~185 de média nos demais meses).
5. Os 10 cooperados com maior saldo concentram ~28% do saldo total da
   carteira (calculado sobre valor de parcela em aberto, como proxy).

## 4. Dicionário de dados

Ver [`docs/dicionario_dados.md`](docs/dicionario_dados.md) — todas as
tabelas, colunas, tipos e observações de qualidade de dados.

## 5. Catálogo de inconsistências

Ver [`docs/catalogo_inconsistencias.md`](docs/catalogo_inconsistencias.md) —
cada inconsistência plantada, onde está, como tratar e por quê. Inclui a
mais crítica: duplicidade em `dim_cooperado`, sem a qual o relacionamento
1:N com `fato_contrato` não se sustenta.

## 6. Conexão no Power BI

1. Power BI Desktop → **Obter Dados** → **Outros** → **ODBC**.
2. Selecionar o DSN criado no passo 2 (`cooperativa_horizonte_sul`) → OK.
3. Na janela de prévia, marcar as 5 tabelas (`dim_cooperado`, `dim_pa`,
   `dim_produto`, `fato_contrato`, `fato_parcela`) → **Transformar Dados**
   (não "Carregar" direto — todo o tratamento acontece antes de carregar).
4. Confirmar que o modo de conexão é **Importar** (padrão do conector ODBC;
   não há opção DirectQuery para este driver). Em modo Importar, os dados
   ficam copiados dentro do `.pbix` — o driver ODBC só volta a ser necessário
   se um dia for preciso **atualizar** os dados a partir do SQLite de novo.

## 7. Transformações no Power Query

Ver [`docs/power_query_transformacoes.md`](docs/power_query_transformacoes.md)
— passo a passo de cada consulta, com código M pronto para colar no Editor
Avançado quando for mais rápido que clicar.

## 8. Modelagem e relacionamentos

Ver [`docs/modelagem_relacionamentos.md`](docs/modelagem_relacionamentos.md)
— todas as relações, cardinalidade e direção de filtro, com justificativa.

## 9. Tabela de datas

Ver [`docs/tabela_calendario.md`](docs/tabela_calendario.md) — código DAX da
`dim_calendario`, e por que ela se relaciona com `fato_contrato` por duas
datas (uma ativa, uma via `USERELATIONSHIP`).

## 10. Medidas DAX

Ver [`dax/medidas_dax.txt`](dax/medidas_dax.txt) — todas as medidas já
escritas, organizadas por categoria (carteira, inadimplência, volume,
concentração, evolução temporal), cada uma com finalidade e justificativa.
Basta criar uma tabela `_Medidas` vazia no modelo e colar cada bloco como
uma New Measure.

## 11. Dashboard

Ver [`docs/guia_dashboard.md`](docs/guia_dashboard.md) — blueprint completo
das duas páginas (Visão Executiva e Detalhamento de Risco), visual por
visual, com os títulos que enunciam a conclusão.

*(Esta seção será completada com prints reais do dashboard depois de
montado no Power BI Desktop.)*

## 12. Limitações e próximos passos

- **Saldo da carteira simplificado:** o projeto usa soma de parcelas em
  aberto como proxy de saldo devedor. Um modelo de carteira real traria
  amortização (juros vs. principal) separada por parcela — fora do escopo
  aqui porque a pergunta de negócio é sobre concentração/evolução de risco,
  não sobre contabilidade de carteira.
- **Sem DirectQuery:** o driver ODBC do SQLite não suporta DirectQuery no
  Power BI; o projeto usa modo Importar de propósito (adequado ao volume e
  ao fato de a base não mudar).
- **Parcelas órfãs mantidas, não corrigidas:** decisão deliberada para não
  mascarar um problema real de integridade referencial (ver catálogo de
  inconsistências, item 7).
- **Próximo passo natural:** trocar a fonte SQLite por uma fonte que
  suporte DirectQuery (SQL Server, por exemplo) se o volume crescer muito
  além do que cabe em modo Importar.

---

## Estrutura do repositório

```
scripts/gerar_dados.py         - gera o banco e exporta o .sql
database/*.db, *.sql           - banco SQLite e dump SQL equivalente
dax/medidas_dax.txt            - todas as medidas DAX, prontas para colar
docs/dicionario_dados.md       - tabelas, colunas, relacionamentos
docs/catalogo_inconsistencias.md - inconsistências plantadas e tratamento
docs/power_query_transformacoes.md - passo a passo + código M
docs/modelagem_relacionamentos.md  - relacionamentos e justificativas
docs/tabela_calendario.md      - dim_calendario e USERELATIONSHIP
docs/guia_dashboard.md         - blueprint das páginas do dashboard
*.pbix                         - (a adicionar após montar o dashboard)
```
