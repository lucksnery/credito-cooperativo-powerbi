"""
Gerador de dados sinteticos - Cooperativa Horizonte Sul (ficticia).

Cria um banco SQLite com 5 tabelas (3 dimensoes + 2 fatos) e exporta o
mesmo conteudo em um arquivo .sql (CREATE TABLE + INSERT), para que o
banco possa ser recriado em qualquer maquina sem depender do .db binario.

Padroes propositalmente plantados nos dados (usados depois no dashboard):
  1. O produto "Credito Pessoal" tem inadimplencia bem acima dos demais.
  2. Dois PAs (postos de atendimento) concentram carteira e atraso.
  3. A inadimplencia piora gradualmente entre abr/2026 e set/2026.
  4. A concessao de contratos tem pico sazonal em nov/dez.
  5. Um grupo pequeno de cooperados concentra grande parte do saldo.

Inconsistencias propositais (para tratamento no Power Query):
  - CPF e telefone em formatos diferentes.
  - Nome, cidade e categoria de produto com caixa alta/baixa misturada
    e espacos extras.
  - Datas de nascimento/associacao em formatos diferentes (ISO, BR).
  - Valores nulos em email, telefone e sexo.
  - cooperado_id duplicado (mesma pessoa recadastrada) - a tabela nao
    tem PRIMARY KEY/UNIQUE em cooperado_id de proposito, para que o
    relacionamento 1:N so funcione depois que o Power Query remover a
    duplicidade.
  - valor_contratado gravado como TEXTO em formato BR ("15.000,50").
  - Parcelas orfas (contrato_id que nao existe em fato_contrato).
  - Parcelas com data_pagamento anterior a data_contratacao do contrato.

A data de corte do cenario e fixa em 30/09/2026: nenhuma data gerada
passa disso para tras no tempo de "hoje" da narrativa, e os numeros do
dashboard nao mudam a cada reabertura do arquivo.
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 42
random.seed(SEED)

DATA_CORTE = date(2026, 9, 30)
INICIO_HISTORICO = date(2023, 10, 1)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "cooperativa_horizonte_sul.db"
SQL_PATH = BASE_DIR / "database" / "cooperativa_horizonte_sul.sql"

N_COOPERADOS = 2000
N_COOPERADOS_DUPLICADOS = 25
N_CONTRATOS = 3000
N_PARCELAS_ORFAS = 50
N_PAGAMENTOS_ANTES_DA_CONTRATACAO = 15

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
CIDADES_UF = [
    ("Vale Verde", "SC"), ("Porto Alto", "SC"), ("Serra Nova", "SC"),
    ("Campo Bello", "SC"), ("Rio Claro do Sul", "SC"), ("Monte Alegre", "SC"),
    ("Santa Fonte", "SC"), ("Barra Funda do Sul", "SC"),
]

PAS = [
    ("PA Centro", "Vale Verde", "SC"),
    ("PA Norte", "Porto Alto", "SC"),
    ("PA Industrial", "Vale Verde", "SC"),
    ("PA Agro", "Campo Bello", "SC"),
    ("PA Sul", "Serra Nova", "SC"),
    ("PA Litoral", "Barra Funda do Sul", "SC"),
    ("PA Centro II", "Monte Alegre", "SC"),
    ("PA Vale", "Santa Fonte", "SC"),
]
# indices (0-based) dos PAs que concentram carteira e atraso
PAS_CONCENTRADOS = {0, 2}

PRODUTOS = [
    ("Credito Pessoal", "pessoal"),
    ("Consignado Publico", "consignado"),
    ("Consignado INSS", "CONSIGNADO"),
    ("Financiamento de Veiculos", "veiculos"),
    ("Capital de Giro PJ", "Empresarial"),
    ("Credito Agro", "agro "),
    ("Cartao Consignado", " Consignado"),
]
PRODUTO_RISCO_ID = 1  # Credito Pessoal (1-based) = produto de inadimplencia alta

random_choice = random.choice


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


def gerar_cpf_fake() -> str:
    """Gera um CPF com formato e digitos verificadores validos (fictício)."""
    base = [random.randint(0, 9) for _ in range(9)]

    def digito(nums):
        soma = sum(n * p for n, p in zip(nums, range(len(nums) + 1, 1, -1)))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = digito(base)
    d2 = digito(base + [d1])
    numeros = base + [d1, d2]
    return "".join(str(n) for n in numeros)


def formatar_cpf(cpf_numerico: str) -> str:
    """Formata o mesmo CPF numerico em estilos diferentes (inconsistencia)."""
    estilo = random.random()
    if estilo < 0.4:
        return f"{cpf_numerico[:3]}.{cpf_numerico[3:6]}.{cpf_numerico[6:9]}-{cpf_numerico[9:]}"
    if estilo < 0.7:
        return cpf_numerico
    return f" {cpf_numerico[:3]}.{cpf_numerico[3:6]}.{cpf_numerico[6:9]}-{cpf_numerico[9:]} "


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
        nome = f"{random.choice(NOMES)} {random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"
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
        email = (
            None
            if random.random() < 0.1
            else f"{nome.split()[0].lower()}.{cooperado_id}@teste.com.br"
        )
        linhas.append(
            {
                "cooperado_id": cooperado_id,
                "nome": aplicar_sujeira_texto(nome),
                "cpf": formatar_cpf(gerar_cpf_fake()),
                "data_nascimento": data_aleatoria_formatada(nascimento),
                "telefone": gerar_telefone(),
                "email": email,
                "sexo": sexo,
                "cidade": aplicar_sujeira_texto(cidade),
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
        {"pa_id": i + 1, "nome_pa": nome, "cidade": cidade, "uf": uf}
        for i, (nome, cidade, uf) in enumerate(PAS)
    ]


def gerar_produtos():
    return [
        {"produto_id": i + 1, "nome_produto": nome, "categoria": categoria}
        for i, (nome, categoria) in enumerate(PRODUTOS)
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


def gerar_contratos(cooperados):
    contratos = []
    cooperados_normais = [c for c in cooperados if not c["vip"]]
    cooperados_vip = [c for c in cooperados if c["vip"]]
    # cooperado_id pode estar duplicado na lista: usar so ids distintos para FK
    ids_normais = list({c["cooperado_id"] for c in cooperados_normais})
    ids_vip = list({c["cooperado_id"] for c in cooperados_vip})

    for contrato_id in range(1, N_CONTRATOS + 1):
        # ~8% dos contratos vao para o grupo VIP, com ticket muito maior
        eh_vip = random.random() < 0.08
        cooperado_id = random.choice(ids_vip) if eh_vip else random.choice(ids_normais)

        pa_idx = random.choices(
            range(len(PAS)),
            weights=[4 if i in PAS_CONCENTRADOS else 1 for i in range(len(PAS))],
        )[0]
        produto_idx = random.randrange(len(PRODUTOS))

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
                "pa_idx": pa_idx,
                "produto_idx": produto_idx,
            }
        )
    return contratos


def fator_tempo_atraso(vencimento: date) -> float:
    """Piora gradual da inadimplencia entre abr/2026 e set/2026."""
    inicio_piora = date(2026, 4, 1)
    fim_piora = date(2026, 9, 30)
    if vencimento < inicio_piora or vencimento > fim_piora:
        return 1.0
    progresso = (vencimento - inicio_piora).days / (fim_piora - inicio_piora).days
    return 1.0 + 2.5 * progresso  # chega a 3.5x no fim do periodo


def gerar_parcelas(contratos):
    parcelas = []
    parcela_id = 1
    base_rate = 0.05

    for contrato in contratos:
        data_contratacao = date.fromisoformat(contrato["data_contratacao"])
        prazo = contrato["prazo_meses"]
        valor_parcela = contrato["valor_parcela"]

        mult_produto = 4.0 if contrato["produto_idx"] == PRODUTO_RISCO_ID - 1 else 1.0
        mult_pa = 2.0 if contrato["pa_idx"] in PAS_CONCENTRADOS else 1.0

        for n in range(1, prazo + 1):
            vencimento = data_contratacao + timedelta(days=30 * n)
            if vencimento > DATA_CORTE + timedelta(days=365 * 3):
                break  # nao gera parcelas absurdamente no futuro

            prob_atraso = min(
                0.95, base_rate * mult_produto * mult_pa * fator_tempo_atraso(vencimento)
            )

            data_pagamento = None
            if vencimento <= DATA_CORTE:
                if random.random() > prob_atraso:
                    # pagou em dia ou com pequeno atraso tolerado
                    data_pagamento = vencimento + timedelta(days=random.randint(-5, 5))
                else:
                    # ficou em atraso; parte quita depois, parte continua aberta
                    if random.random() < 0.4:
                        data_pagamento = vencimento + timedelta(
                            days=random.randint(10, 150)
                        )
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


def criar_banco(cooperados, pas, produtos, contratos, parcelas):
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
            cpf TEXT,
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
            uf TEXT
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
            valor_parcela REAL
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

    cur.executemany(
        "INSERT INTO dim_cooperado VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                c["cooperado_id"], c["nome"], c["cpf"], c["data_nascimento"],
                c["telefone"], c["email"], c["sexo"], c["cidade"], c["uf"],
                c["data_associacao"],
            )
            for c in cooperados
        ],
    )
    cur.executemany(
        "INSERT INTO dim_pa VALUES (?,?,?,?)",
        [(p["pa_id"], p["nome_pa"], p["cidade"], p["uf"]) for p in pas],
    )
    cur.executemany(
        "INSERT INTO dim_produto VALUES (?,?,?)",
        [(p["produto_id"], p["nome_produto"], p["categoria"]) for p in produtos],
    )
    cur.executemany(
        "INSERT INTO fato_contrato VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                c["contrato_id"], c["cooperado_id"], c["pa_id"], c["produto_id"],
                c["data_contratacao"], c["data_vencimento_final"], c["prazo_meses"],
                c["taxa_juros_am"], c["valor_contratado"], c["valor_parcela"],
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

    conn.commit()
    return conn


def exportar_sql(conn: sqlite3.Connection):
    with open(SQL_PATH, "w", encoding="utf-8") as f:
        for linha in conn.iterdump():
            f.write(f"{linha}\n")


def imprimir_resumo(conn: sqlite3.Connection):
    cur = conn.cursor()
    for tabela in ("dim_cooperado", "dim_pa", "dim_produto", "fato_contrato", "fato_parcela"):
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

    conn = criar_banco(cooperados, pas, produtos, contratos, parcelas)
    exportar_sql(conn)
    imprimir_resumo(conn)
    conn.close()

    print(f"\nBanco gerado em: {DB_PATH}")
    print(f"SQL exportado em: {SQL_PATH}")


if __name__ == "__main__":
    main()
