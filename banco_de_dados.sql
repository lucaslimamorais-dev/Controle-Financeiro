-- ============================================================================
-- CONTROLE FINANCEIRO PESSOAL - BANCO DE DADOS COMPLETO (SQLite)
-- Projeto Integrador: Laboratório de Programação - Universidade Santo Amaro
--
-- Arquivo único com todo o SQL do projeto, em 4 seções:
--   SEÇÃO 1  Criação das tabelas (Apêndice A do projeto)
--   SEÇÃO 2  Dados iniciais: 12 categorias e a conta Carteira
--   SEÇÃO 3  Dados de exemplo (novembro/2026) - opcional
--   SEÇÃO 4  Consultas usadas pelo sistema (saldos, relatórios, extrato...)
--   SEÇÃO 5  Comandos de escrita (exemplos comentados)
--
-- Como usar:
--   sqlite3 financas.db < banco_de_dados.sql
--       (cria o banco, insere os dados de exemplo e mostra os resultados das consultas)
--   Para um banco VAZIO, apague (ou comente) as seções 3 e 4 antes de executar.
--   Para ver as colunas formatadas:  sqlite3 -header -column financas.db < banco_de_dados.sql
--
-- O programa financas.py cria as tabelas sozinho (mesmo SQL da seção 1); este
-- arquivo serve para montar ou inspecionar o banco sem o Python.
--
-- Valores monetários em CENTAVOS (450000 = R$ 4.500,00). Datas em AAAA-MM-DD.
-- Resultado esperado dos dados de exemplo (Figuras 2 a 7 do projeto):
--   receitas R$ 5.300,00 | despesas R$ 2.393,00 | saldo R$ 2.907,00
--   saldo atual da Conta corrente: R$ 4.407,00
-- ============================================================================

PRAGMA foreign_keys = ON;


-- ============================================================================
-- SEÇÃO 1 - CRIAÇÃO DAS TABELAS (Apêndice A)
-- ============================================================================

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

-- ============================================================================
-- SEÇÃO 2 - DADOS INICIAIS (inseridos pelo programa na primeira execução)
-- ============================================================================

INSERT OR IGNORE INTO categorias (nome, tipo) VALUES
    ('Salário', 'receita'), ('Freelance', 'receita'),
    ('Investimentos', 'receita'), ('Outras receitas', 'receita'),
    ('Alimentação', 'despesa'), ('Moradia', 'despesa'),
    ('Transporte', 'despesa'), ('Saúde', 'despesa'),
    ('Educação', 'despesa'), ('Lazer', 'despesa'),
    ('Contas e serviços', 'despesa'), ('Outras despesas', 'despesa');

INSERT OR IGNORE INTO contas (nome, tipo, saldo_inicial) VALUES ('Carteira', 'Carteira', 0);

-- ============================================================================
-- SEÇÃO 3 - DADOS DE EXEMPLO (opcional - mesmos da opção 7 do programa)
-- ============================================================================

INSERT OR IGNORE INTO contas (nome, tipo, saldo_inicial)
VALUES ('Conta corrente', 'Conta corrente', 150000);

INSERT INTO lancamentos (tipo, conta_id, categoria_id, descricao, valor, data) VALUES
  ('receita', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Salário'     AND tipo = 'receita'),
             'Salário do mês',   450000, '2026-11-05'),
  ('despesa', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Moradia'     AND tipo = 'despesa'),
             'Aluguel',          130000, '2026-11-06'),
  ('despesa', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Alimentação' AND tipo = 'despesa'),
             'Supermercado',      42000, '2026-11-08'),
  ('despesa', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Alimentação' AND tipo = 'despesa'),
             'Almoço e lanches',  18500, '2026-11-10'),
  ('despesa', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Transporte'  AND tipo = 'despesa'),
             'Combustível',       25000, '2026-11-11'),
  ('receita', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Freelance'   AND tipo = 'receita'),
             'Projeto de site',   80000, '2026-11-12'),
  ('despesa', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Lazer'       AND tipo = 'despesa'),
             'Cinema e jantar',   14000, '2026-11-14'),
  ('despesa', (SELECT id FROM contas WHERE nome = 'Conta corrente'),
             (SELECT id FROM categorias WHERE nome = 'Saúde'       AND tipo = 'despesa'),
             'Farmácia',           9800, '2026-11-15');

-- ============================================================================
-- SEÇÃO 4 - CONSULTAS USADAS PELO SISTEMA
-- No programa os valores entram como parâmetros (?), nunca concatenados ao texto.
-- Troque '2026-11' (mês), '2026' (ano) e o id da conta (2) pelos que quiser.
-- ============================================================================

-- ============================================================
-- 1. SALDO DE CADA CONTA E PATRIMÔNIO TOTAL (RF06)
--    saldo atual = saldo inicial + receitas - despesas
--    (o saldo nunca é gravado: é calculado a cada consulta)
-- ============================================================
SELECT c.id, c.nome, c.tipo,
       c.saldo_inicial
         + COALESCE(SUM(CASE WHEN l.tipo = 'receita' THEN  l.valor
                             WHEN l.tipo = 'despesa' THEN -l.valor END), 0) AS saldo_atual
  FROM contas c
  LEFT JOIN lancamentos l ON l.conta_id = c.id
 GROUP BY c.id
 ORDER BY c.id;

