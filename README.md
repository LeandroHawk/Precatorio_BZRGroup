# Case de conciliação de precatórios

Python 3.10+; limpeza somente com biblioteca padrão. No Windows, se os fusos IANA não estiverem disponíveis, instale `python -m pip install tzdata`.

Na raiz do repositório:

```sh
python limpeza.py --data-referencia 2026-11-25 --saida saida
python -m unittest discover -s tests -v
```

Para outra entrada, use `--entrada caminho/dados`. A saída deve ser uma pasta nova, separada da entrada. Gera `base.json`, `pagamentos_limpos.json` e `relatorio.json`, sem alterar originais. Dinheiro é exportado como texto decimal para preservar centavos. Totais e saldos são do recorte recebido; pendências não são corrigidas por adivinhação.

O diagnóstico, as regras, a prevenção e as dúvidas estão em [Case Python Júnior.md](<case-candidato/Case Python Júnior.md>). O PDF original foi mantido e não inclui as complementações. A implementação offline não se conecta ao banco.

[prevencao.sql](prevencao.sql) cria as tabelas, controles e view propostos, em banco PostgreSQL 14+ vazio. Não execute como migração em produção. Exemplo (com PostgreSQL instalado e conexão configurada):

```sh
psql -v ON_ERROR_STOP=1 -d banco_vazio -f prevencao.sql
psql -v ON_ERROR_STOP=1 -d banco_vazio -f tests/test_prevencao.sql
```

Os testes SQL são transacionais e desfazem seus dados. Os testes Python cobrem centavos, máscara, limite/fuso, duplicatas, versões fora de ordem, versão mais nova inválida, empate divergente, reexecução e preservação dos arquivos.

Validação realizada: sete testes Python aprovados e esquema/testes SQL executados com sucesso em uma instância temporária isolada de PostgreSQL 16, encerrada após a conferência. O ZIP de entrega inclui `.git` e a pasta `saida` de exemplo; para rodar novamente após extraí-lo, escolha outra pasta, por exemplo `--saida saida_nova`.

Uso de IA: o diagnóstico inicial foi escrito por Leandro. Codex foi usado para conferir os arquivos, revisar conclusões, completar limpeza/dúvidas e elaborar Python, SQL e testes. A conferência nesta execução incluiu leitura dos originais (incluindo PDF), cálculos por evento, execução dos testes, comparação dos hashes antes/depois e comparação das saídas de duas execuções. Não houve consulta ao tribunal nem validação jurídica; as hipóteses pendentes estão explicitadas no diagnóstico. O uso de IA não substitui a revisão e a compreensão do código pelo candidato antes da apresentação.
