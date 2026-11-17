# -*- coding: utf-8 -*-
"""
CONTROLE FINANCEIRO PESSOAL
Projeto Integrador: Laboratório de Programação - Universidade Santo Amaro

Sistema de controle financeiro em terminal, escrito somente com a
biblioteca padrão do Python (3.8 ou superior) e banco de dados SQLite.

Os valores monetários são guardados em CENTAVOS (inteiros) para evitar
erros de arredondamento. As datas são guardadas como AAAA-MM-DD e exibidas
ao usuário como dd/mm/aaaa.

Para executar:  python financas.py
"""

import math
import os
import re
import sqlite3
import sys
from datetime import date

# ---------------------------------------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------------------------------------

# RNF02: o banco fica em um arquivo local, na mesma pasta do programa.
# (A variável de ambiente FINANCAS_DB existe apenas para facilitar testes.)
PASTA = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_BANCO = os.environ.get("FINANCAS_DB") or os.path.join(PASTA, "financas.db")

TIPOS_CONTA = ["Carteira", "Conta corrente", "Poupança", "Investimento", "Outro"]

CATEGORIAS_RECEITA = ["Salário", "Freelance", "Investimentos", "Outras receitas"]
CATEGORIAS_DESPESA = [
    "Alimentação", "Moradia", "Transporte", "Saúde",
    "Educação", "Lazer", "Contas e serviços", "Outras despesas",
]

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

ANO_MIN, ANO_MAX = 1900, 2100

# Limite por lançamento/saldo inicial: R$ 999.999.999,99. Evita estouro do
# inteiro de 64 bits do SQLite com entradas absurdas.
VALOR_MAX = 99_999_999_999

# Apêndice A do projeto: criação das tabelas.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL,
    saldo_inicial INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa')),
    UNIQUE (nome, tipo)
);

