"""Limpeza auditável do case. Python 3.10+, somente biblioteca padrão."""
import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo


BRASILIA = ZoneInfo("America/Sao_Paulo")


def processo(valor):
    texto = str(valor or "").strip()
    if not re.fullmatch(r"[0-9]{20}|[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}", texto):
        raise ValueError("processo deve ter 20 dígitos ou máscara CNJ completa")
    return re.sub(r"[^0-9]", "", texto)


def dinheiro(valor):
    texto = str(valor).strip()
    if re.fullmatch(r"-?(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2}", texto):
        texto = texto.replace(".", "").replace(",", ".")
    elif not re.fullmatch(r"-?[0-9]+(?:\.[0-9]{1,2})?", texto):
        raise ValueError("valor ausente ou formato monetário inválido")
    try:
        numero = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError("valor inválido") from erro
    if not numero.is_finite() or numero <= 0 or numero >= Decimal("10000000000000"):
        raise ValueError("valor deve ser positivo e caber em NUMERIC(15,2)")
    return numero.quantize(Decimal("0.01"))


def instante(valor):
    horario = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    if horario.tzinfo is None:
        raise ValueError("data e hora sem fuso")
    return horario.astimezone(timezone.utc)


def data_local(valor):
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(valor)):
        return date.fromisoformat(valor)
    return instante(valor).astimezone(BRASILIA).date()


def data_pagamento(valor):
    if re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", str(valor)):
        return datetime.strptime(valor, "%d/%m/%Y").date()
    return date.fromisoformat(valor)


def prazo(apresentado):
    anos = 1 if apresentado <= date(apresentado.year, 4, 2) else 2
    return date(apresentado.year + anos, 12, 31)


def chave_ente(nome):
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", nome)
                         if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def ler_csv(caminho, separador, campos):
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=separador, skipinitialspace=True)
        leitor.fieldnames = [nome.strip() for nome in (leitor.fieldnames or [])]
        if set(leitor.fieldnames) != set(campos):
            raise ValueError(f"{caminho.name}: cabeçalho inesperado")
        registros = []
        for linha, registro in enumerate(leitor, 2):
            if None in registro or None in registro.values():
                raise ValueError(f"{caminho.name}, linha {linha}: quantidade de campos inválida")
            registros.append((linha, {k: v.strip() for k, v in registro.items()}))
        return registros


def ler_json(caminho):
    # Decimal evita introduzir arredondamento binário nos valores financeiros.
    registros = json.loads(caminho.read_text(encoding="utf-8-sig"), parse_float=Decimal)
    if not isinstance(registros, list) or any(not isinstance(r, dict) for r in registros):
        raise ValueError(f"{caminho.name}: esperado um array de objetos")
    return list(enumerate(registros, 1))


