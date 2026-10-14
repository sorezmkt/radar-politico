#!/usr/bin/env python3
"""
Radar Político — robô de dados.

Baixa dados abertos oficiais e gera os arquivos JSON que o site lê:
  data/index.json        lista de deputados com nota e nível de risco
  data/dep/<id>.json     ficha completa de cada deputado
  data/status.json       diagnóstico da última execução

Fontes:
  - API de Dados Abertos da Câmara (deputados em exercício)
  - Cota parlamentar (CEAP): https://www.camara.leg.br/cotas/Ano-<ano>.csv.zip
  - Proposições e autores, eventos e presenças, votações (arquivos anuais da Câmara)
  - Situação cadastral de CNPJ: BrasilAPI / Minha Receita (dados públicos da Receita Federal)

Roda no GitHub Actions todo dia (veja .github/workflows/atualizar-dados.yml).
"""
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict

from comum import aberta_ha_pouco, campos_receita, dias_desde_abertura, precisa_detalhe, precisa_reconsultar, pontuar, sinais_empresa_nova, situacao_cnpj

csv.field_size_limit(10_000_000)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DEP_DIR = os.path.join(DATA, "dep")
CACHE_DIR = os.path.join(ROOT, "cache")
CNPJ_CACHE = os.path.join(CACHE_DIR, "cnpj.json")

API = "https://dadosabertos.camara.leg.br/api/v2"
ARQ = "https://dadosabertos.camara.leg.br/arquivos"
UA = {"User-Agent": "RadarPolitico/1.0 (+https://github.com/sorezmkt/radar-politico)"}

T0 = time.time()
LIMITE_CNPJ_NOVOS = int(os.environ.get("LIMITE_CNPJ", "3000"))
TEMPO_MAX_CNPJ = 55 * 60  # segundos gastos no máximo com consultas de CNPJ por execução

status = {"avisos": [], "colunas": {}, "contagens": {}, "fontes": {}}


def aviso(msg):
    print("AVISO:", msg, flush=True)
    status["avisos"].append(msg)


def log(msg):
    print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)


# ---------------------------------------------------------------- utilidades

def baixar(url, tentativas=4, timeout=180):
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            erro = e
        except Exception as e:  # noqa: BLE001
            erro = e
        time.sleep(4 * (i + 1))
    raise erro