CREATE TABLE IF NOT EXISTS lancamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('receita','despesa')),
    conta_id INTEGER NOT NULL,
    categoria_id INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    valor INTEGER NOT NULL CHECK (valor > 0),
    data TEXT NOT NULL,
    FOREIGN KEY (conta_id) REFERENCES contas(id),
    FOREIGN KEY (categoria_id) REFERENCES categorias(id)
);
"""

# RNF06: símbolos com alternativa para terminais sem suporte a Unicode.
def _terminal_aceita(texto):
    codificacao = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        texto.encode(codificacao)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


if _terminal_aceita("█✔✖…"):
    BLOCO, OK, ERRO, AVISO, RETICENCIAS = "█", "✔", "✖", "⚠", "…"
else:
    BLOCO, OK, ERRO, AVISO, RETICENCIAS = "#", "[OK]", "[ERRO]", "[!]", "~"


# ---------------------------------------------------------------------------
# BANCO DE DADOS
# ---------------------------------------------------------------------------

def conectar(caminho=None):
    """Abre a conexão com o SQLite e ativa as chaves estrangeiras."""
    conn = sqlite3.connect(caminho or ARQUIVO_BANCO)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def iniciar_banco(conn):
    """Cria as tabelas e, na primeira utilização, insere as categorias
    padrão e a conta 'Carteira'."""
    conn.executescript(SCHEMA_SQL)

    # user_version = 0 indica banco recém-criado; assim os itens padrão são
    # inseridos uma única vez e não reaparecem depois de excluídos.
    if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
        for nome in CATEGORIAS_RECEITA:
            conn.execute("INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?, 'receita')", (nome,))
        for nome in CATEGORIAS_DESPESA:
            conn.execute("INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?, 'despesa')", (nome,))
        conn.execute(
            "INSERT OR IGNORE INTO contas (nome, tipo, saldo_inicial) VALUES ('Carteira', 'Carteira', 0)"
        )
        conn.execute("PRAGMA user_version = 1")
    conn.commit()


# ---------------------------------------------------------------------------
# UTILITÁRIOS: formatação
# ---------------------------------------------------------------------------

def brl(centavos):
    """Formata centavos como moeda brasileira: 123456 -> 'R$ 1.234,56'."""
    negativo = centavos < 0
    reais, cent = divmod(abs(centavos), 100)
    texto = "R$ {},{:02d}".format("{:,}".format(reais).replace(",", "."), cent)
    return "-" + texto if negativo else texto


def data_br(iso):
    """'2026-11-05' -> '05/11/2026'."""
    ano, mes, dia = iso.split("-")
    return "{}/{}/{}".format(dia, mes, ano)


def nome_mes(ano_mes):
    """'2026-11' -> 'Novembro/2026'."""
    ano, mes = ano_mes.split("-")
    return "{}/{}".format(MESES[int(mes) - 1], ano)


def mes_atual():
    hoje = date.today()
    return "{:04d}-{:02d}".format(hoje.year, hoje.month)


def titulo(texto):
    print("\n" + texto)


def cortar(texto, largura):
    """Corta o texto para caber na coluna, deixando ao menos 1 espaço livre."""
    texto = str(texto)
    return texto if len(texto) < largura else texto[:largura - 1] + RETICENCIAS


def linha_tabela(colunas, celulas):
    """Monta uma linha com colunas de largura fixa.
    colunas: lista de (largura, 'l' ou 'r'); largura 0 = sem preenchimento."""
    partes = []
    for (largura, alin), celula in zip(colunas, celulas):
        celula = str(celula)
        if largura == 0:
            partes.append(celula)
        elif alin == "l":
            partes.append(cortar(celula, largura).ljust(largura))
        else:
            partes.append(celula.rjust(largura))
    return "".join(partes).rstrip()


def tabela(colunas, cabecalho, linhas, rodape=None, largura_sep=None):
    """Imprime cabeçalho, separador, linhas e (opcionalmente) um rodapé já
    formatado. O separador tem a soma das larguras, salvo se largura_sep."""
    sep = "-" * (largura_sep or sum(larg for larg, _ in colunas))
    print(linha_tabela(colunas, cabecalho))
    print(sep)
    for linha in linhas:
        print(linha_tabela(colunas, linha))
    if rodape is not None:
        print(sep)
        print(rodape)


# ---------------------------------------------------------------------------
# UTILITÁRIOS: leitura e validação de entradas (RNF04)
# ---------------------------------------------------------------------------

def ler_texto(pergunta, obrigatorio=True):
    """Lê um texto; se obrigatório, repete até que não seja vazio."""
    while True:
        resposta = input(pergunta).strip()
        if resposta or not obrigatorio:
            return resposta
        print(ERRO, "Este campo é obrigatório.")


def converter_valor(texto, permitir_zero=False):
    """Converte o texto digitado em centavos inteiros.

    Aceita 1234,56 | 1.234,56 | 1234.56 | 1.500 (= mil e quinhentos), com ou
    sem 'R$'. Levanta ValueError se o valor for inválido."""
    t = texto.upper().replace("R$", "").replace(" ", "")
    if not t:
        raise ValueError("valor vazio")
    if t.startswith("-"):
        raise ValueError("valores negativos não são aceitos")

    if "," in t and "." in t:
        # O último separador é o decimal; o outro é separador de milhar.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    elif "." in t and re.fullmatch(r"[0-9]{1,3}(\.[0-9]{3})+", t):
        t = t.replace(".", "")          # '1.500' -> mil e quinhentos

    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?|\.[0-9]+", t):
        raise ValueError("formato inválido")
    numero = float(t)
    if not math.isfinite(numero):
        raise ValueError("valor não finito")
    centavos = int(round(numero * 100))
    if centavos > VALOR_MAX:
        raise ValueError("valor muito grande (máximo R$ 999.999.999,99)")
    if centavos == 0 and not permitir_zero:
        raise ValueError("o valor deve ser maior que zero")
    return centavos


def ler_valor(pergunta, permitir_zero=False):
    while True:
        try:
            return converter_valor(input(pergunta), permitir_zero)
        except ValueError as erro:
            print(ERRO, "Valor inválido ({}). Exemplos: 1234,56 | 1.234,56 | 50".format(erro))


def converter_data(texto):
    """'dd/mm/aaaa' -> 'AAAA-MM-DD'. Levanta ValueError se inválida."""
    m = re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})", texto.strip())
    if not m:
        raise ValueError("use o formato dd/mm/aaaa")
    dia, mes, ano = (int(x) for x in m.groups())
    if not ANO_MIN <= ano <= ANO_MAX:
        raise ValueError("o ano deve estar entre {} e {}".format(ANO_MIN, ANO_MAX))
    return date(ano, mes, dia).isoformat()   # ValueError se a data não existe


def ler_data(pergunta="Data (dd/mm/aaaa, ENTER = hoje): "):
    while True:
        resposta = input(pergunta).strip()
        if not resposta:
            return date.today().isoformat()
        try:
            return converter_data(resposta)
        except ValueError as erro:
            print(ERRO, "Data inválida ({}).".format(erro))


def converter_mes(texto):
    """'mm/aaaa' -> 'AAAA-MM'. Levanta ValueError se inválido."""
    m = re.fullmatch(r"([0-9]{1,2})/([0-9]{4})", texto.strip())
    if not m:
        raise ValueError("use o formato mm/aaaa")
    mes, ano = int(m.group(1)), int(m.group(2))
    if not 1 <= mes <= 12:
        raise ValueError("o mês deve estar entre 1 e 12")
    if not ANO_MIN <= ano <= ANO_MAX:
        raise ValueError("o ano deve estar entre {} e {}".format(ANO_MIN, ANO_MAX))
    return "{:04d}-{:02d}".format(ano, mes)


def ler_mes(pergunta="Mês (mm/aaaa, ENTER = mês atual): "):
    while True:
        resposta = input(pergunta).strip()
        if not resposta:
            return mes_atual()
        try:
            return converter_mes(resposta)
        except ValueError as erro:
            print(ERRO, "Mês inválido ({}).".format(erro))


def ler_ano(pergunta="Ano (aaaa, ENTER = ano atual): "):
    while True:
        resposta = input(pergunta).strip()
        if not resposta:
            return date.today().year
        if re.fullmatch(r"[0-9]{4}", resposta) and ANO_MIN <= int(resposta) <= ANO_MAX:
            return int(resposta)
        print(ERRO, "Ano inválido. Use aaaa, entre {} e {}.".format(ANO_MIN, ANO_MAX))


def escolher_item(ids_validos, pergunta="Escolha o ID (0 = cancelar): "):
    """Só aceita um ID da lista exibida. Retorna o ID, ou None se cancelar."""
    ids_validos = set(ids_validos)
    while True:
        resposta = input(pergunta).strip()
        if resposta == "0":
            return None
        # [0-9] e limite de tamanho: isdigit()/int() aceitam caracteres e
        # tamanhos que causariam erro (ex.: '²' ou milhares de dígitos).
        if re.fullmatch(r"[0-9]{1,9}", resposta) and int(resposta) in ids_validos:
            return int(resposta)
        print(ERRO, "Opção inexistente. Escolha um ID da lista ou 0 para cancelar.")


def confirmar(pergunta):
    while True:
        resposta = input(pergunta + " (s/n): ").strip().lower()
        if resposta in ("s", "sim"):
            return True
        if resposta in ("n", "nao", "não"):
            return False
        print(ERRO, "Responda com 's' ou 'n'.")


def saldo_conta(conn, conta_id):
    """Saldo atual = saldo inicial + receitas - despesas (calculado a cada
    consulta, nunca gravado no banco)."""
    linha = conn.execute(
        """
        SELECT c.saldo_inicial
               + COALESCE(SUM(CASE WHEN l.tipo = 'receita' THEN l.valor
                                   WHEN l.tipo = 'despesa' THEN -l.valor END), 0) AS saldo
          FROM contas c
          LEFT JOIN lancamentos l ON l.conta_id = c.id
         WHERE c.id = ?
        """,
        (conta_id,),
    ).fetchone()
    return linha["saldo"]


# ---------------------------------------------------------------------------
# CONTAS
# ---------------------------------------------------------------------------

def listar_contas(conn):
    """Lista as contas com o saldo atual e o patrimônio total.
    Retorna as contas listadas."""
    contas = conn.execute("SELECT * FROM contas ORDER BY id").fetchall()
    if not contas:
        print("Nenhuma conta cadastrada.")
        return contas
    linhas, total = [], 0
    for c in contas:
        saldo = saldo_conta(conn, c["id"])
        total += saldo
        linhas.append([c["id"], c["nome"], c["tipo"], brl(saldo)])
    tabela([(5, "l"), (24, "l"), (16, "l"), (16, "r")],
           ["ID", "Conta", "Tipo", "Saldo atual"], linhas,
           rodape="{:<45}{:>16}".format("Patrimônio total", brl(total)))
    return contas


def cadastrar_conta(conn):
    titulo("NOVA CONTA")
    nome = ler_texto("Nome da conta: ")
    print("Tipos:")
    for i, tipo in enumerate(TIPOS_CONTA, 1):
        print("  {} - {}".format(i, tipo))
    escolha = escolher_item(range(1, len(TIPOS_CONTA) + 1), "Tipo (0 = cancelar): ")
    if escolha is None:
        print("Cadastro cancelado.")
        return
    saldo = ler_valor("Saldo inicial (ex.: 1500,00): ", permitir_zero=True)
    try:
        conn.execute(
            "INSERT INTO contas (nome, tipo, saldo_inicial) VALUES (?, ?, ?)",
            (nome, TIPOS_CONTA[escolha - 1], saldo),
        )
        conn.commit()
        print(OK, "Conta '{}' cadastrada.".format(nome))
    except sqlite3.IntegrityError:
        print(AVISO, "Já existe uma conta chamada '{}'.".format(nome))


def excluir_conta(conn):
    titulo("EXCLUIR CONTA")
    contas = listar_contas(conn)
    if not contas:
        return
    conta_id = escolher_item([c["id"] for c in contas])
    if conta_id is None:
        return
    qtd = conn.execute("SELECT COUNT(*) FROM lancamentos WHERE conta_id = ?", (conta_id,)).fetchone()[0]
    if qtd:
        print(AVISO, "Não é possível excluir: a conta possui {} lançamento(s) vinculado(s).".format(qtd))
        return
    if confirmar("Confirma a exclusão da conta?"):
        conn.execute("DELETE FROM contas WHERE id = ?", (conta_id,))
        conn.commit()
        print(OK, "Conta excluída.")


def menu_contas(conn):
    while True:
        titulo("=== CONTAS ===\n1 - Cadastrar conta\n2 - Listar contas e saldos\n3 - Excluir conta\n0 - Voltar")
        op = input("Opção: ").strip()
        if op == "1":
            cadastrar_conta(conn)
        elif op == "2":
            listar_contas(conn)
        elif op == "3":
            excluir_conta(conn)
        elif op == "0":
            return
        else:
            print(ERRO, "Opção inválida.")


# ---------------------------------------------------------------------------
# CATEGORIAS
# ---------------------------------------------------------------------------

def listar_categorias(conn, tipo=None):
    """Lista categorias (de um tipo, ou todas). Retorna as listadas."""
    if tipo:
        cats = conn.execute("SELECT * FROM categorias WHERE tipo = ? ORDER BY nome", (tipo,)).fetchall()
    else:
        cats = conn.execute("SELECT * FROM categorias ORDER BY tipo, nome").fetchall()
    if not cats:
        print("Nenhuma categoria cadastrada.")
        return cats
    print()
    tabela([(5, "l"), (24, "l"), (0, "l")], ["ID", "Categoria", "Tipo"],
           [[c["id"], c["nome"], c["tipo"]] for c in cats])
    return cats


def cadastrar_categoria(conn):
    titulo("NOVA CATEGORIA")
    print("Tipo: 1 - receita | 2 - despesa")
    escolha = escolher_item([1, 2], "Tipo (0 = cancelar): ")
    if escolha is None:
        print("Cadastro cancelado.")
        return
    tipo = "receita" if escolha == 1 else "despesa"
    nome = ler_texto("Nome da categoria: ")
    try:
        conn.execute("INSERT INTO categorias (nome, tipo) VALUES (?, ?)", (nome, tipo))
        conn.commit()
        print(OK, "Categoria '{}' ({}) cadastrada.".format(nome, tipo))
    except sqlite3.IntegrityError:
        print(AVISO, "Já existe a categoria '{}' do tipo {}.".format(nome, tipo))


def excluir_categoria(conn):
    titulo("EXCLUIR CATEGORIA")
    cats = listar_categorias(conn)
    if not cats:
        return
    cat_id = escolher_item([c["id"] for c in cats])
    if cat_id is None:
        return
    qtd = conn.execute("SELECT COUNT(*) FROM lancamentos WHERE categoria_id = ?", (cat_id,)).fetchone()[0]
    if qtd:
        print(AVISO, "Não é possível excluir: a categoria possui {} lançamento(s) vinculado(s).".format(qtd))
        return
    if confirmar("Confirma a exclusão da categoria?"):
        conn.execute("DELETE FROM categorias WHERE id = ?", (cat_id,))
        conn.commit()
        print(OK, "Categoria excluída.")


def menu_categorias(conn):
    while True:
        titulo("=== CATEGORIAS ===\n1 - Cadastrar categoria\n2 - Listar categorias\n3 - Excluir categoria\n0 - Voltar")
        op = input("Opção: ").strip()
        if op == "1":
            cadastrar_categoria(conn)
        elif op == "2":
            listar_categorias(conn)
        elif op == "3":
            excluir_categoria(conn)
        elif op == "0":
            return
        else:
            print(ERRO, "Opção inválida.")


# ---------------------------------------------------------------------------
# LANÇAMENTOS (receitas e despesas compartilham as mesmas funções)
# ---------------------------------------------------------------------------

def inserir_lancamento(conn, tipo, conta_id, categoria_id, descricao, valor, data):
    """Grava um lançamento no banco e retorna o saldo resultante da conta."""
    conn.execute(
        "INSERT INTO lancamentos (tipo, conta_id, categoria_id, descricao, valor, data) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tipo, conta_id, categoria_id, descricao, valor, data),
    )
    conn.commit()
    return saldo_conta(conn, conta_id)


def registrar(conn, tipo):
    rotulo = "RECEITA" if tipo == "receita" else "DESPESA"
    titulo("REGISTRAR " + rotulo)

    contas = listar_contas(conn)
    if not contas:
        print(AVISO, "Cadastre uma conta antes de registrar lançamentos.")
        return
    conta_id = escolher_item([c["id"] for c in contas], "Conta (0 = cancelar): ")
    if conta_id is None:
        return

    cats = listar_categorias(conn, tipo)
    if not cats:
        print(AVISO, "Cadastre uma categoria de {} antes.".format(tipo))
        return
    cat_id = escolher_item([c["id"] for c in cats], "Categoria (0 = cancelar): ")
    if cat_id is None:
        return

    descricao = ler_texto("Descrição: ")
    valor = ler_valor("Valor (ex.: 1.234,56): ")
    data = ler_data()

    saldo = inserir_lancamento(conn, tipo, conta_id, cat_id, descricao, valor, data)
    print(OK, "{} registrada: {} - {} em {}.".format(tipo.capitalize(), descricao, brl(valor), data_br(data)))
    # RF11: alerta de saldo negativo.
    if tipo == "despesa" and saldo < 0:
        print(AVISO, "Atenção: a conta ficou com saldo negativo ({}).".format(brl(saldo)))


def listar_lancamentos(conn, tipo, mes=None):
    """Lista os lançamentos de um mês e o total do período.
    Retorna as linhas listadas."""
    if mes is None:
        mes = ler_mes()
    linhas = conn.execute(
        """
        SELECT l.id, l.data, l.descricao, c.nome AS categoria, ct.nome AS conta, l.valor
          FROM lancamentos l
          JOIN categorias c  ON c.id  = l.categoria_id
          JOIN contas     ct ON ct.id = l.conta_id
         WHERE l.tipo = ? AND substr(l.data, 1, 7) = ?
         ORDER BY l.data, l.id
        """,
        (tipo, mes),
    ).fetchall()
    titulo("{} - {}".format(("RECEITAS" if tipo == "receita" else "DESPESAS"), nome_mes(mes)))
    if not linhas:
        print("Nenhum lançamento neste mês.")
        return linhas
    total = sum(l["valor"] for l in linhas)
    tabela(
        [(5, "l"), (12, "l"), (24, "l"), (18, "l"), (18, "l"), (14, "r")],
        ["ID", "Data", "Descrição", "Categoria", "Conta", "Valor"],
        [[l["id"], data_br(l["data"]), l["descricao"], l["categoria"], l["conta"], brl(l["valor"])]
         for l in linhas],
        rodape="{:<77}{:>14}".format("Total", brl(total)),
    )
    return linhas


def excluir_lancamento(conn, tipo):
    titulo("EXCLUIR " + ("RECEITA" if tipo == "receita" else "DESPESA"))
    linhas = listar_lancamentos(conn, tipo)
    if not linhas:
        return
    lanc_id = escolher_item([l["id"] for l in linhas])
    if lanc_id is None:
        return
    if confirmar("Confirma a exclusão do lançamento?"):
        conn.execute("DELETE FROM lancamentos WHERE id = ?", (lanc_id,))
        conn.commit()
        print(OK, "Lançamento excluído.")


def menu_lancamentos(conn, tipo):
    nome = "RECEITAS" if tipo == "receita" else "DESPESAS"
    while True:
        titulo("=== {} ===\n1 - Registrar\n2 - Listar por mês\n3 - Excluir\n0 - Voltar".format(nome))
        op = input("Opção: ").strip()
        if op == "1":
            registrar(conn, tipo)
        elif op == "2":
            listar_lancamentos(conn, tipo)
        elif op == "3":
            excluir_lancamento(conn, tipo)
        elif op == "0":
            return
        else:
            print(ERRO, "Opção inválida.")


# ---------------------------------------------------------------------------
# SALDO MENSAL E RELATÓRIOS
# ---------------------------------------------------------------------------

def totais_do_mes(conn, mes):
    """Retorna (receitas, despesas) do mês, em centavos."""
    linha = conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor END), 0) AS rec,
               COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor END), 0) AS desp
          FROM lancamentos
         WHERE substr(data, 1, 7) = ?
        """,
        (mes,),
    ).fetchone()
    return linha["rec"], linha["desp"]


