# -*- coding: utf-8 -*-
"""Testes automatizados (apenas biblioteca padrão).

Executar, a partir da pasta do projeto:
    python -m unittest discover -s tests -v
"""
import io
import os
import re
import sqlite3
import sys
import unittest
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import financas as f  # noqa: E402


def banco_novo():
    conn = f.conectar(":memory:")
    f.iniciar_banco(conn)
    return conn


def capturar(func, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(*args, **kwargs)
    return buf.getvalue()


class TestValores(unittest.TestCase):
    def test_formatos_aceitos(self):
        for texto, esperado in [
            ("1234,56", 123456), ("1.234,56", 123456), ("1234.56", 123456),
            ("1.500", 150000), ("R$ 50", 5000), ("0,10", 10), ("1,234.56", 123456),
            ("1.234.567,89", 123456789),
        ]:
            self.assertEqual(f.converter_valor(texto), esperado, texto)

    def test_invalidos(self):
        for texto in ["", "abc", "-10", "0", "0,00", "inf", "nan", "1,2,3", "10 reais"]:
            with self.assertRaises(ValueError, msg=texto):
                f.converter_valor(texto)

    def test_zero_permitido_no_saldo_inicial(self):
        self.assertEqual(f.converter_valor("0", permitir_zero=True), 0)

    def test_brl(self):
        self.assertEqual(f.brl(123456), "R$ 1.234,56")
        self.assertEqual(f.brl(-130000), "-R$ 1.300,00")
        self.assertEqual(f.brl(0), "R$ 0,00")
        self.assertEqual(f.brl(5), "R$ 0,05")


class TestDatas(unittest.TestCase):
    def test_data(self):
        self.assertEqual(f.converter_data("05/11/2026"), "2026-11-05")
        for ruim in ["31/02/2026", "2026-11-05", "05/13/2026", "01/01/1899", "01/01/2101", "x"]:
            with self.assertRaises(ValueError, msg=ruim):
                f.converter_data(ruim)

    def test_mes(self):
        self.assertEqual(f.converter_mes("11/2026"), "2026-11")
        self.assertEqual(f.converter_mes("1/2026"), "2026-01")
        for ruim in ["13/2026", "00/2026", "11/1800", "2026", "ab/cdef"]:
            with self.assertRaises(ValueError, msg=ruim):
                f.converter_mes(ruim)


class TestBanco(unittest.TestCase):
    def test_dados_iniciais(self):
        conn = banco_novo()
        n = lambda t: conn.execute("SELECT COUNT(*) FROM categorias WHERE tipo=?", (t,)).fetchone()[0]
        self.assertEqual(n("receita"), 4)
        self.assertEqual(n("despesa"), 8)
        self.assertEqual(conn.execute("SELECT nome FROM contas").fetchall()[0]["nome"], "Carteira")

    def test_inicializacao_repetida_nao_duplica_nem_recria(self):
        conn = banco_novo()
        conn.execute("DELETE FROM contas WHERE nome='Carteira'")
        conn.commit()
        f.iniciar_banco(conn)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0], 12)

    def test_restricoes(self):
        conn = banco_novo()
        with self.assertRaises(sqlite3.IntegrityError):   # valor > 0
            conn.execute("INSERT INTO lancamentos (tipo,conta_id,categoria_id,descricao,valor,data) "
                         "VALUES ('despesa',1,5,'x',0,'2026-01-01')")
        with self.assertRaises(sqlite3.IntegrityError):   # tipo inválido
            conn.execute("INSERT INTO categorias (nome,tipo) VALUES ('X','outro')")
        with self.assertRaises(sqlite3.IntegrityError):   # chave estrangeira
            conn.execute("INSERT INTO lancamentos (tipo,conta_id,categoria_id,descricao,valor,data) "
                         "VALUES ('despesa',99,5,'x',100,'2026-01-01')")
        with self.assertRaises(sqlite3.IntegrityError):   # conta duplicada
            conn.execute("INSERT INTO contas (nome,tipo) VALUES ('Carteira','Carteira')")

    def test_schema_sql_igual_ao_codigo(self):
        caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "banco_de_dados.sql")
        with open(caminho, encoding="utf-8") as arq:
            sql = arq.read()
        norm = lambda s: re.sub(r"\s+", " ", s).strip()
        for bloco in f.SCHEMA_SQL.strip().split(";"):
            if bloco.strip():
                self.assertIn(norm(bloco), norm(sql))


