# Controle Financeiro Pessoal

Projeto Integrador: Laboratório de Programação — Universidade Santo Amaro (2026/2)
Orientador: Prof. Danilo Cardenuto Ferreira

Sistema de controle financeiro em terminal, feito em **Python 3.8+** usando **apenas a
biblioteca padrão** e banco de dados **SQLite**. Funciona offline, sem instalar nada.

## Como executar

```bash
python financas.py        # no Windows também: py financas.py
```

Na primeira execução o arquivo `financas.db` é criado automaticamente na mesma pasta do
programa, com as 12 categorias padrão e a conta *Carteira*. Para ver o sistema funcionando,
escolha a opção **7 - Carregar dados de exemplo**.

## Menu principal

| Opção | Item | Função |
|------:|------|--------|
| 1 | Receitas | Registrar, listar por mês e excluir receitas |
| 2 | Despesas | Registrar, listar por mês e excluir despesas |
| 3 | Contas | Cadastrar, listar (com saldos e patrimônio total) e excluir contas |
| 4 | Categorias | Cadastrar, listar e excluir categorias de receita e despesa |
| 5 | Saldo mensal | Receitas, despesas, saldo e % de sobra do mês |
| 6 | Relatórios | Despesas/receitas por categoria, extrato de conta, evolução anual |
| 7 | Dados de exemplo | Insere lançamentos fictícios (só se não houver lançamentos) |
| 0 | Sair | Encerra o programa |

## Formatos de entrada

- **Valores:** `1234,56` · `1.234,56` · `1234.56` · `1.500` (= mil e quinhentos) · `R$ 50`
- **Datas:** `dd/mm/aaaa` (ENTER = hoje) · **Mês:** `mm/aaaa` (ENTER = mês atual) · **Ano:** `aaaa`

## Estrutura do projeto

```
financas.py             programa completo (interface, regras e acesso ao banco)
banco_de_dados.sql      todo o SQL do projeto: criação das tabelas (Apêndice A), dados
                        iniciais, dados de exemplo, consultas e comandos de escrita
tests/test_financas.py  testes automatizados (unittest)
financas.db             banco SQLite (criado na primeira execução)
```

## Banco de dados

Três tabelas: `contas`, `categorias` e `lancamentos` (receitas e despesas).

- Valores monetários em **centavos inteiros** (sem erros de arredondamento).
- Datas como texto `AAAA-MM-DD`.
- O saldo de uma conta **não é gravado**: é calculado a cada consulta
  (saldo inicial + receitas − despesas).
- Integridade: `NOT NULL`, `UNIQUE`, `CHECK` e chaves estrangeiras (`PRAGMA foreign_keys = ON`).
- Contas e categorias com lançamentos vinculados não podem ser excluídas.
- Todas as consultas usam parâmetros (`?`), nunca concatenação de texto (sem injeção de SQL).

O banco também pode ser montado só com SQL, sem o programa Python:

```bash
sqlite3 -header -column financas.db < banco_de_dados.sql
```

O arquivo cria as tabelas, insere os dados de exemplo e mostra o resultado das consultas.
Para um banco vazio, apague as seções 3 e 4 do arquivo antes de executar.

Para inspecionar o banco: `sqlite3 financas.db` → `.tables`, `SELECT * FROM lancamentos;`

## Testes

```bash
python -m unittest discover -s tests -v
```

## Limitações conhecidas

Sem edição de registros (apenas cadastro e exclusão), sem transferência entre contas, saldo
mensal sem acúmulo dos meses anteriores, um único usuário e sem exportação de relatórios.