def saldo_mensal(conn, mes=None):
    if mes is None:
        mes = ler_mes()
    receitas, despesas = totais_do_mes(conn, mes)
    saldo = receitas - despesas
    titulo(nome_mes(mes))
    print("  {:<13}{:>17}".format("Receitas ....", brl(receitas)))
    print("  {:<13}{:>17}".format("Despesas ....", brl(despesas)))
    print("  {:<13}{:>17}".format("Saldo .......", brl(saldo)))
    print()
    if saldo > 0:
        print("Situação: positiva. Sobrou {:.1f}% da receita.".format(saldo / receitas * 100))
    elif saldo < 0:
        print("Situação: negativa. Os gastos superaram a receita em {}.".format(brl(-saldo)))
    else:
        print("Situação: equilibrada (receitas iguais às despesas).")


def relatorio_categorias(conn, tipo, mes=None):
    """Relatório por categoria com percentual e gráfico de barras em texto
    (cada bloco representa cerca de 5% do total)."""
    if mes is None:
        mes = ler_mes()
    linhas = conn.execute(
        """
        SELECT c.nome AS nome, COUNT(*) AS qtd, SUM(l.valor) AS total
          FROM lancamentos l
          JOIN categorias c ON c.id = l.categoria_id
         WHERE l.tipo = ? AND substr(l.data, 1, 7) = ?
         GROUP BY c.id
         ORDER BY total DESC, c.nome
        """,
        (tipo, mes),
    ).fetchall()
    rotulo = "DESPESAS" if tipo == "despesa" else "RECEITAS"
    titulo("{} POR CATEGORIA - {}".format(rotulo, nome_mes(mes)))
    if not linhas:
        print("Nenhum lançamento neste mês.")
        return
    total = sum(l["total"] for l in linhas)
    saida = []
    for l in linhas:
        pct = l["total"] / total * 100
        blocos = max(1, int(round(pct / 5)))
        saida.append([l["nome"], l["qtd"], brl(l["total"]), "{:.1f}%".format(pct), "  " + BLOCO * blocos])
    print()
    tabela([(22, "l"), (4, "r"), (16, "r"), (8, "r"), (0, "l")],
           ["Categoria", "Qtd", "Total", "%", "  Gráfico"], saida,
           rodape="{:<22}{:>4}{:>16}".format("Total", "", brl(total)),
           largura_sep=62)