class TestExemploERelatorios(unittest.TestCase):
    def setUp(self):
        self.conn = banco_novo()
        capturar(f.popular_exemplo, self.conn)
        self.mes = f.mes_atual()

    def test_totais_conforme_documento(self):
        rec, desp = f.totais_do_mes(self.conn, self.mes)
        self.assertEqual((rec, desp), (530000, 239300))

    def test_saldo_conta_corrente_e_patrimonio(self):
        cid = self.conn.execute("SELECT id FROM contas WHERE nome='Conta corrente'").fetchone()["id"]
        self.assertEqual(f.saldo_conta(self.conn, cid), 440700)

    def test_saldo_mensal(self):
        saida = capturar(f.saldo_mensal, self.conn, self.mes)
        self.assertIn("R$ 5.300,00", saida)
        self.assertIn("R$ 2.393,00", saida)
        self.assertIn("R$ 2.907,00", saida)
        self.assertIn("Sobrou 54.8% da receita", saida)

    def test_relatorio_despesas(self):
        saida = capturar(f.relatorio_categorias, self.conn, "despesa", self.mes)
        linhas = [l for l in saida.splitlines() if l.strip()]
        corpo = [l for l in linhas if any(c in l for c in ("Moradia", "Alimentação", "Transporte", "Lazer", "Saúde"))]
        self.assertEqual([l.split()[0] for l in corpo], ["Moradia", "Alimentação", "Transporte", "Lazer", "Saúde"])
        self.assertIn("54.3%", saida)
        self.assertIn("25.3%", saida)
        self.assertEqual(corpo[0].count(f.BLOCO), 11)
        self.assertEqual(corpo[-1].count(f.BLOCO), 1)

    def test_relatorio_receitas(self):
        saida = capturar(f.relatorio_categorias, self.conn, "receita", self.mes)
        self.assertIn("84.9%", saida)
        self.assertIn("15.1%", saida)

    def test_extrato_saldo_acumulado(self):
        cid = self.conn.execute("SELECT id FROM contas WHERE nome='Conta corrente'").fetchone()["id"]
        saida = capturar(f.extrato_conta, self.conn, cid)
        self.assertIn("Saldo inicial: R$ 1.500,00", saida)
        self.assertIn("R$ 6.000,00", saida)
        self.assertIn("-R$ 1.300,00", saida)
        self.assertIn("Saldo atual: R$ 4.407,00", saida)

    def test_evolucao_anual(self):
        saida = capturar(f.evolucao_anual, self.conn, date.today().year)
        total = [l for l in saida.splitlines() if l.startswith("Total")][0]
        self.assertIn("R$ 5.300,00", total)
        self.assertIn("R$ 2.393,00", total)
        self.assertIn("R$ 2.907,00", total)
        self.assertEqual(len([l for l in saida.splitlines() if l.startswith("Janeiro")]), 1)

    def test_exemplo_so_roda_uma_vez(self):
        capturar(f.popular_exemplo, self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM lancamentos").fetchone()[0], 8)

    def test_listagem_de_lancamentos(self):
        saida = capturar(f.listar_lancamentos, self.conn, "despesa", self.mes)
        self.assertIn("Aluguel", saida)
        self.assertIn("R$ 2.393,00", saida)


class TestRegrasDeNegocio(unittest.TestCase):
    def test_alerta_de_saldo_negativo(self):
        conn = banco_novo()
        # Carteira (id 1) tem saldo 0; uma despesa a deixa negativa.
        saldo = f.inserir_lancamento(conn, "despesa", 1, 5, "Teste", 1000, "2026-11-01")
        self.assertEqual(saldo, -1000)

    def test_exclusao_bloqueada_com_lancamentos(self):
        conn = banco_novo()
        f.inserir_lancamento(conn, "despesa", 1, 5, "Teste", 1000, "2026-11-01")
        respostas = iter(["1"])
        original = f.input if hasattr(f, "input") else None
        f.input = lambda _="": next(respostas)
        try:
            saida = capturar(f.excluir_conta, conn)
        finally:
            if original is None:
                del f.input
        self.assertIn("1 lançamento(s) vinculado(s)", saida)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0], 1)

    def test_injecao_sql_e_tratada_como_texto(self):
        conn = banco_novo()
        nome = "x'); DROP TABLE contas;--"
        conn.execute("INSERT INTO contas (nome, tipo) VALUES (?, 'Outro')", (nome,))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0], 2)


