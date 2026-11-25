# Case Python Júnior

Análise iniciada manualmente por Leandro e revisada com os arquivos fornecidos. As capturas originais foram preservadas ao final. Foram lidos os três Markdown originais, o PDF, os quatro arquivos de dados e o `schema.sql`. O PDF é uma versão das observações iniciais; este Markdown contém a análise completada.

## Diagnóstico

Os itens estão em ordem de impacto. As referências de CSV contam o cabeçalho como linha 1; as de JSON indicam a posição do objeto no array, começando em 1. As hipóteses sobre o importador se baseiam no fluxo do `ENUNCIADO.md`, pois seu código não foi fornecido. Os prazos seguem exclusivamente a regra do case, sem afirmar sua aplicação jurídica fora dele.

### 1. Total pago sujeito a duplicação e correções somadas como novos pagamentos

**Evidência:** `dados/pagamentos.json`, registros 2 e 4, repetem `ev-002` integralmente. Os registros 1 e 9 são versões de `ev-001`: R$ 15.000,00 em 10/03 e R$ 15.500,00 em 11/03, conforme `atualizado_em`. O fluxo soma cada registro e permite repetir a importação após falha (`ENUNCIADO.md`, linhas 16 e 19). O banco não impõe unicidade de `evento_id` nem guarda `atualizado_em` (`schema.sql`, linhas 8–16).

**Impacto:** se os formatos forem lidos, a soma bruta do processo 0012345 é R$ 35.501,00; usando uma vez cada evento e a versão mais recente, é R$ 18.000,50. A diferença é R$ 17.500,50 neste arquivo; novas execuções podem ampliar o erro. Não há exportação do total pago para provar quanto foi efetivamente gravado em produção.

**Relação:** a soma incremental sem controle de identidade/versão e sem transação é causa; o total inflado e a falsa impressão de quitação são consequências. O significado de versão precisa ser confirmado com o tribunal.

### 2. Estorno pode aumentar o pago; registros inválidos desaparecem sem aviso

**Evidência:** `pagamentos.json`, registros 7 e 8: pagamento `ev-006` e estorno `ev-007`, ambos de R$ 5.000,00 no processo 0034567. Registros 5 (`ev-004`, valor nulo), 11 (`ev-009`, pagamento de −200) e 12 (`ev-010`, processo vazio) são inválidos sob o contrato atual. `ENUNCIADO.md`, linhas 16 e 19, descreve soma e descarte silencioso. O `schema.sql`, linha 13, recusaria os valores nulo e negativo.

**Impacto:** somar os dois valores positivos gera R$ 10.000,00 pagos, enquanto o líquido observado é zero se o estorno desfizer pagamento. Descartes invisíveis impedem distinguir saldo real de importação incompleta. Não converter −200 em estorno automaticamente: isso inventaria uma regra.

**Relação:** tratamento uniforme de tipos e ausência de quarentena/alertas são causas; saldos distorcidos e falta de rastreabilidade são consequências. A relação exata entre estorno e evento original não consta dos dados.

### 3. Carteiras diferentes e divergência real de valor

**Evidência:** `tribunal.csv`, linha 3: processo 0023456 tem R$ 30.000,00; `hub.csv`, linha 3: o mesmo processo sem máscara tem R$ 31.000,00. O processo 0067890, R$ 7.000,00, aparece no tribunal, linha 6, e tem pagamento `ev-011` (`pagamentos.json`, registro 13), mas está ausente do hub. O processo 0056789, R$ 22.000,00, aparece apenas no hub, linha 6, e nas apresentações, registro 5; seu único evento recebido é o inválido `ev-009`.

**Impacto:** diferença de R$ 1.000,00 no valor de face do 0023456 e risco de carteira incompleta ou cadastro indevido. As somas dos arquivos são R$ 104.300,00 no tribunal e R$ 120.300,00 no hub. A diferença de R$ 16.000,00 se decompõe em +1.000 +22.000 −7.000. Isso não prova que R$ 7.000,00 virou R$ 22.000,00: são processos diferentes.