def extrato_conta(conn, conta_id=None):
    """Lançamentos de uma conta em ordem cronológica, com saldo acumulado."""
    if conta_id is None:
        contas = listar_contas(conn)
        if not contas:
            return
        conta_id = escolher_item([c["id"] for c in contas], "Conta (0 = cancelar): ")
        if conta_id is None:
            return
    conta = conn.execute("SELECT * FROM contas WHERE id = ?", (conta_id,)).fetchone()
    lancs = conn.execute(
        """
        SELECT l.data, l.descricao, c.nome AS categoria, l.tipo, l.valor
          FROM lancamentos l
          JOIN categorias c ON c.id = l.categoria_id
         WHERE l.conta_id = ?
         ORDER BY l.data, l.id
        """,
        (conta_id,),
    ).fetchall()
    print("\nConta: {}  |  Saldo inicial: {}".format(conta["nome"], brl(conta["saldo_inicial"])))
    saldo = conta["saldo_inicial"]
    if not lancs:
        print("Nenhum lançamento nesta conta.")
    else:
        linhas = []
        for l in lancs:
            delta = l["valor"] if l["tipo"] == "receita" else -l["valor"]
            saldo += delta
            linhas.append([data_br(l["data"]), l["descricao"], l["categoria"], brl(delta), brl(saldo)])
        print()
        tabela([(12, "l"), (22, "l"), (16, "l"), (13, "r"), (14, "r")],
               ["Data", "Descrição", "Categoria", "Valor", "Saldo"], linhas)
    print("\nSaldo atual: " + brl(saldo))