def limpar(entrada, saida, referencia):
    entrada, saida = Path(entrada).resolve(), Path(saida).resolve()
    if saida == entrada or entrada in saida.parents or saida in entrada.parents:
        raise ValueError("a saída deve ficar separada da pasta de entrada")
    ocorrencias = []

    def registrar(arquivo, registro, acao, motivo, original=None):
        ocorrencias.append(dict(arquivo=arquivo, registro=registro, acao=acao,
                                motivo=motivo, original=original))

    tribunal = ler_csv(entrada / "tribunal.csv", ";", ["numero_processo", "ente_devedor", "valor_face"])
    hub = ler_csv(entrada / "hub.csv", ",", ["processo", "ente", "valor_face", "apresentado_em", "prazo_pagamento"])
    apresentacoes = ler_json(entrada / "apresentacoes.json")
    pagamentos = ler_json(entrada / "pagamentos.json")

    def indexar(registros, arquivo, campo, transformar):
        grupos = defaultdict(list)
        for numero, bruto in registros:
            try:
                numero_processo = processo(bruto.get(campo))
                valor = transformar(bruto)
                grupos[numero_processo].append((numero, bruto, valor))
                registrar(arquivo, numero, "normalizado", "formato e chave normalizados", bruto)
            except (ValueError, TypeError, KeyError) as erro:
                registrar(arquivo, numero, "quarentena", str(erro), bruto)
        resultado = {}
        for numero_processo, linhas in grupos.items():
            if any(linha[2] != linhas[0][2] for linha in linhas[1:]):
                registrar(arquivo, [l[0] for l in linhas], "quarentena", "cadastros conflitantes para o mesmo processo")
            else:
                resultado[numero_processo] = linhas[0][2]
                for numero, bruto, _ in linhas[1:]:
                    registrar(arquivo, numero, "descartado", "cadastro repetido", bruto)
        return resultado

    cadastros = indexar(tribunal, "tribunal.csv", "numero_processo",
                       lambda r: dict(ente_original=r["ente_devedor"], valor_face=dinheiro(r["valor_face"])))
    exportacao = indexar(hub, "hub.csv", "processo", lambda r: r)
    datas = indexar(apresentacoes, "apresentacoes.json", "processo", lambda r: data_local(r["apresentado_em"]))

    grupos = defaultdict(list)
    for numero, bruto in pagamentos:
        identificador = bruto.get("evento_id")
        if not isinstance(identificador, str) or not identificador.strip():
            registrar("pagamentos.json", numero, "quarentena", "evento_id ausente", bruto)
        else:
            grupos[identificador.strip()].append((numero, bruto))

    aceitos = []
    for identificador, versoes in sorted(grupos.items()):
        try:
            # Seleciona a versão ANTES de validar valor: uma correção inválida
            # não pode fazer a versão antiga voltar a valer silenciosamente.
            ordenadas = [(instante(r["atualizado_em"]), n, r) for n, r in versoes]
            ultima = max(t for t, _, _ in ordenadas)
            atuais = [(n, r) for t, n, r in ordenadas if t == ultima]
            if any(r != atuais[0][1] for _, r in atuais[1:]):
                raise ValueError("mesmo evento e horário com conteúdos diferentes")
            numero, bruto = atuais[0]
            evento = dict(evento_id=identificador, processo=processo(bruto["processo"]),
                          valor=dinheiro(bruto["valor"]), tipo=bruto["tipo"],
                          pago_em=data_pagamento(bruto["data_pagamento"]).isoformat(),
                          atualizado_em=ultima.isoformat(), registro_origem=numero)
            if evento["tipo"] not in ("pagamento", "estorno"):
                raise ValueError("tipo desconhecido")
            if evento["processo"] not in cadastros:
                raise ValueError("processo sem cadastro válido no tribunal")
            aceitos.append(evento)
            registrar("pagamentos.json", numero, "aceito", "versão mais recente válida; formatos normalizados", bruto)
            for horario, n, r in ordenadas:
                if n != numero:
                    motivo = "duplicata" if horario == ultima else "versão substituída"
                    registrar("pagamentos.json", n, "descartado", motivo, r)
        except (ValueError, TypeError, KeyError) as erro:
            for n, r in versoes:
                registrar("pagamentos.json", n, "quarentena", str(erro), r)

    totais = defaultdict(lambda: Decimal("0.00"))
    for evento in aceitos:
        sinal = 1 if evento["tipo"] == "pagamento" else -1
        totais[evento["processo"]] += sinal * evento["valor"]

    base = []
    for numero_processo in sorted(set(cadastros) | set(exportacao) | set(datas)):
        cadastro = cadastros.get(numero_processo, {})
        h = exportacao.get(numero_processo)
        apresentado = datas.get(numero_processo)
        limite = prazo(apresentado) if apresentado else None
        pendencias = []
        ente = cadastro.get("ente_original")
        if not cadastro:
            pendencias.append("ausente ou inválido no tribunal; não adotar valor do hub")
        if ente is not None and ("\ufffd" in ente or not ente.strip()):
            pendencias.append("ente do tribunal danificado; confirmar nome e identificador")
            ente = None
        if not h:
            pendencias.append("ausente ou inválido no hub")
        if not apresentado:
            pendencias.append("data de apresentação ausente ou conflitante")
        if h:
            try:
                if cadastro and dinheiro(h["valor_face"]) != cadastro["valor_face"]:
                    pendencias.append("valor de face diverge do hub")
                if ente and chave_ente(ente) != chave_ente(h["ente"]):
                    pendencias.append("ente diverge do hub")
                if apresentado and data_local(h["apresentado_em"]) != apresentado:
                    pendencias.append("apresentação diverge do hub")
                if limite and date.fromisoformat(h["prazo_pagamento"]) != limite:
                    registrar("hub.csv", numero_processo, "corrigido", f"prazo recalculado: {limite}", h)
            except (ValueError, TypeError, KeyError) as erro:
                pendencias.append(f"campo inválido no hub: {erro}")
        for motivo in pendencias:
            registrar("conciliacao", numero_processo, "duvida", motivo)
        face = cadastro.get("valor_face")
        saldo = face - totais[numero_processo] if face is not None else None
        base.append(dict(processo=numero_processo, ente_devedor=ente,
                         ente_original=cadastro.get("ente_original"), valor_face=face,
                         apresentado_em=apresentado, prazo_pagamento=limite,
                         total_pago_observado=totais[numero_processo], saldo_observado=saldo,
                         vencido_no_recorte=bool(limite and limite < referencia and saldo is not None and saldo > 0),
                         pendencias=pendencias, dados_hub=h))

    registrar("conjunto", None, "duvida", "janela histórica incompleta: totais e saldos são apenas do recorte recebido")
    registrar("conjunto", None, "duvida", "confirmar versão por atualizado_em, fuso de apresentação e semântica do estorno")
    arquivos = {nome: hashlib.sha256((entrada / nome).read_bytes()).hexdigest()
                for nome in ("tribunal.csv", "hub.csv", "apresentacoes.json", "pagamentos.json")}
    relatorio = dict(data_referencia=referencia.isoformat(), sha256_entradas=arquivos,
                     localizacao="CSV: linha física (cabeçalho = 1); JSON: posição no array (inicia em 1)",
                     contagens=dict(Counter(o["acao"] for o in ocorrencias)),
                     pagamentos_lidos=len(pagamentos), pagamentos_aceitos=len(aceitos),
                     pronto_para_producao=False, ocorrencias=ocorrencias)
    # Nova pasta por execução: evita misturar resultados antigos ou sobrescrever originais.
    saida.mkdir(parents=True, exist_ok=False)
    for nome, conteudo in (("base.json", base), ("pagamentos_limpos.json", aceitos), ("relatorio.json", relatorio)):
        (saida / nome).write_text(json.dumps(conteudo, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return base, aceitos, relatorio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=Path(__file__).parent / "case-candidato" / "dados")
    parser.add_argument("--saida", type=Path, default=Path("saida"))
    parser.add_argument("--data-referencia", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        _, eventos, _ = limpar(args.entrada, args.saida, args.data_referencia)
    except (ValueError, OSError) as erro:
        parser.exit(1, f"Falha: {erro}\n")
    print(f"{len(eventos)} eventos aceitos. Base e relatório em {args.saida}. Consulte as pendências.")


if __name__ == "__main__":
    main()