**Relação:** divergências são consequências observadas; causas possíveis incluem atualização não conciliada ou recortes/datas diferentes. Não há evidência suficiente para escolher uma dessas causas. Na limpeza, o tribunal é a referência provisória de valor de face; divergências continuam pendentes.

### 4. Dois prazos um ano além do calculado pela regra fornecida

**Evidência:** `hub.csv`, linha 2, e `apresentacoes.json`, registro 1: 0012345 foi apresentado em 02/04/2025, com prazo no hub em 31/12/2027; pela regra inclusiva seria 31/12/2026. `hub.csv`, linha 6, e apresentações, registro 5: `2025-04-03T01:00:00Z` corresponde a 02/04/2025 às 22h em Brasília; usando essa data civil, 0056789 também teria prazo em 31/12/2026, e não 2027.

**Impacto:** a operação pode priorizar essas dívidas um ano depois. Em 25/11/2026, os prazos de 0034567 e 0067890 são 31/12/2025 e seus saldos observados são positivos. São alertas para conferir o histórico, não prova de inadimplência: faltam eventos fora do recorte.

**Relação:** prazo errado é consequência. Exclusão indevida do dia 2 e uso da data UTC são hipóteses de causa; precisam ser verificadas no script. O fuso de negócio ainda precisa de confirmação.

### 5. Nomes dos entes danificados e possível devedor incorreto

**Evidência:** todas as linhas de dados de `tribunal.csv` (2–6) contêm o caractere de substituição Unicode `�` nos nomes. Os bytes `EF BF BD` representam esse caractere em UTF-8: não é algo que se resolva relendo como outra codificação. Na linha 5, o texto é `Uni�o`, enquanto o mesmo processo 0045678 está associado a `Município de Santos` no hub, linha 5. É uma divergência aparente de identidade, a confirmar com uma fonte íntegra.

**Impacto:** filtros e comparações por nome falham; aceitar o hub pode associar o crédito ao devedor errado. A limpeza conserva o texto original e deixa o ente confirmado nulo. Não completa letras por adivinhação nem copia o nome do hub como se fosse validado.

**Relação:** perda de caracteres é causa de comparação insegura. A origem dessa perda é desconhecida. Abrir e salvar no Excel (`ENUNCIADO.md`, linha 17) introduz risco de alteração, mas os arquivos não comprovam que o Excel causou esta corrupção.

### 6. Contrato de integração diverge dos arquivos e não garante cobertura

**Evidência:** `DOCUMENTACAO_TRIBUNAL.md`, linhas 13–15, exige valor numérico, data ISO e tipo sempre pagamento; `ev-002` traz texto `2.500,50` e `10/04/2025`, e `ev-007` é estorno. As linhas 20 e 26 descrevem CSV com vírgula e decimal com ponto, mas o tribunal usa ponto e vírgula, milhares com ponto e decimal com vírgula. `apresentacoes.json` nem está documentado. As datas de pagamento vão de 20/02/2025 (`ev-006`) a 10/08/2025 (`ev-011`), incompatíveis com uma única janela de sete dias, descrita no enunciado, linha 15. Não há data de geração dos arquivos.

**Impacto:** parser conforme a documentação pode falhar ou perder registros; não se consegue afirmar que totais representam todo o histórico. As apresentações são essenciais para calcular prazos, mas falta um contrato para elas.

**Relação:** contrato desatualizado ou arquivo de natureza diferente da descrita são hipóteses de causa; formatos inesperados e incerteza de cobertura são consequências. O arquivo pode ser uma amostra histórica: isso precisa de confirmação.

### 7. Comparação literal e esquema insuficiente para controle e auditoria

**Evidência:** `hub.csv`, linha 3, e `pagamentos.json`, registro 6 (`ev-005`), têm processo sem máscara, com os mesmos 20 dígitos do tribunal. Os cabeçalhos `numero_processo`/`ente_devedor` e `processo`/`ente` são diferentes, e os CSV têm espaços de alinhamento. `schema.sql`, linha 3, usa `CHAR(20)`, incompatível com os 25 caracteres da máscara completa e sem validação de dígitos; linha 5 não exige valor de face positivo. O esquema completo (linhas 1–16) não tem apresentação, prazo, histórico de valor de face, log de importação nem índice específico da FK de pagamentos.

