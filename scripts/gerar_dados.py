"""
Gerador de dados sinteticos - Cooperativa Horizonte Sul (ficticia).

Cria um banco SQLite com 6 tabelas (4 dimensoes + 2 fatos, mais a tabela de
metas) e exporta o mesmo conteudo em um arquivo .sql (CREATE TABLE + INSERT).

Padroes propositalmente plantados nos dados (usados depois no dashboard).
Originais:
  1. O produto "Credito Pessoal" tem inadimplencia bem acima dos demais.
  2. Dois PAs (postos de atendimento) concentram carteira e atraso.
  3. A inadimplencia 90+ (medida ponto no tempo, nao por coorte de
     vencimento) sobe de forma gradual a partir de abril/2026.
  4. A concessao de contratos tem pico sazonal em nov/dez.
  5. Um grupo pequeno de cooperados concentra grande parte do saldo.
Novos:
  6. Pessoa juridica tem inadimplencia MENOR que pessoa fisica.
  7. Contrato sem garantia atrasa mais que contrato com garantia.
  8. score_risco e nivel_risco sao coerentes com o atraso real (D e E
     concentram atraso, porque sao derivados do mesmo fator de risco que
     determina a chance de atraso).
  9. Um PA bate a meta mensal com folga, outro fica sistematicamente abaixo.

Inconsistencias propositais (para tratamento no Power Query) - ver tambem
docs/catalogo_inconsistencias.md:
  - CPF/CNPJ e telefone em formatos diferentes.
  - Nome, cidade e categoria de produto com caixa alta/baixa misturada,
    espacos extras e (cidade) acentos inconsistentes.
  - tipo_pessoa escrito de formas diferentes ("PJ", "pj", "Pessoa Juridica").
  - garantia escrita de formas diferentes ("Com garantia", "COM GARANTIA").
  - Datas de nascimento/associacao em formatos diferentes (ISO, BR).
  - Valores nulos em email, telefone, sexo e nivel_risco (poucos contratos).
  - cooperado_id duplicado (mesma pessoa recadastrada) - a tabela nao tem
    PRIMARY KEY/UNIQUE em cooperado_id de proposito.
  - valor_contratado gravado como TEXTO em formato BR ("15.000,50").
  - Parcelas orfas (contrato_id que nao existe em fato_contrato).
  - Parcelas com data_pagamento anterior a data_contratacao do contrato.

A data de corte do cenario e fixa em 30/09/2026. Os parametros de
narrativa abaixo controlam QUAIS segmentos sao mais arriscados - inverter
um padrao e so trocar a constante correspondente.
"""

import math
import random
import sqlite3
import unicodedata
from datetime import date, timedelta
from pathlib import Path

SEED = 42
random.seed(SEED)

# ---------------------------------------------------------------------------
# PARAMETROS DE NARRATIVA - mude aqui para inverter ou recalibrar os padroes
# ---------------------------------------------------------------------------
DATA_CORTE = date(2026, 9, 30)
INICIO_HISTORICO = date(2023, 10, 1)

N_COOPERADOS = 2000
N_COOPERADOS_DUPLICADOS = 25
N_CONTRATOS = 3000
N_PARCELAS_ORFAS = 50
N_PAGAMENTOS_ANTES_DA_CONTRATACAO = 15
N_NIVEL_RISCO_NULO = 60  # ~2% dos contratos

PRODUTO_RISCO_NOME = "Credito Pessoal"   # produto com inadimplencia mais alta
MULT_PRODUTO_RISCO = 4.0
PAS_CONCENTRADOS_NOMES = {"PA Centro", "PA Industrial"}  # PAs com maior atraso
MULT_PA_CONCENTRADO = 2.0
MULT_PJ = 0.5             # PJ tem inadimplencia MENOR que PF (fator < 1 = menos risco)
MULT_SEM_GARANTIA = 1.8   # contrato sem garantia atrasa mais que com garantia
PCT_PJ = 0.15             # fracao de cooperados que sao pessoa juridica

