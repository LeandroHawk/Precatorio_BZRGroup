-- PostgreSQL 14+. Execute em um banco vazio; não é migração do schema original.
-- Somente cadastros confirmados entram nestas tabelas. Pendências ficam no log.
BEGIN;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE importacao (
    id BIGSERIAL PRIMARY KEY,
    arquivo TEXT NOT NULL CHECK (btrim(arquivo) <> ''),
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (arquivo, sha256)
);

CREATE TABLE ocorrencia_importacao (
    id BIGSERIAL PRIMARY KEY,
    importacao_id BIGINT NOT NULL REFERENCES importacao(id),
    registro TEXT NOT NULL,
    acao TEXT NOT NULL CHECK (acao IN ('aceito', 'normalizado', 'corrigido', 'descartado', 'quarentena', 'duvida')),
    motivo TEXT NOT NULL CHECK (btrim(motivo) <> ''),
    original JSONB,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ente_devedor (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT NOT NULL CHECK (btrim(nome) <> '' AND position('�' IN nome) = 0),
    chave TEXT NOT NULL UNIQUE
);

CREATE FUNCTION padronizar_ente() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.nome := btrim(regexp_replace(NEW.nome, '\s+', ' ', 'g'));
    NEW.chave := lower(unaccent(NEW.nome));
    RETURN NEW;
END;
$$;
CREATE TRIGGER ente_padronizado BEFORE INSERT OR UPDATE ON ente_devedor
FOR EACH ROW EXECUTE FUNCTION padronizar_ente();

CREATE TABLE precatorio (
    id BIGSERIAL PRIMARY KEY,
    numero_processo TEXT NOT NULL UNIQUE CHECK (numero_processo ~ '^[0-9]{20}$'),
    ente_id BIGINT NOT NULL REFERENCES ente_devedor(id),
    valor_face NUMERIC(15,2) NOT NULL CHECK (valor_face > 0 AND valor_face <> 'NaN'::numeric),
    -- Data civil de Brasília, convertida pelo importador antes da gravação.
    apresentado_em DATE NOT NULL,
    -- Regra fornecida pelo enunciado: 2 de abril é inclusivo.
    prazo_pagamento DATE GENERATED ALWAYS AS (
        make_date(extract(year FROM apresentado_em)::int +
            CASE WHEN extract(month FROM apresentado_em) < 4 OR
                (extract(month FROM apresentado_em) = 4 AND extract(day FROM apresentado_em) <= 2)
            THEN 1 ELSE 2 END, 12, 31)
    ) STORED,
    importacao_id BIGINT NOT NULL REFERENCES importacao(id)
);

CREATE TABLE historico_valor_face (
    id BIGSERIAL PRIMARY KEY,
    precatorio_id BIGINT NOT NULL REFERENCES precatorio(id),
    valor_anterior NUMERIC(15,2) NOT NULL,
    valor_novo NUMERIC(15,2) NOT NULL,
    importacao_id BIGINT NOT NULL REFERENCES importacao(id),
    alterado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE FUNCTION registrar_valor_face() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.valor_face IS DISTINCT FROM NEW.valor_face THEN
        INSERT INTO historico_valor_face(precatorio_id, valor_anterior, valor_novo, importacao_id)
        VALUES (NEW.id, OLD.valor_face, NEW.valor_face, NEW.importacao_id);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER valor_face_auditado AFTER UPDATE ON precatorio
FOR EACH ROW EXECUTE FUNCTION registrar_valor_face();

CREATE TABLE pagamento (
    id BIGSERIAL PRIMARY KEY,
    precatorio_id BIGINT NOT NULL REFERENCES precatorio(id),
    evento_id TEXT NOT NULL UNIQUE CHECK (btrim(evento_id) <> ''),
    tipo TEXT NOT NULL CHECK (tipo IN ('pagamento', 'estorno')),
    valor NUMERIC(15,2) NOT NULL CHECK (valor > 0 AND valor <> 'NaN'::numeric),
    pago_em DATE NOT NULL,
    atualizado_em TIMESTAMPTZ NOT NULL,
    importacao_id BIGINT NOT NULL REFERENCES importacao(id),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX pagamento_precatorio_idx ON pagamento(precatorio_id);

-- Uma linha por evento. Serializa correções concorrentes do mesmo evento.
-- Empate divergente gera erro: importador deve registrar quarentena em outra
-- transação após rollback (ou usar SAVEPOINT para preservar o log do lote).
CREATE FUNCTION importar_pagamento(
    p_evento TEXT, p_precatorio BIGINT, p_tipo TEXT, p_valor NUMERIC,
    p_pago_em DATE, p_atualizado_em TIMESTAMPTZ, p_importacao BIGINT
) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE
    existente pagamento%ROWTYPE;
BEGIN
    INSERT INTO pagamento(evento_id, precatorio_id, tipo, valor, pago_em, atualizado_em, importacao_id)
    VALUES (p_evento, p_precatorio, p_tipo, p_valor, p_pago_em, p_atualizado_em, p_importacao)
    ON CONFLICT (evento_id) DO NOTHING;
    IF FOUND THEN RETURN 'inserido'; END IF;

    SELECT * INTO existente FROM pagamento WHERE evento_id = p_evento FOR UPDATE;
    IF p_atualizado_em < existente.atualizado_em THEN RETURN 'versao_antiga'; END IF;
    IF p_atualizado_em = existente.atualizado_em THEN
        IF ROW(p_precatorio, p_tipo, p_valor, p_pago_em) IS DISTINCT FROM
           ROW(existente.precatorio_id, existente.tipo, existente.valor, existente.pago_em) THEN
            RAISE EXCEPTION 'Evento % tem versões conflitantes no mesmo horário', p_evento;
        END IF;
        RETURN 'duplicata';
    END IF;
    UPDATE pagamento SET precatorio_id = p_precatorio, tipo = p_tipo, valor = p_valor,
        pago_em = p_pago_em, atualizado_em = p_atualizado_em, importacao_id = p_importacao
    WHERE evento_id = p_evento;
    RETURN 'atualizado';
END;
$$;

-- O total é derivado; não há contador acumulado para duplicar ao reexecutar.
-- Só representa todo o histórico se a operação tiver validado sua cobertura.
CREATE VIEW saldo_precatorio AS
SELECT p.id, p.numero_processo, p.ente_id, p.valor_face,
       p.apresentado_em, p.prazo_pagamento,
       coalesce(sum(CASE WHEN e.tipo = 'pagamento' THEN e.valor ELSE -e.valor END), 0) AS total_pago,
       p.valor_face - coalesce(sum(CASE WHEN e.tipo = 'pagamento' THEN e.valor ELSE -e.valor END), 0) AS saldo
FROM precatorio p LEFT JOIN pagamento e ON e.precatorio_id = p.id
GROUP BY p.id;
COMMIT;