class TestRobustez(unittest.TestCase):
    """Regressões de erros encontrados em testes de estresse."""

    def test_valor_gigante_e_recusado(self):
        for texto in ["99999999999999999999", "1.000.000.000,00", "9" * 400]:
            with self.assertRaises(ValueError, msg=texto):
                f.converter_valor(texto)
        self.assertEqual(f.converter_valor("999.999.999,99"), f.VALOR_MAX)

    def test_digitos_nao_ascii_sao_recusados(self):
        with self.assertRaises(ValueError):
            f.converter_valor("١٢٣")

    def _escolher(self, entrada):
        respostas = iter([entrada, "0"])
        f.input = lambda _="": next(respostas)
        try:
            return capturar(f.escolher_item, [1, 2])
        finally:
            del f.input

    def test_escolher_item_nao_quebra_com_caracteres_estranhos(self):
        for entrada in ["²", "١", "9" * 5000, "1.5", "-1", " "]:
            self.assertIn("inexistente", self._escolher(entrada), repr(entrada)[:20])


class TestLayoutDoDocumento(unittest.TestCase):
    """As linhas abaixo são idênticas às Figuras 2 a 7 do documento."""

    def setUp(self):
        self.conn = banco_novo()
        capturar(f.popular_exemplo, self.conn)
        self.mes = f.mes_atual()

    def linhas(self, func, *args):
        return capturar(func, self.conn, *args).split("\n")

    def test_figura_2_saldo_mensal(self):
        saida = self.linhas(f.saldo_mensal, self.mes)
        for esperado in ["  Receitas ....      R$ 5.300,00",
                         "  Despesas ....      R$ 2.393,00",
                         "  Saldo .......      R$ 2.907,00",
                         "Situação: positiva. Sobrou 54.8% da receita."]:
            self.assertIn(esperado, saida)

    def test_figura_3_despesas_por_categoria(self):
        saida = self.linhas(f.relatorio_categorias, "despesa", self.mes)
        for esperado in [
            "Categoria              Qtd           Total       %  Gráfico",
            "-" * 62,
            "Moradia                  1     R$ 1.300,00   54.3%  ███████████",
            "Alimentação              2       R$ 605,00   25.3%  █████",
            "Saúde                    1        R$ 98,00    4.1%  █",
            "Total                          R$ 2.393,00",
        ]:
            self.assertIn(esperado, saida)

    def test_figura_5_extrato(self):
        cid = self.conn.execute("SELECT id FROM contas WHERE nome='Conta corrente'").fetchone()["id"]
        saida = self.linhas(f.extrato_conta, cid)
        for esperado in [
            "Conta: Conta corrente  |  Saldo inicial: R$ 1.500,00",
            "Data        Descrição             Categoria               Valor         Saldo",
            "-" * 77,
            "06/11/2026  Aluguel               Moradia          -R$ 1.300,00   R$ 4.700,00",
            "15/11/2026  Farmácia              Saúde               -R$ 98,00   R$ 4.407,00",
            "Saldo atual: R$ 4.407,00",
        ]:
            self.assertIn(esperado, saida)

    def test_figura_6_contas(self):
        saida = self.linhas(f.listar_contas)
        for esperado in [
            "ID   Conta                   Tipo                 Saldo atual",
            "2    Conta corrente          Conta corrente       R$ 4.407,00",
            "Patrimônio total                                  R$ 4.407,00",
        ]:
            self.assertIn(esperado, saida)

    def test_figura_7_evolucao(self):
        saida = self.linhas(f.evolucao_anual, date.today().year)
        for esperado in [
            "Mês                Receitas       Despesas          Saldo",
            "Novembro        R$ 5.300,00    R$ 2.393,00    R$ 2.907,00",
            "Total           R$ 5.300,00    R$ 2.393,00    R$ 2.907,00",
        ]:
            self.assertIn(esperado, saida)

    def test_texto_longo_e_cortado_sem_desalinhar(self):
        f.inserir_lancamento(self.conn, "despesa", 1, 5, "D" * 80, 100, self.mes + "-20")
        saida = self.linhas(f.listar_lancamentos, "despesa", self.mes)
        linha = [l for l in saida if "DDDD" in l][0]
        self.assertLessEqual(len(linha), 91)