SELECT SUM(saldo) AS patrimonio_total
  FROM (SELECT c.saldo_inicial
               + COALESCE(SUM(CASE WHEN l.tipo = 'receita' THEN  l.valor
                                   WHEN l.tipo = 'despesa' THEN -l.valor END), 0) AS saldo
          FROM contas c
          LEFT JOIN lancamentos l ON l.conta_id = c.id
         GROUP BY c.id);

-- ============================================================
-- 2. LISTAR RECEITAS (ou DESPESAS) DE UM MÊS (RF05)
--    troque 'despesa' por 'receita' para listar receitas
-- ============================================================
SELECT l.id, l.data, l.descricao, c.nome AS categoria, ct.nome AS conta, l.valor
  FROM lancamentos l
  JOIN categorias c  ON c.id  = l.categoria_id
  JOIN contas     ct ON ct.id = l.conta_id
 WHERE l.tipo = 'despesa' AND substr(l.data, 1, 7) = '2026-11'
 ORDER BY l.data, l.id;

-- ============================================================
-- 3. SALDO MENSAL: RECEITAS, DESPESAS E SALDO DO MÊS (RF07)
-- ============================================================
SELECT COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor END), 0) AS receitas,
       COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor END), 0) AS despesas,
       COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor END), 0)
         - COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor END), 0) AS saldo
  FROM lancamentos
 WHERE substr(data, 1, 7) = '2026-11';

-- ============================================================
-- 4. RELATÓRIO POR CATEGORIA, COM PERCENTUAL (RF08)
--    troque 'despesa' por 'receita' para o relatório de receitas
-- ============================================================
SELECT c.nome AS categoria,
       COUNT(*)                      AS qtd,
       SUM(l.valor)                  AS total,
       ROUND(SUM(l.valor) * 100.0 /
             (SELECT SUM(valor) FROM lancamentos
               WHERE tipo = 'despesa' AND substr(data, 1, 7) = '2026-11'), 1) AS percentual
  FROM lancamentos l
  JOIN categorias c ON c.id = l.categoria_id
 WHERE l.tipo = 'despesa' AND substr(l.data, 1, 7) = '2026-11'
 GROUP BY c.id
 ORDER BY total DESC, c.nome;

-- ============================================================
-- 5. EXTRATO DE UMA CONTA COM SALDO ACUMULADO (RF09)
--    (o programa calcula o acumulado em Python; aqui, com função de janela,
--     disponível no SQLite 3.25 ou superior)
-- ============================================================
SELECT l.data, l.descricao, c.nome AS categoria,
       CASE WHEN l.tipo = 'receita' THEN l.valor ELSE -l.valor END AS valor,
       ct.saldo_inicial
         + SUM(CASE WHEN l.tipo = 'receita' THEN l.valor ELSE -l.valor END)
             OVER (ORDER BY l.data, l.id) AS saldo_acumulado
  FROM lancamentos l
  JOIN categorias c  ON c.id  = l.categoria_id
  JOIN contas     ct ON ct.id = l.conta_id
 WHERE l.conta_id = 2
 ORDER BY l.data, l.id;

-- ============================================================
-- 6. EVOLUÇÃO MENSAL DO ANO (RF10) - só meses com movimento;
--    o programa completa os meses vazios com zero
-- ============================================================
SELECT substr(data, 6, 2) AS mes,
       COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor END), 0) AS receitas,
       COALESCE(SUM(CASE WHEN tipo = 'despesa' THEN valor END), 0) AS despesas,
       COALESCE(SUM(CASE WHEN tipo = 'receita' THEN valor ELSE -valor END), 0) AS saldo
  FROM lancamentos
 WHERE substr(data, 1, 4) = '2026'
 GROUP BY mes
 ORDER BY mes;

-- ============================================================
-- 7. QUANTOS LANÇAMENTOS BLOQUEIAM A EXCLUSÃO (integridade, seção 4.6)
--    se > 0, o programa não deixa excluir a conta / a categoria
-- ============================================================
SELECT COUNT(*) AS lancamentos_da_conta     FROM lancamentos WHERE conta_id = 2;
SELECT COUNT(*) AS lancamentos_da_categoria FROM lancamentos WHERE categoria_id = 6;

-- ============================================================================
-- SEÇÃO 5 - COMANDOS DE ESCRITA (exemplos, comentados para não alterar o banco)
-- ============================================================================

-- Nova conta:
--   INSERT INTO contas (nome, tipo, saldo_inicial) VALUES ('Poupança', 'Poupança', 0);
-- Nova categoria:
--   INSERT INTO categorias (nome, tipo) VALUES ('Pets', 'despesa');
-- Novo lançamento (R$ 59,90):
--   INSERT INTO lancamentos (tipo, conta_id, categoria_id, descricao, valor, data)
--   VALUES ('despesa', 2, 5, 'Padaria', 5990, '2026-11-17');
-- Excluir lançamento / conta / categoria:
--   DELETE FROM lancamentos WHERE id = 1;
--   DELETE FROM contas      WHERE id = 3;   -- falha se houver lançamentos (chave estrangeira)
--   DELETE FROM categorias  WHERE id = 13;  -- idem