def evolucao_anual(conn, ano=None):
    """Receitas, despesas e saldo de cada mês do ano."""
    if ano is None:
        ano = ler_ano()
    dados = {}
    for l in conn.execute(
        """
        SELECT substr(data, 6, 2) AS mes, tipo, SUM(valor) AS total
          FROM lancamentos
         WHERE substr(data, 1, 4) = ?
         GROUP BY mes, tipo
        """,
        ("{:04d}".format(ano),),
    ):
        dados[(int(l["mes"]), l["tipo"])] = l["total"]

    titulo("EVOLUÇÃO MENSAL - {}".format(ano))
    linhas, tot_rec, tot_desp = [], 0, 0
    for m in range(1, 13):
        rec = dados.get((m, "receita"), 0)
        desp = dados.get((m, "despesa"), 0)
        tot_rec += rec
        tot_desp += desp
        linhas.append([MESES[m - 1], brl(rec), brl(desp), brl(rec - desp)])
    print()
    tabela([(12, "l"), (15, "r"), (15, "r"), (15, "r")],
           ["Mês", "Receitas", "Despesas", "Saldo"], linhas,
           rodape="{:<12}{:>15}{:>15}{:>15}".format(
               "Total", brl(tot_rec), brl(tot_desp), brl(tot_rec - tot_desp)))