class TestArquivoSQL(unittest.TestCase):
    """O banco_de_dados.sql deve funcionar sozinho e dar os mesmos números do programa."""
    RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def secoes(self):
        """Divide o arquivo nas seções 'SEÇÃO n' -> {n: texto}."""
        with open(os.path.join(self.RAIZ, "banco_de_dados.sql"), encoding="utf-8") as arq:
            texto = arq.read()
        partes = re.split(r"^-- SEÇÃO (\d) - .*$", texto, flags=re.M)
        return {int(partes[k]): partes[k + 1] for k in range(1, len(partes), 2)}

    def sem_comentarios(self, sql):
        return "\n".join(l for l in sql.split("\n") if not l.strip().startswith("--"))

    def banco(self):
        sec = self.secoes()
        conn = f.conectar(":memory:")
        for n in (1, 2, 3):
            conn.executescript(sec[n])
        return conn

    def test_tem_as_cinco_secoes(self):
        self.assertEqual(sorted(self.secoes()), [1, 2, 3, 4, 5])

    def test_arquivo_completo_executa_do_inicio_ao_fim(self):
        with open(os.path.join(self.RAIZ, "banco_de_dados.sql"), encoding="utf-8") as arq:
            conn = sqlite3.connect(":memory:")
            conn.executescript(arq.read())
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM lancamentos").fetchone()[0], 8)

    def test_scripts_montam_o_banco_do_documento(self):
        conn = self.banco()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0], 12)
        self.assertEqual(f.totais_do_mes(conn, "2026-11"), (530000, 239300))
        cid = conn.execute("SELECT id FROM contas WHERE nome='Conta corrente'").fetchone()[0]
        self.assertEqual(f.saldo_conta(conn, cid), 440700)

    def test_todas_as_consultas_executam(self):
        conn = self.banco()
        sql = self.sem_comentarios(self.secoes()[4])
        selects = [s.strip() for s in sql.split(";") if s.strip().upper().startswith("SELECT")]
        self.assertGreaterEqual(len(selects), 9)
        for stmt in selects:
            conn.execute(stmt).fetchall()

    def test_consulta_de_extrato_termina_no_saldo_atual(self):
        conn = self.banco()
        sql = self.sem_comentarios(self.secoes()[4])
        extrato = [s for s in sql.split(";") if "saldo_acumulado" in s][0]
        linhas = conn.execute(extrato).fetchall()
        self.assertEqual(linhas[-1]["saldo_acumulado"], 440700)

    def test_secao_de_escrita_nao_altera_o_banco(self):
        sql = self.sem_comentarios(self.secoes()[5])
        self.assertEqual(sql.strip(), "")

    def test_programa_aproveita_banco_criado_por_sql(self):
        conn = self.banco()
        f.iniciar_banco(conn)                      # não pode duplicar nada
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0], 12)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM contas").fetchone()[0], 2)
        self.assertIn("Já existem lançamentos", capturar(f.popular_exemplo, conn))


if __name__ == "__main__":
    unittest.main()
