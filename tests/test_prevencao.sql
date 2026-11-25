-- Execute depois de prevencao.sql em um banco de testes vazio.
BEGIN;
DO $$
DECLARE
    lote BIGINT;
    ente BIGINT;
    prec BIGINT;
    resultado TEXT;
BEGIN
    INSERT INTO importacao(arquivo, sha256) VALUES ('teste.json', repeat('a', 64)) RETURNING id INTO lote;
    INSERT INTO ente_devedor(nome) VALUES ('  Município   de São Paulo  ') RETURNING id INTO ente;
    ASSERT (SELECT chave = 'municipio de sao paulo' FROM ente_devedor WHERE id = ente);
    BEGIN
        INSERT INTO ente_devedor(nome) VALUES ('MUNICIPIO DE SAO PAULO');
        RAISE EXCEPTION 'Aceitou ente duplicado';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO ente_devedor(nome) VALUES ('Uni�o');
        RAISE EXCEPTION 'Aceitou ente danificado';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    INSERT INTO precatorio(numero_processo, ente_id, valor_face, apresentado_em, importacao_id)
    VALUES ('00123451020198260053', ente, 45000, '2025-04-02', lote) RETURNING id INTO prec;
    ASSERT (SELECT prazo_pagamento = '2026-12-31' FROM precatorio WHERE id = prec);
    UPDATE precatorio SET apresentado_em = '2025-04-03' WHERE id = prec;
    ASSERT (SELECT prazo_pagamento = '2027-12-31' FROM precatorio WHERE id = prec);
    UPDATE precatorio SET apresentado_em = '2024-02-29', valor_face = 46000 WHERE id = prec;
    ASSERT (SELECT prazo_pagamento = '2025-12-31' FROM precatorio WHERE id = prec);
    ASSERT (SELECT count(*) = 1 FROM historico_valor_face WHERE precatorio_id = prec
            AND valor_anterior = 45000 AND valor_novo = 46000 AND importacao_id = lote);
    BEGIN
        UPDATE precatorio SET valor_face = -1 WHERE id = prec;
        RAISE EXCEPTION 'Aceitou face negativa';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE precatorio SET numero_processo = 'abc' WHERE id = prec;
        RAISE EXCEPTION 'Aceitou processo inválido';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    resultado := importar_pagamento('teste-1', prec, 'pagamento', 15000, '2025-03-10', '2025-03-10T10:00:00-03:00', lote);
    ASSERT resultado = 'inserido';
    resultado := importar_pagamento('teste-1', prec, 'pagamento', 15000, '2025-03-10', '2025-03-10T10:00:00-03:00', lote);
    ASSERT resultado = 'duplicata';
    resultado := importar_pagamento('teste-1', prec, 'pagamento', 15500, '2025-03-10', '2025-03-11T09:00:00-03:00', lote);
    ASSERT resultado = 'atualizado';
    resultado := importar_pagamento('teste-1', prec, 'pagamento', 15000, '2025-03-10', '2025-03-10T10:00:00-03:00', lote);
    ASSERT resultado = 'versao_antiga';
    ASSERT (SELECT count(*) = 1 FROM pagamento WHERE evento_id = 'teste-1');
    BEGIN
        PERFORM importar_pagamento('teste-1', prec, 'pagamento', 16000, '2025-03-10', '2025-03-11T09:00:00-03:00', lote);
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Aceitou empate divergente';
    EXCEPTION WHEN raise_exception THEN NULL;
    END;
    ASSERT (SELECT valor = 15500 FROM pagamento WHERE evento_id = 'teste-1');

    PERFORM importar_pagamento('teste-2', prec, 'estorno', 5000, '2025-03-12', '2025-03-12T10:00:00-03:00', lote);
    ASSERT (SELECT total_pago = 10500 AND saldo = 35500 FROM saldo_precatorio WHERE id = prec);
    BEGIN
        PERFORM importar_pagamento('teste-3', prec, 'pagamento', -200, '2025-03-12', now(), lote);
        RAISE EXCEPTION 'Aceitou pagamento negativo';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        PERFORM importar_pagamento('teste-4', prec, 'outro', 100, '2025-03-12', now(), lote);
        RAISE EXCEPTION 'Aceitou tipo desconhecido';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    INSERT INTO ocorrencia_importacao(importacao_id, registro, acao, motivo, original)
    VALUES (lote, '3', 'quarentena', 'valor negativo', '{"valor": -200}');
END;
$$;
ROLLBACK;
