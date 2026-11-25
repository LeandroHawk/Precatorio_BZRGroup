import hashlib
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from limpeza import limpar, dinheiro, processo, data_local, prazo


DADOS = Path(__file__).resolve().parents[1] / 'case-candidato' / 'dados'


class RegrasTest(unittest.TestCase):
    def test_processo_preserva_zeros_e_rejeita_lixo(self):
        self.assertEqual(processo('0023456-21.2020.8.26.0053'), '00234562120208260053')
        self.assertEqual(processo('00234562120208260053'), '00234562120208260053')
        for invalido in ('', 'abc00234562120208260053', '0023456212020826005'):
            with self.assertRaises(ValueError):
                processo(invalido)

    def test_dinheiro_exato_e_valores_invalidos(self):
        self.assertEqual(dinheiro('2.500,50'), Decimal('2500.50'))
        self.assertEqual(dinheiro(Decimal('15000.0')), Decimal('15000.00'))
        for invalido in (None, -200, 0, 'NaN', 'Infinity', '1.234', '1,234', '12.34,56'):
            with self.assertRaises(ValueError):
                dinheiro(invalido)

    def test_limite_inclusivo_fuso_e_ano_bissexto(self):
        self.assertEqual(prazo(date(2025, 4, 2)), date(2026, 12, 31))
        self.assertEqual(prazo(date(2025, 4, 3)), date(2027, 12, 31))
        self.assertEqual(data_local('2025-04-03T01:00:00Z'), date(2025, 4, 2))
        self.assertEqual(data_local('2025-04-02T23:30:00-03:00'), date(2025, 4, 2))
        self.assertEqual(prazo(data_local('2024-02-29')), date(2025, 12, 31))
        with self.assertRaises(ValueError):
            data_local('2025-04-03T01:00:00')


class IntegracaoTest(unittest.TestCase):
    def executar(self, alteracao=None):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        raiz = Path(pasta.name)
        entrada = raiz / 'entrada'
        entrada.mkdir()
        for arquivo in DADOS.iterdir():
            (entrada / arquivo.name).write_bytes(arquivo.read_bytes())
        if alteracao:
            caminho = entrada / 'pagamentos.json'
            eventos = json.loads(caminho.read_text(encoding='utf-8'))
            alteracao(eventos)
            caminho.write_text(json.dumps(eventos), encoding='utf-8')
        return entrada, raiz

    def test_recorte_reexecucao_e_originais(self):
        entrada, raiz = self.executar()
        antes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in entrada.iterdir()}
        base, eventos, relatorio = limpar(entrada, raiz / 'saida1', date(2026, 11, 25))
        limpar(entrada, raiz / 'saida2', date(2026, 11, 25))
        for nome in ('base.json', 'pagamentos_limpos.json', 'relatorio.json'):
            self.assertEqual((raiz / 'saida1' / nome).read_bytes(), (raiz / 'saida2' / nome).read_bytes())
        self.assertEqual(antes, relatorio['sha256_entradas'])
        self.assertEqual(antes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in entrada.iterdir()})
        self.assertEqual(len(eventos), 8)
        self.assertEqual(len(base), 6)
        self.assertEqual([r['total_pago_observado'] for r in base],
                         list(map(Decimal, ['18000.50', '9200', '0', '3000', '0', '4000'])))
        self.assertIsNone(base[4]['valor_face'])  # Só existe no hub.
        self.assertIsNone(base[0]['ente_devedor'])  # Não inventar nome corrompido.
        self.assertEqual(base[0]['prazo_pagamento'], date(2026, 12, 31))
        self.assertTrue(base[2]['vencido_no_recorte'])
        self.assertTrue(base[5]['vencido_no_recorte'])
        self.assertEqual([e['evento_id'] for e in eventos].count('ev-002'), 1)
        acoes = [o for o in relatorio['ocorrencias'] if o['arquivo'] == 'pagamentos.json']
        self.assertEqual(len(acoes), 13)  # Cada registro recebe uma decisão.
        self.assertEqual(sum(o['acao'] == 'quarentena' for o in acoes), 3)
        with self.assertRaises(FileExistsError):
            limpar(entrada, raiz / 'saida1', date(2026, 11, 25))
        with self.assertRaises(ValueError):
            limpar(entrada, entrada / 'saida', date(2026, 11, 25))

    def test_versao_antiga_nao_reaparece_quando_nova_e_invalida(self):
        def alterar(eventos):
            eventos[8]['valor'] = None
        entrada, raiz = self.executar(alterar)
        _, eventos, relatorio = limpar(entrada, raiz / 'saida', date(2026, 11, 25))
        self.assertNotIn('ev-001', [e['evento_id'] for e in eventos])
        self.assertEqual(sum(o['acao'] == 'quarentena' and o['original'] and
                             o['original'].get('evento_id') == 'ev-001'
                             for o in relatorio['ocorrencias']), 2)

    def test_empate_conflitante_nao_escolhe_pela_ordem(self):
        def alterar(eventos):
            eventos[8]['atualizado_em'] = eventos[0]['atualizado_em']
        entrada, raiz = self.executar(alterar)
        _, eventos, _ = limpar(entrada, raiz / 'saida', date(2026, 11, 25))
        self.assertNotIn('ev-001', [e['evento_id'] for e in eventos])

    def test_versoes_fora_de_ordem(self):
        entrada, raiz = self.executar(lambda eventos: eventos.reverse())
        base, _, _ = limpar(entrada, raiz / 'saida', date(2026, 11, 25))
        self.assertEqual(base[0]['total_pago_observado'], Decimal('18000.50'))


if __name__ == '__main__':
    unittest.main()