BASE_RATE = 0.02          # probabilidade-base (contrato "medio", risco_fator=1) de atrasar
RAMPA_INICIO = date(2026, 4, 1)
RAMPA_FIM = date(2026, 9, 30)
RAMPA_MULTIPLICADOR_MAX = 160.0  # o quanto a rampa multiplica o risco no fim da janela

PA_META_FOLGADA = "PA Litoral"  # bate a meta mensal com folga
PA_META_APERTADA = "PA Sul"     # fica sistematicamente abaixo da meta mensal
TETO_INADIMPLENCIA_90 = 0.08     # teto de inadimplencia 90+ definido na meta (criterio interno)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "cooperativa_horizonte_sul.db"
SQL_PATH = BASE_DIR / "database" / "cooperativa_horizonte_sul.sql"

NOMES = [
    "Ana", "Bruno", "Carla", "Daniel", "Elisa", "Fabio", "Gabriela", "Hugo",
    "Isabela", "Joao", "Karina", "Leonardo", "Mariana", "Nelson", "Otavio",
    "Patricia", "Rafael", "Sabrina", "Thiago", "Vanessa", "William", "Yasmin",
    "Cesar", "Debora", "Eduardo", "Fernanda", "Gustavo", "Helena", "Igor",
    "Julia", "Lucas", "Monica", "Natalia", "Paulo", "Renata", "Simone",
]
SOBRENOMES = [
    "Silva", "Souza", "Oliveira", "Santos", "Pereira", "Costa", "Rodrigues",
    "Almeida", "Nascimento", "Lima", "Araujo", "Fernandes", "Carvalho",
    "Gomes", "Martins", "Rocha", "Ribeiro", "Alves", "Monteiro", "Cardoso",
    "Teixeira", "Correia", "Barbosa", "Pinto", "Moreira",
]
RAZOES_SOCIAIS = [
    "Comercio", "Distribuidora", "Industria", "Servicos", "Transportes",
    "Alimentos", "Confeccoes", "Materiais de Construcao", "Autopecas",
]
CIDADES_UF = [
    ("Vale Verde", "SC"), ("Porto Alto", "SC"), ("Serra Nova", "SC"),
    ("Campo Bello", "SC"), ("Rio Claro do Sul", "SC"), ("Monte Alegre", "SC"),
    ("Santa Fonte", "SC"), ("Barra Funda do Sul", "SC"),
    ("São Bento do Vale", "SC"), ("Águas Claras do Sul", "SC"),
]

# (nome_pa, cidade, uf, regiao)
PAS = [
    ("PA Centro", "Vale Verde", "SC", "Regional 1"),
    ("PA Norte", "Porto Alto", "SC", "Regional 2"),
    ("PA Industrial", "Vale Verde", "SC", "Regional 1"),
    ("PA Agro", "Campo Bello", "SC", "Regional 3"),
    ("PA Sul", "Serra Nova", "SC", "Regional 2"),
    ("PA Litoral", "Barra Funda do Sul", "SC", "Regional 4"),
    ("PA Centro II", "Monte Alegre", "SC", "Regional 1"),
    ("PA Vale", "Santa Fonte", "SC", "Regional 3"),
]
PAS_CONCENTRADOS = {i for i, p in enumerate(PAS) if p[0] in PAS_CONCENTRADOS_NOMES}
PA_IDX_META_FOLGADA = next(i for i, p in enumerate(PAS) if p[0] == PA_META_FOLGADA)
PA_IDX_META_APERTADA = next(i for i, p in enumerate(PAS) if p[0] == PA_META_APERTADA)

# (nome_produto, categoria, prob_com_garantia)
PRODUTOS = [
    ("Credito Pessoal", "pessoal", 0.15),
    ("Consignado Publico", "consignado", 0.90),
    ("Consignado INSS", "CONSIGNADO", 0.90),
    ("Financiamento de Veiculos", "veiculos", 0.95),
    ("Capital de Giro PJ", "Empresarial", 0.60),
    ("Credito Agro", "agro ", 0.70),
    ("Cartao Consignado", " Consignado", 0.85),
]
PRODUTO_RISCO_IDX = next(i for i, p in enumerate(PRODUTOS) if p[0] == PRODUTO_RISCO_NOME)