def menu_relatorios(conn):
    while True:
        titulo(
            "=== RELATÓRIOS ===\n"
            "1 - Despesas por categoria\n"
            "2 - Receitas por categoria\n"
            "3 - Extrato de conta\n"
            "4 - Evolução mensal do ano\n"
            "0 - Voltar"
        )
        op = input("Opção: ").strip()
        if op == "1":
            relatorio_categorias(conn, "despesa")
        elif op == "2":
            relatorio_categorias(conn, "receita")
        elif op == "3":
            extrato_conta(conn)
        elif op == "4":
            evolucao_anual(conn)
        elif op == "0":
            return
        else:
            print(ERRO, "Opção inválida.")


# ---------------------------------------------------------------------------
# DADOS DE EXEMPLO (RF12)
# ---------------------------------------------------------------------------

def popular_exemplo(conn):
    """Cria a conta 'Conta corrente' (saldo inicial R$ 1.500,00) e insere duas
    receitas e seis despesas no mês corrente. Só roda se não houver
    lançamentos, para não misturar dados fictícios com dados reais."""
    if conn.execute("SELECT COUNT(*) FROM lancamentos").fetchone()[0] > 0:
        print(AVISO, "Já existem lançamentos cadastrados; os dados de exemplo não foram inseridos.")
        return False

    conn.execute(
        "INSERT OR IGNORE INTO contas (nome, tipo, saldo_inicial) VALUES ('Conta corrente', 'Conta corrente', 150000)"
    )
    conta_id = conn.execute("SELECT id FROM contas WHERE nome = 'Conta corrente'").fetchone()["id"]

    # Garante a existência das categorias usadas (caso tenham sido excluídas).
    for nome in ("Salário", "Freelance"):
        conn.execute("INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?, 'receita')", (nome,))
    for nome in ("Moradia", "Alimentação", "Transporte", "Lazer", "Saúde"):
        conn.execute("INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?, 'despesa')", (nome,))

    def cat(nome, tipo):
        return conn.execute("SELECT id FROM categorias WHERE nome = ? AND tipo = ?", (nome, tipo)).fetchone()["id"]

    hoje = date.today()
    exemplos = [
        # (tipo, categoria, descrição, valor em centavos, dia do mês)
        ("receita", "Salário", "Salário do mês", 450000, 5),
        ("despesa", "Moradia", "Aluguel", 130000, 6),
        ("despesa", "Alimentação", "Supermercado", 42000, 8),
        ("despesa", "Alimentação", "Almoço e lanches", 18500, 10),
        ("despesa", "Transporte", "Combustível", 25000, 11),
        ("receita", "Freelance", "Projeto de site", 80000, 12),
        ("despesa", "Lazer", "Cinema e jantar", 14000, 14),
        ("despesa", "Saúde", "Farmácia", 9800, 15),
    ]
    for tipo, categoria, descricao, valor, dia in exemplos:
        data = date(hoje.year, hoje.month, dia).isoformat()
        conn.execute(
            "INSERT INTO lancamentos (tipo, conta_id, categoria_id, descricao, valor, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tipo, conta_id, cat(categoria, tipo), descricao, valor, data),
        )
    conn.commit()
    print(OK, "Dados de exemplo inseridos: conta 'Conta corrente', 2 receitas e 6 despesas em {}.".format(
        nome_mes(mes_atual())))
    return True