**Impacto:** comparação textual pode deixar de vincular `ev-005`, de R$ 1.200,00, e produzir divergências falsas. Falta suporte para explicar alterações e rejeições. A ausência de índice pode prejudicar consultas com volume; não foi medida lentidão nesta amostra.

**Relação:** identidade não normalizada e controles ausentes são causas de fragilidade. A ausência de colunas de prazo ou total pago no esquema não prova que estejam armazenados fora do banco: podem ser calculados na exportação. Sem código, isso permanece desconhecido.

**Ajustes das observações iniciais:** processo sem pontuação é recuperável mantendo os 20 dígitos e zeros à esquerda; o grave é compará-lo literalmente ou convertê-lo em número. `12.500,00` e `12500.00` representam o mesmo valor. Caixa e acentos podem ser normalizados para comparação quando o texto está íntegro; isso não recupera caracteres `�`. Timestamp com fuso é uma representação válida de data/hora, mas exige uma regra de conversão para a data de apresentação. As capturas servem de apoio; os arquivos e registros identificados acima são a evidência principal.

## Limpeza

O programa [limpeza.py](../limpeza.py) lê os quatro arquivos como recebidos, usando `csv`, `json` e `Decimal`. Não usa Excel, não modifica entradas e exige uma nova pasta de saída por execução.

Regras adotadas para este exercício, sujeitas às dúvidas abaixo:

1. Processos ficam como texto com 20 dígitos, preservando zeros. Aceitam-se somente a máscara completa ou 20 dígitos. Não se valida o dígito verificador dos processos fictícios; essa regra deve ser acordada antes de produção.
2. CSV do tribunal usa `;`, hub usa `,`; cabeçalhos e valores são aparados. Cabeçalho ou estrutura de arquivo inesperados interrompem a execução. Problemas de registros identificáveis geram quarentena. Duplicatas de cadastro são registradas; cadastros conflitantes não são escolhidos pela ordem.
3. Dinheiro é convertido com `Decimal`, sem arredondar centavos extras. São aceitos os formatos brasileiros recebidos e o decimal com ponto. Nulo, zero, negativo, formato inválido e valores fora de `NUMERIC(15,2)` são rejeitados. Não se presume que valor negativo seja estorno.
4. Eventos são agrupados por `evento_id`; vence o maior `atualizado_em`, comparado como instante com fuso. Duplicata é descartada e versão anterior é substituída. Empate com conteúdo diferente fica em quarentena. Se a versão mais recente for inválida, a antiga não volta a valer. Se faltar horário confiável em qualquer versão, o grupo fica em quarentena.
5. Pagamento aumenta o líquido; estorno positivo diminui. Não se exige correspondência com evento original porque não há esse identificador no contrato. Esse vínculo precisa ser definido pelo tribunal.
6. Apresentação sem hora é data civil; timestamp é convertido para `America/Sao_Paulo` antes de extrair a data. Prazo usa 2 de abril inclusivo, conforme o enunciado. O hub é comparado com a apresentação recebida, sem servir de autoridade para corrigir cadastro.
7. Valor de face vem provisoriamente do tribunal. O hub fica preservado para comparação. Processos presentes em somente uma fonte não desaparecem: ficam na base com pendência. Valor ausente não é preenchido com zero. Entes danificados ficam nulos no campo confirmado, com original preservado. Todos os cinco cadastros do tribunal precisam de confirmação de ente.

Saídas:

| Arquivo                  | Conteúdo                                                                                                                          |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `base.json`              | União dos processos cadastrados/apresentados, formatos normalizados, campos de origem, pendências, prazo e total/saldo observados |
| `pagamentos_limpos.json` | Uma versão válida por evento, sem duplicatas, mantendo a posição original                                                         |
| `relatorio.json`         | SHA-256 de cada entrada, referência temporal, ações, localização, motivo e dados originais dos registros processados              |