FAIXAS_RENDA_PF = ["Ate R$ 2.000", "De R$ 2.000 a R$ 5.000", "De R$ 5.000 a R$ 10.000", "Acima de R$ 10.000"]
PESOS_FAIXA_RENDA_PF = [0.25, 0.40, 0.25, 0.10]
PORTES_PJ = ["Microempresa", "Pequena Empresa", "Media Empresa"]
PESOS_PORTE_PJ = [0.60, 0.30, 0.10]

VARIANTES_TIPO_PESSOA = {"PF": ["PF", "pf", "Pessoa Fisica"], "PJ": ["PJ", "pj", "Pessoa Juridica"]}
VARIANTES_GARANTIA = {
    "Com garantia": ["Com garantia", "COM GARANTIA", "com garantia "],
    "Sem garantia": ["Sem garantia", "SEM GARANTIA", " sem Garantia"],
}


def aplicar_sujeira_texto(texto: str) -> str:
    """Aplica aleatoriamente caixa alta/baixa e espacos extras a um texto."""
    estilo = random.random()
    if estilo < 0.15:
        texto = texto.upper()
    elif estilo < 0.30:
        texto = texto.lower()
    if random.random() < 0.15:
        texto = f"  {texto}  "
    return texto


def remover_acentos(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def aplicar_sujeira_cidade(cidade: str) -> str:
    """Alem de caixa/espacos, remove acentos em parte dos registros."""
    if random.random() < 0.3:
        cidade = remover_acentos(cidade)
    return aplicar_sujeira_texto(cidade)


def _digito_modulo11(nums, pesos):
    soma = sum(n * p for n, p in zip(nums, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def gerar_cpf_fake() -> str:
    """CPF com formato e digitos verificadores validos (ficticio)."""
    base = [random.randint(0, 9) for _ in range(9)]
    d1 = _digito_modulo11(base, range(10, 1, -1))
    d2 = _digito_modulo11(base + [d1], range(11, 1, -1))
    return "".join(str(n) for n in base + [d1, d2])


def gerar_cnpj_fake() -> str:
    """CNPJ com formato e digitos verificadores validos (ficticio)."""
    base = [random.randint(0, 9) for _ in range(12)]
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _digito_modulo11(base, pesos1)
    d2 = _digito_modulo11(base + [d1], pesos2)
    return "".join(str(n) for n in base + [d1, d2])


def formatar_documento(numero: str, tipo_pessoa_real: str) -> str:
    """Formata CPF/CNPJ em estilos diferentes (inconsistencia proposital)."""
    estilo = random.random()
    if tipo_pessoa_real == "PF":
        if estilo < 0.4:
            return f"{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"
        if estilo < 0.7:
            return numero
        return f" {numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]} "
    if estilo < 0.4:
        return f"{numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}"
    if estilo < 0.7:
        return numero
    return f" {numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]} "


def gerar_telefone() -> str | None:
    if random.random() < 0.05:
        return None
    ddd = random.choice(["47", "48", "49"])
    numero = f"9{random.randint(1000, 9999)}{random.randint(1000, 9999)}"
    estilo = random.random()
    if estilo < 0.4:
        return f"({ddd}) {numero[:5]}-{numero[5:]}"
    if estilo < 0.7:
        return f"{ddd}{numero}"
    return f"{ddd} {numero[:5]}-{numero[5:]}"


def data_aleatoria_formatada(d: date) -> str:
    """Formata uma data em um de tres formatos possiveis (inconsistencia)."""
    estilo = random.random()
    if estilo < 0.5:
        return d.strftime("%Y-%m-%d")
    if estilo < 0.8:
        return d.strftime("%d/%m/%Y")
    return d.strftime("%d-%m-%Y")


def gerar_cooperados():
    linhas = []
    pessoas_vip = set(random.sample(range(1, N_COOPERADOS + 1), 20))
    for cooperado_id in range(1, N_COOPERADOS + 1):
        tipo_pessoa_real = "PJ" if random.random() < PCT_PJ else "PF"
        cidade, uf = random.choice(CIDADES_UF)
        nascimento = date(
            random.randint(1950, 2005), random.randint(1, 12), random.randint(1, 28)
        )
        associacao = INICIO_HISTORICO + timedelta(
            days=random.randint(0, (DATA_CORTE - INICIO_HISTORICO).days)
        )
        sexo = random.choice(["M", "F", "m", "f", None])
        if sexo is not None and random.random() < 0.9:
            sexo = sexo.upper()

        if tipo_pessoa_real == "PF":
            nome = f"{random.choice(NOMES)} {random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"
            documento = formatar_documento(gerar_cpf_fake(), "PF")
            faixa_renda = random.choices(FAIXAS_RENDA_PF, weights=PESOS_FAIXA_RENDA_PF)[0]
            porte = None
        else:
            nome = f"{random.choice(SOBRENOMES)} {random.choice(RAZOES_SOCIAIS)} Ltda"
            documento = formatar_documento(gerar_cnpj_fake(), "PJ")
            faixa_renda = None
            porte = random.choices(PORTES_PJ, weights=PESOS_PORTE_PJ)[0]

        email = (
            None
            if random.random() < 0.1
            else f"{nome.split()[0].lower()}.{cooperado_id}@teste.com.br"
        )

        linhas.append(
            {
                "cooperado_id": cooperado_id,
                "nome": aplicar_sujeira_texto(nome),
                "documento": documento,
                "tipo_pessoa_real": tipo_pessoa_real,
                "tipo_pessoa": random.choice(VARIANTES_TIPO_PESSOA[tipo_pessoa_real]),
                "faixa_renda": faixa_renda,
                "porte": porte,
                "data_nascimento": data_aleatoria_formatada(nascimento),
                "telefone": gerar_telefone(),
                "email": email,
                "sexo": sexo,
                "cidade": aplicar_sujeira_cidade(cidade),
                "uf": uf,
                "data_associacao": data_aleatoria_formatada(associacao),
                "vip": cooperado_id in pessoas_vip,
            }
        )

    # duplicidade proposital: mesma pessoa recadastrada com texto diferente
    duplicados = random.sample(linhas, N_COOPERADOS_DUPLICADOS)
    for original in duplicados:
        copia = dict(original)
        copia["nome"] = aplicar_sujeira_texto(original["nome"].strip().title())
        copia["telefone"] = gerar_telefone()
        linhas.append(copia)

    return linhas


def gerar_pas():
    return [
        {"pa_id": i + 1, "nome_pa": nome, "cidade": cidade, "uf": uf, "regiao": regiao}
        for i, (nome, cidade, uf, regiao) in enumerate(PAS)
    ]


def gerar_produtos():
    return [
        {"produto_id": i + 1, "nome_produto": nome, "categoria": categoria}
        for i, (nome, categoria, _prob_garantia) in enumerate(PRODUTOS)
    ]


def fator_sazonal_concessao(d: date) -> float:
    return 3.0 if d.month in (11, 12) else 1.0


def gerar_data_contratacao() -> date:
    """Sorteia uma data de contratacao com pico sazonal em nov/dez."""
    dias_totais = (DATA_CORTE - INICIO_HISTORICO).days
    while True:
        candidata = INICIO_HISTORICO + timedelta(days=random.randint(0, dias_totais))
        if random.random() < fator_sazonal_concessao(candidata) / 3.0:
            return candidata


def risco_fator_contrato(produto_idx: int, pa_idx: int, tipo_pessoa_real: str, garantia: str) -> float:
    """Fator de risco estrutural do contrato (nao inclui a rampa temporal).

    E o mesmo fator usado para decidir a chance de atraso e para derivar o
    score_risco - por isso score_risco e atraso saem coerentes um com o
    outro (nivel D/E concentra atraso de verdade, nao so no nome).
    """
    mult_produto = MULT_PRODUTO_RISCO if produto_idx == PRODUTO_RISCO_IDX else 1.0
    mult_pa = MULT_PA_CONCENTRADO if pa_idx in PAS_CONCENTRADOS else 1.0
    mult_pessoa = MULT_PJ if tipo_pessoa_real == "PJ" else 1.0
    mult_garantia = 1.0 if garantia == "Com garantia" else MULT_SEM_GARANTIA
    return mult_produto * mult_pa * mult_pessoa * mult_garantia


def score_e_nivel_risco(risco_fator: float) -> tuple[int, str]:
    score = 850 - 150 * math.log2(risco_fator) + random.gauss(0, 50)
    score = max(0, min(1000, round(score)))
    if score >= 800:
        nivel = "A"
    elif score >= 650:
        nivel = "B"
    elif score >= 450:
        nivel = "C"
    elif score >= 300:
        nivel = "D"
    else:
        nivel = "E"
    return score, nivel


def gerar_contratos(cooperados):
    contratos = []
    tipo_pessoa_por_cooperado = {c["cooperado_id"]: c["tipo_pessoa_real"] for c in cooperados}
    cooperados_normais = [c for c in cooperados if not c["vip"]]
    cooperados_vip = [c for c in cooperados if c["vip"]]
    ids_normais = list({c["cooperado_id"] for c in cooperados_normais})
    ids_vip = list({c["cooperado_id"] for c in cooperados_vip})

    for contrato_id in range(1, N_CONTRATOS + 1):
        # ~8% dos contratos vao para o grupo VIP, com ticket muito maior
        eh_vip = random.random() < 0.08
        cooperado_id = random.choice(ids_vip) if eh_vip else random.choice(ids_normais)
        tipo_pessoa_real = tipo_pessoa_por_cooperado[cooperado_id]

        pa_idx = random.choices(
            range(len(PAS)),
            weights=[4 if i in PAS_CONCENTRADOS else 1 for i in range(len(PAS))],
        )[0]
        produto_idx = random.randrange(len(PRODUTOS))
        prob_com_garantia = PRODUTOS[produto_idx][2]
        garantia_real = "Com garantia" if random.random() < prob_com_garantia else "Sem garantia"

        data_contratacao = gerar_data_contratacao()
        prazo_meses = random.choice([12, 18, 24, 36, 48])
        data_vencimento_final = data_contratacao + timedelta(days=30 * prazo_meses)

        if eh_vip:
            valor_contratado = round(random.uniform(80_000, 250_000), 2)
        else:
            valor_contratado = round(random.uniform(1_500, 40_000), 2)

        taxa_juros_am = round(random.uniform(1.2, 4.5), 2)
        valor_parcela = round(valor_contratado / prazo_meses * (1 + taxa_juros_am / 100), 2)
        valor_texto = f"{valor_contratado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        risco_fator = risco_fator_contrato(produto_idx, pa_idx, tipo_pessoa_real, garantia_real)
        score_risco, nivel_risco = score_e_nivel_risco(risco_fator)

        contratos.append(
            {
                "contrato_id": contrato_id,
                "cooperado_id": cooperado_id,
                "pa_id": pa_idx + 1,
                "produto_id": produto_idx + 1,
                "data_contratacao": data_contratacao.isoformat(),
                "data_vencimento_final": data_vencimento_final.isoformat(),
                "prazo_meses": prazo_meses,
                "taxa_juros_am": taxa_juros_am if random.random() > 0.02 else None,
                "valor_contratado": valor_texto,
                "valor_parcela": valor_parcela,
                "garantia": random.choice(VARIANTES_GARANTIA[garantia_real]),
                "score_risco": score_risco,
                "nivel_risco": nivel_risco,
                "pa_idx": pa_idx,
                "produto_idx": produto_idx,
                "risco_fator": risco_fator,
            }
        )

    # nivel_risco nulo em poucos contratos (inconsistencia proposital)
    for c in random.sample(contratos, N_NIVEL_RISCO_NULO):
        c["nivel_risco"] = None

    return contratos


def fator_tempo_atraso(vencimento: date) -> float:
    """Rampa de piora da inadimplencia entre RAMPA_INICIO e RAMPA_FIM."""
    if vencimento < RAMPA_INICIO or vencimento > RAMPA_FIM:
        return 1.0
    progresso = (vencimento - RAMPA_INICIO).days / (RAMPA_FIM - RAMPA_INICIO).days
    return 1.0 + (RAMPA_MULTIPLICADOR_MAX - 1.0) * progresso


def gerar_parcelas(contratos):
    """Gera as parcelas de cada contrato.

    A decisao de atraso/pagamento de cada parcela usa um gerador aleatorio
    PROPRIO, semeado por (contrato_id, numero_parcela). Isso isola a parcela
    das demais: reclibrar uma constante (BASE_RATE, rampa) move so as
    parcelas cujo resultado realmente deveria mudar, em vez de embaralhar o
    sorteio de todo o resto da base (o que aconteceria se todas as parcelas
    compartilhassem a mesma sequencia global de numeros aleatorios).
    """
    parcelas = []
    parcela_id = 1

    for contrato in contratos:
        data_contratacao = date.fromisoformat(contrato["data_contratacao"])
        prazo = contrato["prazo_meses"]
        valor_parcela = contrato["valor_parcela"]
        risco_fator = contrato["risco_fator"]

        for n in range(1, prazo + 1):
            vencimento = data_contratacao + timedelta(days=30 * n)
            if vencimento > DATA_CORTE + timedelta(days=365 * 3):
                break  # nao gera parcelas absurdamente no futuro

            rng_parcela = random.Random(contrato["contrato_id"] * 1000 + n)
            prob_atraso = min(0.95, BASE_RATE * risco_fator * fator_tempo_atraso(vencimento))

            data_pagamento = None
            if vencimento <= DATA_CORTE:
                if rng_parcela.random() > prob_atraso:
                    data_pagamento = vencimento + timedelta(days=rng_parcela.randint(-5, 5))
                else:
                    if rng_parcela.random() < 0.4:
                        data_pagamento = vencimento + timedelta(days=rng_parcela.randint(10, 150))
                        if data_pagamento > DATA_CORTE:
                            data_pagamento = None
            # parcelas futuras (vencimento > DATA_CORTE) ficam com pagamento nulo (a vencer)

            parcelas.append(
                {
                    "parcela_id": parcela_id,
                    "contrato_id": contrato["contrato_id"],
                    "numero_parcela": n,
                    "data_vencimento": vencimento.isoformat(),
                    "valor_parcela": valor_parcela,
                    "data_pagamento": data_pagamento.isoformat() if data_pagamento else None,
                    "valor_pago": valor_parcela if data_pagamento else None,
                }
            )
            parcela_id += 1

    # parcelas orfas: contrato_id que nao existe
    max_contrato_id = len(contratos)
    for _ in range(N_PARCELAS_ORFAS):
        vencimento = INICIO_HISTORICO + timedelta(
            days=random.randint(0, (DATA_CORTE - INICIO_HISTORICO).days)
        )
        parcelas.append(
            {
                "parcela_id": parcela_id,
                "contrato_id": max_contrato_id + random.randint(1000, 9000),
                "numero_parcela": 1,
                "data_vencimento": vencimento.isoformat(),
                "valor_parcela": round(random.uniform(100, 2000), 2),
                "data_pagamento": None,
                "valor_pago": None,
            }
        )
        parcela_id += 1

    # pagamento antes da contratacao: erro de integridade proposital
    candidatas = [p for p in parcelas if p["contrato_id"] <= max_contrato_id]
    contratos_por_id = {c["contrato_id"]: c for c in contratos}
    for p in random.sample(candidatas, N_PAGAMENTOS_ANTES_DA_CONTRATACAO):
        contrato = contratos_por_id[p["contrato_id"]]
        data_contratacao = date.fromisoformat(contrato["data_contratacao"])
        p["data_pagamento"] = (data_contratacao - timedelta(days=random.randint(5, 60))).isoformat()
        p["valor_pago"] = p["valor_parcela"]

    return parcelas


def gerar_metas(pas, contratos, parcelas):
    """Uma linha por mes/PA, calibrada a partir do volume e saldo realizados.

    A meta nao e um numero independente: e o realizado do PA multiplicado
    por um fator. PA_META_FOLGADA usa fator < 1 (meta facil de bater);
    PA_META_APERTADA usa fator > 1 (meta dificil de bater); os demais PAs
    ficam perto de 1, com ruido, como em qualquer definicao real de meta.
    """
    contrato_por_id = {c["contrato_id"]: c for c in contratos}

    meses = []
    cursor = date(INICIO_HISTORICO.year, INICIO_HISTORICO.month, 1)
    fim = date(DATA_CORTE.year, DATA_CORTE.month, 1)
    while cursor <= fim:
        meses.append(cursor)
        cursor = date(cursor.year + (1 if cursor.month == 12 else 0), (cursor.month % 12) + 1, 1)

    volume_por_mes_pa = {(m, pa["pa_id"]): 0.0 for m in meses for pa in pas}
    for c in contratos:
        d = date.fromisoformat(c["data_contratacao"])
        mes = date(d.year, d.month, 1)
        if (mes, c["pa_id"]) in volume_por_mes_pa:
            volume_por_mes_pa[(mes, c["pa_id"])] += c["valor_parcela"] * c["prazo_meses"]

    # saldo_por_mes_pa e um ESTOQUE (saldo da carteira do PA no fim daquele
    # mes), nao um fluxo por coorte de vencimento - por isso reavalia, para
    # cada mes, todas as parcelas do PA ainda nao pagas naquele fim de mes
    # (inclusive as que vencem depois dele). Mistura estoque com fluxo foi
    # o erro que inflou o "atingimento" de todos os PAs na primeira versao.
    parcelas_por_pa = {pa["pa_id"]: [] for pa in pas}
    for p in parcelas:
        contrato = contrato_por_id.get(p["contrato_id"])
        if contrato is not None:
            parcelas_por_pa[contrato["pa_id"]].append(p)

    saldo_por_mes_pa = {}
    for mes in meses:
        proximo_mes = date(mes.year + (1 if mes.month == 12 else 0), (mes.month % 12) + 1, 1)
        fim_do_mes = (proximo_mes - timedelta(days=1)).isoformat()
        for pa in pas:
            saldo = sum(
                p["valor_parcela"]
                for p in parcelas_por_pa[pa["pa_id"]]
                if p["data_pagamento"] is None or p["data_pagamento"] > fim_do_mes
            )
            saldo_por_mes_pa[(mes, pa["pa_id"])] = saldo

    linhas = []
    for mes in meses:
        for pa in pas:
            pa_idx = pa["pa_id"] - 1
            if pa_idx == PA_IDX_META_FOLGADA:
                fator = 0.80
            elif pa_idx == PA_IDX_META_APERTADA:
                fator = 1.15
            else:
                fator = random.uniform(0.95, 1.05)

            volume_realizado = volume_por_mes_pa[(mes, pa["pa_id"])]
            saldo_realizado = saldo_por_mes_pa[(mes, pa["pa_id"])]
            linhas.append(
                {
                    "mes": mes.isoformat(),
                    "pa_id": pa["pa_id"],
                    "meta_saldo": round(saldo_realizado * fator, 2),
                    "meta_volume_concedido": round(volume_realizado * fator, 2),
                    "teto_inadimplencia_90": TETO_INADIMPLENCIA_90,
                }
            )
    return linhas


def criar_banco(cooperados, pas, produtos, contratos, parcelas, metas):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE dim_cooperado (
            cooperado_id INTEGER,
            nome TEXT,
            documento TEXT,
            tipo_pessoa TEXT,
            faixa_renda TEXT,
            porte TEXT,
            data_nascimento TEXT,
            telefone TEXT,
            email TEXT,
            sexo TEXT,
            cidade TEXT,
            uf TEXT,
            data_associacao TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE dim_pa (
            pa_id INTEGER PRIMARY KEY,
            nome_pa TEXT,
            cidade TEXT,
            uf TEXT,
            regiao TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE dim_produto (
            produto_id INTEGER PRIMARY KEY,
            nome_produto TEXT,
            categoria TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE fato_contrato (
            contrato_id INTEGER PRIMARY KEY,
            cooperado_id INTEGER,
            pa_id INTEGER,
            produto_id INTEGER,
            data_contratacao TEXT,
            data_vencimento_final TEXT,
            prazo_meses INTEGER,
            taxa_juros_am REAL,
            valor_contratado TEXT,
            valor_parcela REAL,
            garantia TEXT,
            score_risco INTEGER,
            nivel_risco TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE fato_parcela (
            parcela_id INTEGER PRIMARY KEY,
            contrato_id INTEGER,
            numero_parcela INTEGER,
            data_vencimento TEXT,
            valor_parcela REAL,
            data_pagamento TEXT,
            valor_pago REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE meta_mensal (
            mes TEXT,
            pa_id INTEGER,
            meta_saldo REAL,
            meta_volume_concedido REAL,
            teto_inadimplencia_90 REAL
        )
        """
    )

    cur.executemany(
        "INSERT INTO dim_cooperado VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                c["cooperado_id"], c["nome"], c["documento"], c["tipo_pessoa"],
                c["faixa_renda"], c["porte"], c["data_nascimento"], c["telefone"],
                c["email"], c["sexo"], c["cidade"], c["uf"], c["data_associacao"],
            )
            for c in cooperados
        ],
    )
    cur.executemany(
        "INSERT INTO dim_pa VALUES (?,?,?,?,?)",
        [(p["pa_id"], p["nome_pa"], p["cidade"], p["uf"], p["regiao"]) for p in pas],
    )
    cur.executemany(
        "INSERT INTO dim_produto VALUES (?,?,?)",
        [(p["produto_id"], p["nome_produto"], p["categoria"]) for p in produtos],
    )
    cur.executemany(
        "INSERT INTO fato_contrato VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                c["contrato_id"], c["cooperado_id"], c["pa_id"], c["produto_id"],
                c["data_contratacao"], c["data_vencimento_final"], c["prazo_meses"],
                c["taxa_juros_am"], c["valor_contratado"], c["valor_parcela"],
                c["garantia"], c["score_risco"], c["nivel_risco"],
            )
            for c in contratos
        ],
    )
    cur.executemany(
        "INSERT INTO fato_parcela VALUES (?,?,?,?,?,?,?)",
        [
            (
                p["parcela_id"], p["contrato_id"], p["numero_parcela"],
                p["data_vencimento"], p["valor_parcela"], p["data_pagamento"],
                p["valor_pago"],
            )
            for p in parcelas
        ],
    )
    cur.executemany(
        "INSERT INTO meta_mensal VALUES (?,?,?,?,?)",
        [
            (m["mes"], m["pa_id"], m["meta_saldo"], m["meta_volume_concedido"], m["teto_inadimplencia_90"])
            for m in metas
        ],
    )

    conn.commit()
    return conn


def exportar_sql(conn: sqlite3.Connection):
    with open(SQL_PATH, "w", encoding="utf-8") as f:
        for linha in conn.iterdump():
            f.write(f"{linha}\n")


def imprimir_resumo(conn: sqlite3.Connection):
    cur = conn.cursor()
    for tabela in ("dim_cooperado", "dim_pa", "dim_produto", "fato_contrato", "fato_parcela", "meta_mensal"):
        total = cur.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        print(f"{tabela}: {total} linhas")

    duplicados = cur.execute(
        "SELECT COUNT(*) FROM (SELECT cooperado_id FROM dim_cooperado "
        "GROUP BY cooperado_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    print(f"cooperado_id duplicados em dim_cooperado: {duplicados}")

    orfas = cur.execute(
        "SELECT COUNT(*) FROM fato_parcela p "
        "LEFT JOIN fato_contrato c ON p.contrato_id = c.contrato_id "
        "WHERE c.contrato_id IS NULL"
    ).fetchone()[0]
    print(f"parcelas orfas (sem contrato): {orfas}")


def main():
    cooperados = gerar_cooperados()
    pas = gerar_pas()
    produtos = gerar_produtos()
    contratos = gerar_contratos(cooperados)
    parcelas = gerar_parcelas(contratos)
    metas = gerar_metas(pas, contratos, parcelas)

    conn = criar_banco(cooperados, pas, produtos, contratos, parcelas, metas)
    exportar_sql(conn)
    imprimir_resumo(conn)
    conn.close()

    print(f"\nBanco gerado em: {DB_PATH}")
    print(f"SQL exportado em: {SQL_PATH}")


if __name__ == "__main__":
    main()