# ---------------------------------------------------------------------------
# MENU PRINCIPAL
# ---------------------------------------------------------------------------

MENU_PRINCIPAL = """
=========================================
      CONTROLE FINANCEIRO PESSOAL
=========================================
1 - Receitas
2 - Despesas
3 - Contas
4 - Categorias
5 - Saldo mensal
6 - Relatórios
7 - Carregar dados de exemplo
0 - Sair"""


def menu_principal():
    conn = conectar()
    try:
        iniciar_banco(conn)
        while True:
            print(MENU_PRINCIPAL)
            op = input("Opção: ").strip()
            if op == "1":
                menu_lancamentos(conn, "receita")
            elif op == "2":
                menu_lancamentos(conn, "despesa")
            elif op == "3":
                menu_contas(conn)
            elif op == "4":
                menu_categorias(conn)
            elif op == "5":
                saldo_mensal(conn)
            elif op == "6":
                menu_relatorios(conn)
            elif op == "7":
                popular_exemplo(conn)
            elif op == "0":
                break
            else:
                print(ERRO, "Opção inválida.")
    finally:
        conn.close()
    print("\nAté logo!")


def main():
    # Nunca travar por causa da codificação do terminal: caracteres que ele
    # não suporta são substituídos (por '?') em vez de gerar erro.
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        menu_principal()
    except (KeyboardInterrupt, EOFError):
        # Encerramento limpo quando o usuário interrompe com Ctrl+C / Ctrl+D.
        print("\n\nPrograma encerrado pelo usuário.")
    except sqlite3.Error as erro:
        print("\n{} Erro no banco de dados ({}): {}".format(ERRO, ARQUIVO_BANCO, erro))
        sys.exit(1)


if __name__ == "__main__":
    main()