O relatório registra as normalizações aplicadas, as duas correções de prazo, os descartes e as dúvidas. Os CSV/JSON originais continuam sendo a fonte exata, inclusive espaços e bytes, identificada pelos hashes. As contagens de ações não são uma contagem de registros únicos: um cadastro pode ter normalização e pendência.

Resultado verificado com `--data-referencia 2026-11-25`: 13 registros de pagamento recebidos, oito aceitos, dois descartados (duplicata de `ev-002` e versão antiga de `ev-001`) e três em quarentena (`ev-004`, `ev-009`, `ev-010`).

| Processo (prefixo) | Face do tribunal | Pago líquido observado | Saldo observado | Prazo calculado |
| ------------------ | ---------------: | ---------------------: | --------------: | --------------- |
| 0012345            |        45.000,00 |              18.000,50 |       26.999,50 | 31/12/2026      |
| 0023456            |        30.000,00 |               9.200,00 |       20.800,00 | 31/12/2027      |
| 0034567            |        12.500,00 |                   0,00 |       12.500,00 | 31/12/2025      |
| 0045678            |         9.800,00 |               3.000,00 |        6.800,00 | 31/12/2026      |
| 0056789            |   não confirmado |                   0,00 |   não calculado | 31/12/2026      |
| 0067890            |         7.000,00 |               4.000,00 |        3.000,00 | 31/12/2025      |

O total líquido dos eventos aceitos é R$ 34.200,50. Zero observado significa ausência de pagamento líquido válido neste recorte; não significa ausência de pagamentos reais. Não há histórico suficiente para certificar os saldos, e o relatório marca `pronto_para_producao: false`. Esta é uma base auditável para conciliação, com campos confirmáveis separados das pendências; não é uma carga automática no banco definitivo.

## Prevenção

### Processo operacional

Guardar anexos originais por lote, sem regravação no Excel, com hash, data de recebimento e versão do leiaute. Pedir contrato atualizado e arquivos íntegros ao tribunal. A conferência deve ser por número de processo normalizado e identificador estável do ente, com relatório de diferenças, não por posição de linha ou texto literal.

Cada lote deve ter responsável, contagem recebida/aceita/rejeitada, totais conciliáveis e alerta de quarentena, divergência de carteira e prazo. Rejeição precisa de motivo e resolução registrada. Validar a cobertura histórica antes de publicar saldo; confirmar divergências com as duas fontes e preservar evidências. Não sobrescrever o sistema inteiro só porque uma lista semanal deixou um processo de fora.

### Script de importação

Aplicar as mesmas normalizações e validações da limpeza. Validar o lote antes da gravação; usar transação e registrar seu resultado. Reexecução deve produzir os mesmos fatos, sem somar novamente. Gravar evento por identidade e versão, incluindo `atualizado_em`; correção mais recente substitui, versão antiga não altera e empate divergente gera quarentena. Preservar registros brutos e horários de todas as versões no log.

No importador de produção, cadastrar o lote em `importacao`; inserir em `ocorrencia_importacao` cada decisão com registro, motivo e original. Usar `importar_pagamento()` para eventos aprovados. Se houver erro de banco, usar savepoint ou registrar a rejeição depois do rollback, para não perder o próprio log. O retorno da função (`inserido`, `atualizado`, `duplicata`, `versao_antiga`) orienta o registro da ação. A função não grava os logs automaticamente: isso é responsabilidade do importador, que não foi fornecido e não é implantado pela limpeza offline.

### Banco de dados

O arquivo [prevencao.sql](../prevencao.sql) cria um banco lógico novo em PostgreSQL 14+, correspondente às medidas abaixo. Deve ser executado em um banco vazio; não altera o `schema.sql` original nem migra produção. Carga definitiva exige resolver os campos pendentes, especialmente os entes.