def norm(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().upper().strip()


def col(row, *nomes):
    for n in nomes:
        v = row.get(n)
        if v not in (None, ""):
            return v
    return ""


def num(s):
    s = (s or "").strip()
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def linhas_csv(texto_io, nome):
    """Lê CSV detectando o separador; registra as colunas em status.json."""
    primeira = texto_io.readline()
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    cab = next(csv.reader([primeira], delimiter=sep))
    cab = [c.strip().strip('"').lstrip("﻿") for c in cab]
    status["colunas"][nome] = cab
    for valores in csv.reader(texto_io, delimiter=sep):
        if valores:
            yield dict(zip(cab, valores))


def csv_remoto(url, nome):
    raw = baixar(url, timeout=600)
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        arq = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        fh = io.TextIOWrapper(z.open(arq), encoding="utf-8-sig", errors="replace", newline="")
    else:
        fh = io.StringIO(raw.decode("utf-8-sig", errors="replace"), newline="")
    return linhas_csv(fh, nome)


def data_iso(s):
    s = (s or "")[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        try:
            return dt.datetime.strptime(s, "%d/%m/%Y").date()
        except ValueError:
            return None


def percentil(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return vals[int(round(p * (len(vals) - 1)))]


def clamp(v):
    return max(0.0, min(100.0, v))


def salvar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- período

HOJE = dt.date.today()
FIM = HOJE.replace(day=1) - dt.timedelta(days=1)  # último dia do mês anterior
MESES = []
_a, _m = FIM.year, FIM.month
for _ in range(12):
    MESES.append((_a, _m))
    _m -= 1
    if _m == 0:
        _a, _m = _a - 1, 12
MESES.reverse()
INI = dt.date(MESES[0][0], MESES[0][1], 1)
ANOS = sorted({a for a, _ in MESES})
IDX_MES = {ym: i for i, ym in enumerate(MESES)}
NOME_MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Teto mensal da cota parlamentar por UF (valores de referência da Câmara, 2025)
TETO = {
    "AC": 50426.26, "AL": 46737.90, "AM": 49363.92, "AP": 49168.58, "BA": 44804.65,
    "CE": 48245.57, "DF": 36582.46, "ES": 43217.71, "GO": 41300.86, "MA": 47945.49,
    "MG": 41886.51, "MS": 46336.64, "MT": 45221.83, "PA": 48021.25, "PB": 47826.36,
    "PE": 47470.60, "PI": 46765.57, "PR": 44665.66, "RJ": 41553.77, "RN": 48525.79,
    "RO": 49466.29, "RR": 51406.33, "RS": 46669.70, "SC": 45671.58, "SE": 45933.06,
    "SP": 42837.33, "TO": 45297.41,
}

# ---------------------------------------------------------------- categorias da cota

CATEGORIAS = [
    ("DIVULGA", "Divulgação do mandato"),
    ("COMBUST", "Combustíveis"),
    ("PASSAGE", "Passagens aéreas"),
    ("ESCRITORIO", "Escritório de apoio"),
    ("AERONAVE", "Fretamento de aeronaves e barcos"),
    ("EMBARCA", "Fretamento de aeronaves e barcos"),
    ("VEICULO", "Locação de veículos"),
    ("CONSULTORI", "Consultorias e pesquisas"),
    ("TELEFON", "Telefonia"),
    ("POSTA", "Correios"),
    ("ALIMENTA", "Alimentação"),
    ("HOSPEDA", "Hospedagem"),
    ("TAXI", "Táxi, pedágio e estacionamento"),
    ("SEGURAN", "Segurança"),
    ("CURSO", "Cursos e eventos"),
    ("PUBLICA", "Assinaturas"),
]


def categoria(desc):
    d = norm(desc)
    for chave, nome in CATEGORIAS:
        if chave in d:
            return nome
    return "Outros"


# categorias em que concentrar em um só fornecedor é normal (companhia aérea, operadora, aluguel)
SEM_CONCENTRACAO = {"Passagens aéreas", "Telefonia", "Correios", "Escritório de apoio",
                    "Hospedagem", "Alimentação", "Táxi, pedágio e estacionamento", "Assinaturas"}
# categorias em que notas de valor redondo repetido são um sinal relevante
VALOR_REDONDO = {"Divulgação do mandato", "Consultorias e pesquisas", "Combustíveis", "Outros"}
# fornecedores que não precisam de checagem de CNPJ
SEM_CNPJ = {"Passagens aéreas", "Telefonia", "Correios"}

# ---------------------------------------------------------------- 1. deputados


def carregar_deputados():
    deps, url = [], f"{API}/deputados?itens=100&ordem=ASC&ordenarPor=nome"
    while url:
        j = json.loads(baixar(url))
        deps += j.get("dados", [])
        url = next((l["href"] for l in j.get("links", []) if l.get("rel") == "next"), None)
    out = {}
    for d in deps:
        out[str(d["id"])] = {
            "id": d["id"], "nome": d.get("nome", ""), "partido": d.get("siglaPartido", ""),
            "uf": d.get("siglaUf", ""), "foto": d.get("urlFoto", ""),
        }
    log(f"{len(out)} deputados em exercício")
    return out


# ---------------------------------------------------------------- 2. cota parlamentar


def carregar_cota(deps):
    reg = {}
    for did in deps:
        reg[did] = {"mensal": [0.0] * 12, "cats": defaultdict(float), "forn": {}, "notas": 0}
    linhas = 0
    for ano in ANOS:
        rows = None
        for base in ("https://www.camara.leg.br", "http://www.camara.leg.br"):
            try:
                rows = csv_remoto(f"{base}/cotas/Ano-{ano}.csv.zip", f"cota_{ano}")
                break
            except Exception as e:  # noqa: BLE001
                ultimo = e
        if rows is None:
            aviso(f"Cota {ano}: não foi possível baixar ({ultimo})")
            continue
        for r in rows:
            linhas += 1
            did = col(r, "ideCadastro").strip()
            if did not in reg:
                continue
            try:
                i = IDX_MES.get((int(col(r, "numAno")), int(col(r, "numMes"))))
            except ValueError:
                continue
            if i is None:
                continue
            v = num(col(r, "vlrLiquido", "vlrDocumento"))
            cat = categoria(col(r, "txtDescricao"))
            d = reg[did]
            d["mensal"][i] += v
            d["cats"][cat] += v
            d["notas"] += 1
            doc = re.sub(r"\D", "", col(r, "txtCNPJCPF"))
            nome = col(r, "txtFornecedor").strip()
            chave = doc or norm(nome)
            f = d["forn"].get(chave)
            if f is None:
                f = d["forn"][chave] = {"doc": doc, "nome": nome, "valor": 0.0, "cats": Counter(),
                                        "primeiro": None, "ultimo": None, "redondos": Counter()}
            f["valor"] += v
            f["cats"][cat] += v
            de = data_iso(col(r, "datEmissao"))
            if de and (f["primeiro"] is None or de < f["primeiro"]):
                f["primeiro"] = de
            if de and (f["ultimo"] is None or de > f["ultimo"]):
                f["ultimo"] = de
            vd = num(col(r, "vlrDocumento"))
            if cat in VALOR_REDONDO and vd >= 1000 and abs(vd - round(vd)) < 0.005 and int(round(vd)) % 100 == 0:
                f["redondos"][int(round(vd))] += 1
    status["contagens"]["linhas_cota"] = linhas
    status["fontes"]["cota"] = linhas > 0
    log(f"cota: {linhas} notas lidas")
    return reg


# ---------------------------------------------------------------- 3. proposições

TIPOS_AUTORAIS = {"PL", "PLP", "PEC", "PDL", "PRC"}
AVANCOU = re.compile(r"norma jur|sanc|senado|aprovad|promulg|pronta para pauta", re.I)


def carregar_proposicoes(deps):
    props = {}
    for ano in ANOS:
        try:
            for r in csv_remoto(f"{ARQ}/proposicoes/csv/proposicoes-{ano}.csv", f"proposicoes_{ano}"):
                if col(r, "siglaTipo") not in TIPOS_AUTORAIS:
                    continue
                data = data_iso(col(r, "dataApresentacao"))
                if not data or data < INI or data > FIM:
                    continue
                props[col(r, "id")] = {
                    "id": col(r, "id"), "tipo": col(r, "siglaTipo"), "numero": col(r, "numero"),
                    "ano": col(r, "ano"), "data": data.isoformat(),
                    "ementa": re.sub(r"\s+", " ", col(r, "ementa"))[:220],
                    "situacao": col(r, "ultimoStatus_descricaoSituacao", "ultimoStatus.descricaoSituacao"),
                }
        except Exception as e:  # noqa: BLE001
            aviso(f"Proposições {ano}: {e}")
    autoria = defaultdict(list)
    for ano in ANOS:
        try:
            for r in csv_remoto(f"{ARQ}/proposicoesAutores/csv/proposicoesAutores-{ano}.csv", f"autores_{ano}"):
                pid = col(r, "idProposicao")
                if pid not in props:
                    continue
                if col(r, "ordemAssinatura") not in ("1", "1.0"):
                    continue
                did = col(r, "idDeputadoAutor")
                if not did:
                    m = re.search(r"/deputados/(\d+)", col(r, "uriAutor"))
                    did = m.group(1) if m else ""
                if did in deps:
                    autoria[did].append(props[pid])
        except Exception as e:  # noqa: BLE001
            aviso(f"Autores {ano}: {e}")
    status["fontes"]["proposicoes"] = bool(props) and bool(autoria)
    status["contagens"]["proposicoes"] = len(props)
    log(f"proposições: {len(props)} no período, {len(autoria)} deputados autores")
    return autoria


# ---------------------------------------------------------------- 4. presença


def presenca_por_sessoes(deps):
    sessoes = {}
    for ano in ANOS:
        for r in csv_remoto(f"{ARQ}/eventos/csv/eventos-{ano}.csv", f"eventos_{ano}"):
            tipo = norm(col(r, "descricaoTipo"))
            if "SESSAO DELIBERATIVA" not in tipo:
                continue
            if "CANCEL" in norm(col(r, "situacao")):
                continue
            d = data_iso(col(r, "dataHoraInicio"))
            if d and INI <= d <= FIM:
                sessoes[col(r, "id")] = d
    presentes = defaultdict(set)
    for ano in ANOS:
        for r in csv_remoto(f"{ARQ}/eventosPresencaDeputados/csv/eventosPresencaDeputados-{ano}.csv",
                            f"presencas_{ano}"):
            eid = col(r, "idEvento")
            if eid not in sessoes:
                continue
            did = col(r, "idDeputado")
            if not did:
                m = re.search(r"/deputados/(\d+)", col(r, "uriDeputado"))
                did = m.group(1) if m else ""
            if did in deps:
                presentes[did].add(eid)
    return sessoes, presentes, "sessões deliberativas do Plenário"


def presenca_por_votacoes(deps):
    votacoes = {}
    for ano in ANOS:
        for r in csv_remoto(f"{ARQ}/votacoes/csv/votacoes-{ano}.csv", f"votacoes_{ano}"):
            if col(r, "siglaOrgao") != "PLEN":
                continue
            if num(col(r, "votosSim")) + num(col(r, "votosNao")) <= 0:
                continue
            d = data_iso(col(r, "data", "dataHoraRegistro"))
            if d and INI <= d <= FIM:
                votacoes[col(r, "id")] = d
    presentes = defaultdict(set)
    for ano in ANOS:
        for r in csv_remoto(f"{ARQ}/votacoesVotos/csv/votacoesVotos-{ano}.csv", f"votos_{ano}"):
            vid = col(r, "idVotacao")
            if vid not in votacoes:
                continue
            did = col(r, "deputado_id", "deputado_.id", "idDeputado")
            if did in deps:
                presentes[did].add(vid)
    return votacoes, presentes, "votações nominais no Plenário"


def carregar_presenca(deps):
    for fn in (presenca_por_sessoes, presenca_por_votacoes):
        try:
            eventos, presentes, metodo = fn(deps)
        except Exception as e:  # noqa: BLE001
            aviso(f"Presença ({fn.__name__}): {e}")
            continue
        res = {}
        for did in deps:
            p = presentes.get(did, set())
            if not p:
                continue
            inicio = min(eventos[e] for e in p)  # considera a partir da primeira presença (suplentes)
            total = sum(1 for d in eventos.values() if d >= inicio)
            res[did] = {"presente": len(p), "total": total, "metodo": metodo}
        if len(res) < 0.5 * len(deps):
            aviso(f"Presença ({metodo}): poucos deputados encontrados ({len(res)}), tentando outra fonte")
            continue
        med = percentil([v["presente"] / v["total"] for v in res.values() if v["total"]], 0.5) or 0
        if med < 0.3:
            aviso(f"Presença ({metodo}): mediana {med:.0%} parece errada, tentando outra fonte")
            continue
        status["fontes"]["presenca"] = metodo
        log(f"presença por {metodo}: {len(eventos)} eventos, mediana {med:.0%}")
        return res
    status["fontes"]["presenca"] = False
    return {}


# ---------------------------------------------------------------- 5. CNPJ


def consultar_cnpjs(cnpjs, primeiros=None):
    """primeiros: data do primeiro pagamento de cada CNPJ, para buscar atividade e capital das empresas recém-abertas."""
    try:
        with open(CNPJ_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except (FileNotFoundError, ValueError):
        cache = {}
    limite_idade = (HOJE - dt.timedelta(days=60)).isoformat()
    novos = [c for c in sorted(cnpjs) if c not in cache or cache[c].get("ts", "") < limite_idade or precisa_reconsultar(cache[c])
             or (precisa_detalhe(cache[c]) and aberta_ha_pouco(cache[c], (primeiros or {}).get(c)))]
    log(f"CNPJ: {len(cnpjs)} necessários, {len(novos)} a consultar")
    inicio, feitos = time.time(), 0
    for c in novos[:LIMITE_CNPJ_NOVOS]:
        if time.time() - inicio > TEMPO_MAX_CNPJ:
            aviso("CNPJ: tempo esgotado nesta execução, o restante fica para a próxima")
            break
        info = None
        for url in (f"https://brasilapi.com.br/api/cnpj/v1/{c}", f"https://minhareceita.org/{c}"):
            try:
                j = json.loads(baixar(url, tentativas=2, timeout=30))
                info = {
                    "situacao": norm(j.get("descricao_situacao_cadastral") or ""),
                    "abertura": j.get("data_inicio_atividade") or "",
                    **campos_receita(j),
                    "razao": j.get("razao_social") or "",
                    "ts": HOJE.isoformat(),
                }
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    info = {"situacao": "NAO ENCONTRADO", "abertura": "", "razao": "", "ts": HOJE.isoformat()}
                    break
            except Exception:  # noqa: BLE001
                pass
        if info:
            cache[c] = info
        feitos += 1
        if feitos % 200 == 0:
            salvar(CNPJ_CACHE, cache)
            log(f"CNPJ: {feitos} consultados")
        time.sleep(0.35)
    salvar(CNPJ_CACHE, cache)
    status["contagens"]["cnpj_consultados_agora"] = feitos
    status["contagens"]["cnpj_em_cache"] = len(cache)
    status["fontes"]["cnpj"] = len(cache) > 0
    return cache


# ---------------------------------------------------------------- 6. montagem


def meses_entre(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30.0


def metricas_padrao(c):
    """Concentração e notas redondas repetidas de um deputado (antes de comparar com a Câmara)."""
    conc_base, conc_por_forn, redondos = 0.0, {}, 0
    for chave, f in c["forn"].items():
        v_conc = sum(v for k, v in f["cats"].items() if k not in SEM_CONCENTRACAO)
        conc_base += v_conc
        conc_por_forn[chave] = v_conc
        redondos += sum(n for n in f["redondos"].values() if n >= 3)
    share = None
    if conc_base >= 20000:
        share = 100 * max(conc_por_forn.values()) / conc_base
    return conc_base, conc_por_forn, share, redondos


def main():
    os.makedirs(DEP_DIR, exist_ok=True)
    deps = carregar_deputados()
    cota = carregar_cota(deps)
    autoria = carregar_proposicoes(deps)
    presenca = carregar_presenca(deps)

    # fornecedores que merecem checagem de CNPJ: os 8 maiores de cada deputado (acima de 2% do total)
    precisa, primeiros = set(), {}
    for did, c in cota.items():
        total = sum(c["mensal"])
        if total <= 0:
            continue
        fs = sorted(c["forn"].values(), key=lambda f: -f["valor"])
        n = 0
        for f in fs:
            if len(f["doc"]) == 14 and f["valor"] / total >= 0.02 and f["cats"].most_common(1)[0][0] not in SEM_CNPJ:
                precisa.add(f["doc"])
                if f["primeiro"] and (f["doc"] not in primeiros or f["primeiro"] < primeiros[f["doc"]]):
                    primeiros[f["doc"]] = f["primeiro"]
                n += 1
            if n >= 8:
                break
    cnpj = consultar_cnpjs(precisa, primeiros) if precisa else {}

    # médias da Câmara
    medias, cats_total, geral = [], Counter(), 0.0
    for did, c in cota.items():
        ativos = [i for i, v in enumerate(c["mensal"]) if abs(v) > 0]
        if not ativos:
            continue
        meses_ativos = 12 - ativos[0]
        medias.append(sum(c["mensal"]) / meses_ativos)
        for k, v in c["cats"].items():
            cats_total[k] += v
            geral += v
    media_mensal = sum(medias) / len(medias) if medias else 0
    cat_media = {k: round(v / geral, 4) for k, v in cats_total.items()} if geral else {}

    prod_vals = [len(autoria.get(d, [])) for d in deps] if status["fontes"].get("proposicoes") else []
    efet_vals = [sum(1 for p in autoria.get(d, []) if AVANCOU.search(p["situacao"] or "")) for d in deps] if prod_vals else []
    ref = {
        "prod_p90": max(1, percentil(prod_vals, 0.9) or 1) if prod_vals else None,
        "prod_p25": percentil(prod_vals, 0.25) if prod_vals else None,
        "prod_mediana": percentil(prod_vals, 0.5) if prod_vals else None,
        "efet_p90": max(1, percentil(efet_vals, 0.9) or 1) if efet_vals else None,
        "efet_p75": percentil(efet_vals, 0.75) if efet_vals else None,
    }

    # limites dos sinais de risco calibrados pela própria Câmara: amarelo acima de 75% dos deputados, vermelho acima de 90%
    metr = {did: metricas_padrao(c) for did, c in cota.items()}
    shares = [m[2] for m in metr.values() if m[2] is not None]
    reds = [m[3] for m in metr.values()]
    lim = {
        "conc_warn": max(25.0, percentil(shares, 0.75) or 25.0), "conc_bad": max(40.0, percentil(shares, 0.9) or 40.0),
        "red_warn": max(3, percentil(reds, 0.75) or 3), "red_bad": max(6, percentil(reds, 0.9) or 6),
    }
    ref["limites_risco"] = {k: round(v, 1) for k, v in lim.items()}

    pesos = {"pres": 0.3, "econ": 0.3, "prod": 0.2, "efet": 0.2}
    if not presenca:
        pesos.pop("pres")
    if not status["fontes"].get("cota"):
        pesos.pop("econ")
    if not prod_vals:
        pesos.pop("prod")
        pesos.pop("efet")

    indice = []
    for did, d in deps.items():
        c = cota[did]
        teto = TETO.get(d["uf"])
        total = sum(c["mensal"])
        ativos = [i for i, v in enumerate(c["mensal"]) if abs(v) > 0]
        meses_ativos = 12 - ativos[0] if ativos else 0
        medio = total / meses_ativos if meses_ativos else 0

        # fornecedores
        fornecedores = []
        conc_base, conc_por_forn, share, redondos = metr[did]
        for chave, f in sorted(c["forn"].items(), key=lambda kv: -kv[1]["valor"])[:10]:
            if f["valor"] <= 0:
                continue
            pf = len(f["doc"]) == 11
            info = cnpj.get(f["doc"]) if len(f["doc"]) == 14 else None
            item = {
                "nome": "Pessoa física (nome omitido)" if pf else f["nome"],
                "cnpj": f["doc"] if len(f["doc"]) == 14 else "",
                "valor": round(f["valor"], 2),
                "pct": round(100 * f["valor"] / total, 1) if total > 0 else 0,
                "categoria": f["cats"].most_common(1)[0][0],
                "flags": [],
            }
            item["_chave"] = chave
            if info:
                item["situacao"] = info.get("situacao", "")
                abertura = data_iso(info.get("abertura"))
                if abertura:
                    item["abertura"] = abertura.isoformat()
                    if f["primeiro"]:
                        meses = meses_entre(abertura, f["primeiro"])
                        item["meses_ate_pagamento"] = round(meses, 1)
                        if meses < 0:
                            item["flags"].append("aberta depois do 1º pagamento")
                        elif meses < 6:
                            item["flags"].append(f"aberta {round(meses)} meses antes do 1º pagamento")
                            item["_sinais"] = sinais_empresa_nova(info, f["valor"], f["ultimo"], item["categoria"])
                # a situação de hoje só conta se já valia quando o deputado ainda pagava o fornecedor
                tipo, txt = situacao_cnpj(info, f["ultimo"])
                if tipo in ("antes", "sem_data"):
                    item["flags"].append(f"CNPJ {item['situacao'].lower()} " + ("antes do último pagamento" if tipo == "antes" else "hoje"))
                    item["_cnpj"] = (tipo, txt)
                elif tipo == "depois":
                    item["_cnpj"] = (tipo, txt)
            if conc_base >= 20000 and 100 * conc_por_forn[chave] / conc_base >= lim["conc_bad"]:
                item["flags"].append("concentração")
            if sum(n for n in f["redondos"].values() if n >= 3) >= lim["red_warn"]:
                item["flags"].append("valores repetidos")
            fornecedores.append(item)

        # sinais de risco
        checks = []
        if share is not None:
            chave_top = max(conc_por_forn, key=conc_por_forn.get)
            ftop = c["forn"][chave_top]
            nome_top = "uma pessoa física" if len(ftop["doc"]) == 11 else ftop["nome"]
            st = "bad" if share >= lim["conc_bad"] else "warn" if share >= lim["conc_warn"] else "good"
            comp = {"bad": "Acima de 90% dos deputados.", "warn": "Acima de 75% dos deputados.", "good": "Dentro do padrão da Câmara."}[st]
            checks.append({"id": "concentracao", "titulo": "Concentração em um fornecedor", "status": st,
                           "texto": f"{share:.0f}% dos gastos com divulgação, consultorias, combustível, veículos e outros serviços foram para {nome_top}. {comp}",
                           "_chaves": {chave_top: conc_por_forn[chave_top]} if st != "good" else None})
        else:
            checks.append({"id": "concentracao", "titulo": "Concentração em um fornecedor", "status": "nd",
                           "texto": "Gastos insuficientes nas categorias analisadas para avaliar."})

        verificados = [f for f in fornecedores if f.get("cnpj") and "situacao" in f]
        if verificados:
            novas = [f for f in verificados if any(x.startswith("aberta") for x in f["flags"]) and f["pct"] >= 2]
            irreg = [f for f in verificados if f.get("_cnpj", ("",))[0] in ("antes", "sem_data")]
            depois = [f for f in verificados if f.get("_cnpj", ("",))[0] == "depois"]
            # empresa recém-aberta sozinha merece conferência (amarelo); com 10% ou mais da cota e mais um sinal independente, vira prioridade
            graves = [f for f in novas if f.get("_sinais") and f["pct"] >= 10]
            checks.append({"id": "recem_aberta", "titulo": "Empresa recém-aberta", "status": "bad" if graves else "warn" if novas else "good",
                           "_chaves": {f["_chave"]: f["valor"] for f in novas},
                           "texto": ("; ".join(
                               (f"{f['nome']} recebeu antes da data de abertura registrada na Receita" if f.get("meses_ate_pagamento", 0) < 0
                                else f"{f['nome']} começou a receber {round(f.get('meses_ate_pagamento', 0))} meses depois de abrir")
                               + (" (" + "; ".join(f["_sinais"]) + ")" if f.get("_sinais") else "")
                               for f in novas) + ".")
                           if novas else f"Nenhum dos {len(verificados)} maiores fornecedores verificados foi aberto menos de 6 meses antes do primeiro pagamento."})
            st_cnpj = "bad" if any(f["_cnpj"][0] == "antes" for f in irreg) else "warn" if irreg else "good"
            txt_dep = (" " + "; ".join(f"{f['nome']}: {f['_cnpj'][1]}" for f in depois) + " (não conta como sinal).") if depois else ""
            checks.append({"id": "cnpj_irregular", "titulo": "Situação do CNPJ na Receita", "status": st_cnpj,
                           "_chaves": {f["_chave"]: f["valor"] for f in irreg},
                           "texto": ("; ".join(f"{f['nome']}: {f['_cnpj'][1]}" for f in irreg) + "." + txt_dep)
                           if irreg else f"Nenhum dos {len(verificados)} maiores fornecedores verificados estava baixado, inapto ou suspenso quando recebeu.{txt_dep}"})
        else:
            for cid, tit in (("recem_aberta", "Empresa recém-aberta"), ("cnpj_irregular", "Situação do CNPJ na Receita")):
                checks.append({"id": cid, "titulo": tit, "status": "nd", "texto": "Fornecedores ainda não verificados na Receita."})

        st = "bad" if redondos >= lim["red_bad"] else "warn" if redondos >= lim["red_warn"] else "good"
        comp = {"bad": "Acima de 90% dos deputados.", "warn": "Acima de 75% dos deputados.", "good": "Dentro do padrão da Câmara."}[st]
        checks.append({"id": "valores_redondos", "titulo": "Notas de valor redondo repetido", "status": st,
                       "texto": f"{redondos} notas com o mesmo valor exato e redondo (acima de R$ 1.000) repetido 3 vezes ou mais no mesmo fornecedor, em divulgação, consultoria, combustível ou outros serviços. {comp}"
                       if redondos else "Nenhum padrão de valores redondos repetidos."})
        checks.append({"id": "doador", "titulo": "Fornecedor ligado a doador de campanha", "status": "breve",
                       "texto": "Cruzamento com as doações declaradas ao TSE em desenvolvimento."})
        checks.append({"id": "agenda", "titulo": "Gasto incompatível com a agenda", "status": "breve",
                       "texto": "Cruzamento entre local das notas e presença em Brasília em desenvolvimento."})
        # o mesmo fornecedor em vários sinais conta uma vez só (vale o mais grave)
        pts, fatores = pontuar(checks, chave_txt="texto")
        for f in fornecedores:
            f.pop("_chave", None)
            f.pop("_cnpj", None)
            f.pop("_sinais", None)
        nivel = "alto" if pts >= 4 else "moderado" if pts >= 2 else "baixo"

        # proposições
        minhas = sorted(autoria.get(did, []), key=lambda p: p["data"], reverse=True)
        avancadas = [p for p in minhas if AVANCOU.search(p["situacao"] or "")]
        destaque = (avancadas[:3] + [p for p in minhas if p not in avancadas])[:6]

        # notas
        s = {}
        pr = presenca.get(did)
        if "pres" in pesos:
            s["pres"] = clamp(100 * pr["presente"] / pr["total"]) if pr and pr["total"] else None
        if "econ" in pesos:
            s["econ"] = clamp((1 - medio / teto) / 0.5 * 100) if teto and meses_ativos else None
        if "prod" in pesos:
            s["prod"] = clamp(100 * len(minhas) / ref["prod_p90"])
            s["efet"] = clamp(100 * len(avancadas) / ref["efet_p90"])
        validos = {k: v for k, v in s.items() if v is not None}
        peso_total = sum(pesos[k] for k in validos)
        nota = round(sum(validos[k] * pesos[k] for k in validos) / peso_total) if peso_total else None
        if s.get("pres") is None and s.get("econ") is None:
            nota = None  # recém-empossado ou sem atividade registrada: dados insuficientes para avaliar

        ficha = {
            **d, "teto": teto, "mensal": [round(v, 2) for v in c["mensal"]], "total": round(total, 2),
            "medio": round(medio, 2), "meses_ativos": meses_ativos, "notas_fiscais": c["notas"],
            "cats": {k: round(v, 2) for k, v in sorted(c["cats"].items(), key=lambda kv: -kv[1]) if v > 0},
            "fornecedores": fornecedores,
            "presenca": pr,
            "props": {"n": len(minhas), "avancadas": len(avancadas),
                      "lista": [{**p, "url": f"https://www.camara.leg.br/propostas-legislativas/{p['id']}"} for p in destaque]},
            "scores": {k: (round(v) if v is not None else None) for k, v in s.items()},
            "nota": nota,
            "risco": {"pontos": pts, "nivel": nivel, "checks": checks, "fatores": fatores},
        }
        salvar(os.path.join(DEP_DIR, f"{did}.json"), ficha)
        indice.append({"id": d["id"], "nome": d["nome"], "partido": d["partido"], "uf": d["uf"],
                       "foto": d["foto"], "nota": nota, "risco": nivel, "pontos": pts,
                       "total": round(total)})

    indice.sort(key=lambda x: (-(x["nota"] if x["nota"] is not None else -1), x["nome"]))
    salvar(os.path.join(DATA, "index.json"), {
        "atualizado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M"),
        "periodo": {"inicio": INI.isoformat(), "fim": FIM.isoformat(),
                    "meses": [f"{NOME_MES[m - 1]}/{str(a)[2:]}" for a, m in MESES]},
        "media_mensal": round(media_mensal, 2),
        "cat_media": cat_media,
        "referencias": ref,
        "pesos": pesos,
        "fontes": status["fontes"],
        "deputados": indice,
    })
    status["contagens"]["deputados"] = len(indice)
    status["duracao_s"] = round(time.time() - T0)
    status["executado_em"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    salvar(os.path.join(DATA, "status.json"), status)
    log("pronto")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        status["erro_fatal"] = repr(e)
        salvar(os.path.join(DATA, "status.json"), status)
        raise