| Requisito                                   | Implementação no SQL                                                                                                                  |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Processo padronizado, sem padding de `CHAR` | `TEXT UNIQUE` com `CHECK` de exatamente 20 dígitos                                                                                    |
| Cadastro único de entes                     | `ente_devedor`, FK obrigatória em precatório e chave única calculada por trigger, sem caixa, acentos e espaços repetidos; rejeita `�` |
| Valor de face válido                        | `NUMERIC(15,2) NOT NULL`, positivo e sem NaN                                                                                          |
| Apresentação e prazo consistentes           | Data civil obrigatória e prazo como coluna gerada pela regra inclusiva do case                                                        |
| Um evento corrente por identidade           | `evento_id UNIQUE`, tipo limitado, valor positivo, data e `atualizado_em` obrigatórios                                                |
| Correções sem duplicação                    | Função `importar_pagamento`, bloqueio da linha, atualização apenas de versão mais nova, erro em empate divergente                     |
| Total e saldo sem contador acumulado        | View `saldo_precatorio`, subtraindo estornos; requer cobertura histórica validada para uso definitivo                                 |
| Consultas de pagamentos por processo        | Índice em `pagamento.precatorio_id`                                                                                                   |
| Rastrear recebimento e rejeições            | `importacao` por arquivo/hash e `ocorrencia_importacao` com original JSONB, localização e motivo                                      |
| Histórico de mudança de valor de face       | Trigger grava valor anterior/novo, horário e lote em `historico_valor_face`; valor inicial permanece no lote original                 |

Cadastro por nome normalizado reduz variações, mas não distingue entes homônimos. Até receber identificador oficial, a operação deve aprovar esse cadastro. O SQL não impõe saldo não negativo ou pagamento limitado à face: o case não define juros, atualização ou estornos de pagamentos anteriores ao recorte. Essas regras precisam ser esclarecidas antes de acrescentar restrições.

## Dúvidas antes de produção

### Ao tribunal

1. `evento_id` é globalmente único e estável? Reenvios do mesmo ID representam substituição integral? `atualizado_em` sempre avança e tem fuso? Como resolver empate, exclusão e cancelamento de evento?
2. Estorno desfaz um pagamento ou é outro ajuste? Pode ser parcial? Qual campo liga o estorno ao evento original? O pagamento negativo `ev-009` é erro ou tem significado próprio?
3. Podem reenviar `ev-004` com valor e `ev-010` com processo? Há outros eventos omitidos? É possível obter histórico completo e um total de controle por processo?
4. O arquivo é janela de sete dias, histórico ou amostra? Qual a data de geração, critério de seleção (pagamento ou atualização), fuso e cobertura de cada arquivo? Como chegam correções antigas?
5. Qual o leiaute oficial vigente: codificação, delimitador, decimal e formatos de datas? Podem reenviar os nomes sem `�` e fornecer identificador oficial dos entes?
6. `apresentacoes.json` é fonte oficial? O que significa o timestamp: apresentação jurídica ou registro técnico? Deve-se usar a data civil de Brasília, inclusive no exemplo em UTC?
7. As listas de precatórios são completas? Por que 0056789 está ausente? Valor de face pode mudar por atualização monetária ou revisão? Há versão ou data de vigência por cadastro?

### À operação

1. De onde vieram R$ 31.000,00 para 0023456 e o cadastro de 0056789? Por que 0067890 não está no hub? As exportações têm a mesma data, filtros e carteira?
2. Quem é o ente correto de 0045678: o nome aparentemente danificado de União no tribunal ou Município de Santos no hub? Quem aprova os demais nomes recuperados?
3. Onde estão o script real e o esquema efetivo de produção? Como os dados de apresentação/prazo são gerados? Existe histórico de reexecução, falhas e totais por lote para medir o erro real?
4. Podemos adotar provisoriamente o tribunal para face e o arquivo de apresentações para data? Quem resolve divergências e autoriza a correção, com qual evidência?
5. A regra de prazo do case vale para toda esta carteira? Há exceções, regimes ou mudanças de regra a representar? Confirmam a interpretação inclusiva e o fuso usados nesta solução?
6. O que compõe saldo: apenas face menos pagamentos ou também juros, atualização e outros ajustes? Pagamentos acima da face e estornos sem original no recorte são esperados?
7. Quem recebe alertas, em quanto tempo resolve quarentenas e como se reprocessa um lote corrigido? Qual reconciliação e validação humana serão exigidas antes da carga definitiva?

## Capturas da análise manual original

As imagens estão no arquivo PDF.
