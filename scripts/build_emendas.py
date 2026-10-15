#!/usr/bin/env python3
"""
Radar Político — robô das emendas parlamentares.

Gera os arquivos que as páginas de emendas leem:
  data/emendas/resumo.json        visão nacional por ano (valores por etapa, tipo, área, estado, entidades)
  data/emendas/deputados.json     lista dos deputados em exercício com o total das emendas individuais
  data/emendas/municipios.json    totais por cidade de destino
  data/emendas/dep/<id>.json      emendas individuais de cada deputado, destinos, favorecidos e alertas

Fontes (todas públicas e gratuitas, sem chave de acesso):
  - Portal da Transparência (CGU): download "Emendas parlamentares" (emendas, convênios e favorecidos)
  - Transferegov (Ministério da Gestão): API das transferências especiais, as "emendas Pix"
  - data/index.json do próprio Radar (deputados em exercício, gerado por build_data.py)

Regras que o robô segue:
  - valores de etapas diferentes (empenhado, pago, restos a pagar) nunca são somados como parcelas independentes;
  - pago até agora = pago no próprio ano + restos a pagar pagos nos anos seguintes;
  - só emendas individuais são atribuídas a um deputado; bancada, comissão e relator aparecem só na visão nacional;
  - a ligação entre bases usa o código oficial da emenda; nada é ligado por nome, valor ou data parecidos,
    exceto o autor, que o Portal identifica pelo nome e o robô liga ao deputado só quando o nome é único.
"""
import csv
import datetime as dt
import gzip
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

csv.field_size_limit(10_000_000)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "emendas")
CACHE_PIX = os.path.join(ROOT, "cache", "pix.json.gz")
UA = {"User-Agent": "RadarPolitico/1.0 (+https://github.com/sorezmkt/radar-politico)"}

URL_EMENDAS = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
URL_TE = "https://api.transferegov.gestao.gov.br/transferenciasespeciais/"
LINK_EMENDA = "https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda={}"
LINK_TE = "https://www.gov.br/transferegov/pt-br/manuais/transferencias-especiais"

HOJE = dt.date.today()
ANO_INI = 2020  # primeiro ano das emendas Pix e das emendas de relator; antes disso o Portal tem muitos códigos em branco
ANOS = list(range(ANO_INI, HOJE.year + 1))
T0 = time.time()
status = {"avisos": [], "contagens": {}}


def log(msg):
    print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)


def aviso(msg):
    print("AVISO:", msg, flush=True)
    status["avisos"].append(msg)


def baixar(url, tentativas=4, timeout=300, cab=None):
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={**UA, **(cab or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                raise
            erro = e
        except Exception as e:  # noqa: BLE001
            erro = e
        time.sleep(5 * (i + 1))
    raise erro


def salvar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def num(s):
    s = (s or "").strip()
    if not s:
        return 0.0
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def chave_nome(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z ]", " ", s).split())


def r2(v):
    return round(v or 0.0, 2)


# ---------------------------------------------------------------- classificações

TIPOS = {
    "Emenda Individual - Transferências com Finalidade Definida": "individual",
    "Emenda Individual - Transferências Especiais": "pix",
    "Emenda de Bancada": "bancada",
    "Emenda de Comissão": "comissao",
    "Emenda de Relator": "relator",
}
INDIVIDUAIS = ("individual", "pix")

BANCOS = {"00000000000191": "Banco do Brasil", "00360305000104": "Caixa Econômica Federal"}

EMPRESA = ("Sociedade Empresária", "Sociedade Anônima", "Empresário (Individual)", "Sociedade Simples", "Consórcio de Sociedades",
           "Estabelecimento, no Brasil, de Sociedade Estrangeira", "Empresa Simples de Inovação", "Cooperativa", "Empresa Individual")
ENTIDADE = ("Associação Privada", "Fundação Privada", "Organização Social", "Organização Religiosa", "Entidade Sindical",
            "Serviço Social Autônomo", "Organização da Sociedade Civil")
PUBLICO = ("Município", "Fundo Público", "Estado ou Distrito Federal", "Órgão Público", "Autarquia", "Fundação Pública",
           "Consórcio Público", "Empresa Pública", "Sociedade de Economia Mista", "Poder")

GRUPOS = {
    "publico": "Prefeituras, estados e órgãos públicos",
    "banco": "Caixa e Banco do Brasil (repassam a obras e convênios)",
    "entidade": "Associações, fundações e outras entidades privadas sem fins lucrativos",
    "empresa": "Empresas privadas",
    "pf": "Pessoas físicas",
    "outro": "Outros ou sem informação",
}


def grupo_favorecido(codigo, natureza, tipo):
    if codigo in BANCOS:
        return "banco"
    if tipo == "Pessoa Fisica" or "Pessoa Física" in (natureza or ""):
        return "pf"
    n = natureza or ""
    if any(n.startswith(x) for x in ENTIDADE):
        return "entidade"
    if any(n.startswith(x) for x in EMPRESA):
        return "empresa"
    if any(x in n for x in PUBLICO):
        return "publico"
    return "outro"


def tipo_emenda(txt):
    return TIPOS.get((txt or "").strip())


def pago_total(e):
    """Pago até agora: o que foi pago no próprio ano mais os restos a pagar pagos depois. Nunca soma o empenhado."""
    return (e.get("pago") or 0) + (e.get("rp_pago") or 0)


def pendente(e):
    """Reservado (empenhado) que ainda não foi pago nem cancelado. Nunca negativo."""
    return max(0.0, (e.get("emp") or 0) - pago_total(e) - (e.get("rp_canc") or 0))


# ---------------------------------------------------------------- leitura do Portal da Transparência

def ler_csv(z, nome):
    arq = next(n for n in z.namelist() if n.lower() == nome.lower())
    fh = io.TextIOWrapper(z.open(arq), encoding="latin-1", newline="")
    return csv.DictReader(fh, delimiter=";")


def carregar_emendas(z):
    """Uma entrada por código de emenda; linhas repetidas do mesmo código (outra ação ou localidade) somam valores da mesma etapa."""
    ems = {}
    sem_codigo = Counter()
    for r in ler_csv(z, "EmendasParlamentares.csv"):
        try:
            ano = int(r["Ano da Emenda"])
        except ValueError:
            continue
        if ano < ANO_INI:
            continue
        tp = tipo_emenda(r["Tipo de Emenda"])
        cod = (r["Código da Emenda"] or "").strip()
        if not tp:
            continue
        if not cod.isdigit():
            sem_codigo[tp] += 1
            continue
        e = ems.get(cod)
        if e is None:
            e = ems[cod] = {
                "cod": cod, "ano": ano, "tipo": tp, "autor": (r["Nome do Autor da Emenda"] or "").strip(),
                "cod_autor": r["Código do Autor da Emenda"], "numero": r["Número da emenda"],
                "locais": Counter(), "ufs": Counter(), "munis": {}, "funcoes": Counter(), "acoes": Counter(),
                "emp": 0.0, "liq": 0.0, "pago": 0.0, "rp_pago": 0.0, "rp_canc": 0.0,
            }
        v = {"emp": num(r["Valor Empenhado"]), "liq": num(r["Valor Liquidado"]), "pago": num(r["Valor Pago"]),
             "rp_pago": num(r["Valor Restos A Pagar Pagos"]), "rp_canc": num(r["Valor Restos A Pagar Cancelados"])}
        for k, x in v.items():
            e[k] += x
        peso = v["emp"] or 1.0
        e["locais"][r["Localidade de aplicação do recurso"]] += peso
        uf = sigla_uf(r["UF"])
        if uf:
            e["ufs"][uf] += peso
        ibge = (r["Código Município IBGE"] or "").strip()
        if ibge.isdigit() and len(ibge) == 7:
            m = e["munis"].setdefault(ibge, {"nome": r["Município"].strip(), "uf": uf, "emp": 0.0, "pago": 0.0})
            m["emp"] += v["emp"]
            m["pago"] += v["pago"] + v["rp_pago"]
        e["funcoes"][r["Nome Função"]] += peso
        e["acoes"][r["Nome Ação"]] += peso
    if sem_codigo:
        status["contagens"]["linhas_sem_codigo"] = dict(sem_codigo)
    return ems


UFS = {"ACRE": "AC", "ALAGOAS": "AL", "AMAPÁ": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARÁ": "CE", "DISTRITO FEDERAL": "DF",
       "ESPÍRITO SANTO": "ES", "GOIÁS": "GO", "MARANHÃO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
       "PARÁ": "PA", "PARAÍBA": "PB", "PARANÁ": "PR", "PERNAMBUCO": "PE", "PIAUÍ": "PI", "RIO DE JANEIRO": "RJ",
       "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDÔNIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC",
       "SÃO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO"}


def sigla_uf(nome):
    return UFS.get((nome or "").strip().upper())


def carregar_favorecidos(z, ems):
    """Quem recebeu o dinheiro de cada emenda (pagamentos efetivos, por mês)."""
    fav = defaultdict(lambda: defaultdict(lambda: {"valor": 0.0}))
    n = 0
    for r in ler_csv(z, "EmendasParlamentares_PorFavorecido.csv"):
        cod = (r["Código da Emenda"] or "").strip()
        if cod not in ems:
            continue
        doc = re.sub(r"\D", "", r["Código do Favorecido"] or "")
        if not doc:
            doc = "?" + (r["Favorecido"] or "")[:40]
        f = fav[cod][doc]
        f["valor"] += num(r["Valor Recebido"])
        f.setdefault("nome", (r["Favorecido"] or "").strip())
        f.setdefault("natureza", (r["Natureza Jurídica"] or "").strip())
        f.setdefault("grupo", grupo_favorecido(doc, r["Natureza Jurídica"], r["Tipo Favorecido"]))
        f.setdefault("uf", (r["UF Favorecido"] or "").strip())
        f.setdefault("municipio", (r["Município Favorecido"] or "").strip())
        am = (r["Ano/Mês"] or "").strip()
        if am and am > f.get("ultimo", ""):
            f["ultimo"] = am
        n += 1
    status["contagens"]["favorecidos_linhas"] = n
    return fav


def carregar_convenios(z, ems):
    conv = defaultdict(list)
    for r in ler_csv(z, "EmendasParlamentares_Convenios.csv"):
        cod = (r["Código da Emenda"] or "").strip()
        if cod not in ems:
            continue
        conv[cod].append({"numero": r["Número Convênio"].strip(), "convenente": r["Convenente"].strip(), "objeto": r["Objeto Convênio"].strip(),
                          "valor": num(r["Valor Convênio"]), "data": r["Data Publicação Convênio"].strip()})
    return conv


# ---------------------------------------------------------------- Transferegov (emendas Pix)

PK = {"plano_acao_especial": "id_plano_acao", "plano_trabalho_especial": "id_plano_trabalho",
      "relatorio_gestao_novo_especial": "id_relatorio_gestao_novo", "relatorio_gestao_especial": "id_relatorio_gestao"}


def tabela_te(tab, campos, passo=1000):
    """A API devolve no máximo 1000 linhas por consulta; pagina pela chave primária."""
    out, off = [], 0
    while True:
        url = f"{URL_TE}{tab}?select={','.join(campos)}&order={PK[tab]}&limit={passo}&offset={off}"
        d = json.loads(baixar(url, timeout=120))
        out += d
        time.sleep(0.4)  # a API bloqueia (403) quem consulta rápido demais
        if len(d) < passo:
            return out
        off += passo


def baixar_pix():
    """Baixa as tabelas do Transferegov. Devolve None se a API não responder."""
    try:
        pa = tabela_te("plano_acao_especial", ["id_plano_acao", "codigo_plano_acao", "ano_plano_acao", "situacao_plano_acao",
                                                "cnpj_beneficiario_plano_acao", "nome_beneficiario_plano_acao", "uf_beneficiario_plano_acao",
                                                "numero_emenda_parlamentar_plano_acao", "valor_custeio_plano_acao", "valor_investimento_plano_acao",
                                                "motivo_impedimento_plano_acao"])
        pt = tabela_te("plano_trabalho_especial", ["id_plano_trabalho", "id_plano_acao", "situacao_plano_trabalho",
                                                    "data_inicio_execucao_plano_trabalho", "data_fim_execucao_plano_trabalho"])
        rgn = tabela_te("relatorio_gestao_novo_especial", ["id_relatorio_gestao_novo", "id_plano_acao", "tipo_relatorio_gestao_novo",
                                                            "situacao_relatorio_gestao_novo", "data_e_hora_relatorio_gestao_novo"])
        rg = tabela_te("relatorio_gestao_especial", ["id_relatorio_gestao", "id_plano_acao", "situacao_relatorio_gestao"])
    except Exception as e:  # noqa: BLE001
        aviso(f"Transferegov não respondeu nesta rodada ({e}).")
        return None
    trab = defaultdict(list)
    for r in pt:
        trab[r["id_plano_acao"]].append({"data_fim_execucao_plano_trabalho": r["data_fim_execucao_plano_trabalho"],
                                         "situacao": r["situacao_plano_trabalho"]})
    rel = defaultdict(list)
    for r in rgn:
        rel[r["id_plano_acao"]].append({"tipo": r["tipo_relatorio_gestao_novo"], "situacao": r["situacao_relatorio_gestao_novo"],
                                        "data": (r["data_e_hora_relatorio_gestao_novo"] or "")[:10]})
    for r in rg:
        rel[r["id_plano_acao"]].append({"tipo": "Antigo", "situacao": r["situacao_relatorio_gestao"]})
    planos = []
    for p in pa:
        p["trabalho"] = trab.get(p["id_plano_acao"], [])
        p["relatorios"] = rel.get(p["id_plano_acao"], [])
        planos.append(p)
    return planos


def carregar_pix():
    """
    Planos de ação das transferências especiais, com plano de trabalho e relatórios de gestão, indexados pelo código da emenda.
    Quando a API falha, usa a última cópia boa guardada em cache/pix.json.gz e avisa a data dela.
    """
    planos = baixar_pix()
    if planos:
        os.makedirs(os.path.dirname(CACHE_PIX), exist_ok=True)
        with gzip.open(CACHE_PIX, "wt", encoding="utf-8") as f:
            json.dump({"data": HOJE.isoformat(), "planos": planos}, f, ensure_ascii=False, separators=(",", ":"))
        status["pix_data"] = HOJE.isoformat()
    elif os.path.exists(CACHE_PIX):
        with gzip.open(CACHE_PIX, "rt", encoding="utf-8") as f:
            c = json.load(f)
        planos = c["planos"]
        status["pix_data"] = c["data"]
        aviso(f"Usando a cópia do Transferegov de {c['data']}.")
    else:
        return None
    status["contagens"]["pix_planos_acao"] = len(planos)
    log(f"Transferegov: {len(planos)} planos de ação (dados de {status['pix_data']})")
    por_emenda = defaultdict(list)
    for p in planos:
        por_emenda[str(p["numero_emenda_parlamentar_plano_acao"] or "")].append(p)
    return por_emenda


def data_iso(s):
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


MARGEM_RELATORIO = 180  # dias depois do fim da execução antes de tratar o relatório final como não localizado


def situacao_plano_pix(p, hoje=HOJE):
    """
    Situação documental de um plano de ação de emenda Pix:
      "ok"          relatório final (ou relatório do sistema antigo) disponibilizado
      "atrasado"    a execução terminou há mais de 180 dias e não há relatório final disponibilizado
      "sem_plano"   plano de ação de 2024 em diante, com mais de um ano, sem plano de trabalho cadastrado
      "andamento"   ainda dentro do prazo, ou sem prazo informado
    """
    rels = p.get("relatorios") or []
    if any(r["situacao"] == "DISPONIBILIZADO" and r["tipo"] in ("Final", "Antigo") for r in rels):
        return "ok", None
    trabalhos = p.get("trabalho") or []
    fins = [d for d in (data_iso(t.get("data_fim_execucao_plano_trabalho")) for t in trabalhos) if d]
    if fins:
        fim = max(fins)
        if (hoje - fim).days > MARGEM_RELATORIO:
            return "atrasado", fim
        return "andamento", fim
    if not trabalhos and 2024 <= (p.get("ano_plano_acao") or 0) <= hoje.year - 2:
        return "sem_plano", None
    return "andamento", None


# ---------------------------------------------------------------- deputados

def carregar_deputados():
    with open(os.path.join(DATA, "index.json"), encoding="utf-8") as f:
        idx = json.load(f)
    deps = idx["deputados"] if isinstance(idx, dict) else idx
    por_nome = defaultdict(list)
    for d in deps:
        por_nome[chave_nome(d["nome"])].append(d)
    return deps, por_nome


def autor_do_deputado(ems, por_nome):
    """Liga o autor de cada emenda individual a um deputado em exercício só quando o nome é único na Câmara."""
    ligados = {}
    for e in ems.values():
        if e["tipo"] not in INDIVIDUAIS:
            continue
        cand = por_nome.get(chave_nome(e["autor"]), [])
        if len(cand) == 1:
            ligados[e["cod"]] = cand[0]["id"]
    return ligados


# ---------------------------------------------------------------- regras de alerta do deputado

def fmt(v):
    return ("R$ {:,.2f}".format(v or 0)).replace(",", "X").replace(".", ",").replace("X", ".")


def regra_pix(emendas_dep, pix, media=None):
    """Emendas Pix com prestação de contas não localizada no Transferegov depois do fim do prazo de execução."""
    alvo = [e for e in emendas_dep if e["tipo"] == "pix" and pago_total(e) > 0]
    base = {"id": "pix", "titulo": "Prestação de contas das emendas Pix"}
    if not alvo:
        return {**base, "status": "nd", "texto": "Não há emenda Pix (transferência especial) paga neste período.", "registros": []}
    if pix is None:
        return {**base, "status": "nd", "texto": "O Transferegov não respondeu nesta atualização; a conferência volta na próxima.", "registros": []}
    regs, atras, sem_plano, sem_registro, valor_atras, valor_sem_plano = [], 0, 0, 0, 0.0, 0.0
    for e in alvo:
        planos = pix.get(e["cod"], [])
        if not planos:
            sem_registro += 1
            continue
        for p in planos:
            sit, fim = situacao_plano_pix(p)
            if sit not in ("atrasado", "sem_plano"):
                continue
            valor = (p.get("valor_custeio_plano_acao") or 0) + (p.get("valor_investimento_plano_acao") or 0)
            if sit == "atrasado":
                atras += 1
                valor_atras += valor
                desc = f"execução terminou em {fim:%d/%m/%Y} e o relatório final não foi localizado"
            else:
                sem_plano += 1
                valor_sem_plano += valor
                desc = "plano de trabalho não cadastrado"
            regs.append({"emenda": e["cod"], "ano": e["ano"], "beneficiario": p.get("nome_beneficiario_plano_acao") or "",
                         "uf": p.get("uf_beneficiario_plano_acao") or "", "plano": p.get("codigo_plano_acao") or "",
                         "valor": r2(valor), "descricao": desc, "link": LINK_EMENDA.format(e["cod"])})
    regs.sort(key=lambda r: -r["valor"])
    if not regs:
        txt = f"As {len(alvo)} emendas Pix pagas têm relatório de gestão entregue ou ainda estão dentro do prazo de execução."
        if sem_registro:
            txt += f" {sem_registro} não aparecem no Transferegov, que só registra os planos de ação a partir de 2020."
        return {**base, "status": "good", "texto": txt, "registros": []}
    partes = []
    if atras:
        partes.append(f"{atras} {'plano' if atras == 1 else 'planos'} com prazo de execução vencido há mais de 6 meses sem relatório final de prestação de contas ({fmt(valor_atras)})")
    if sem_plano:
        partes.append(f"{sem_plano} {'plano' if sem_plano == 1 else 'planos'} de ação sem plano de trabalho cadastrado ({fmt(valor_sem_plano)})")
    pago_pix = sum(pago_total(e) for e in alvo)
    parte = valor_atras / pago_pix * 100 if pago_pix else 0
    if parte >= 40 and valor_atras >= 5_000_000:
        st = "bad"
    elif (parte >= 25 and valor_atras >= 2_000_000) or valor_sem_plano >= 1_000_000:
        st = "warn"
    else:
        st = "good"
    proporcao = f" O valor com prazo vencido equivale a {parte:.0f}% das emendas Pix já pagas deste deputado" + (f" (no país todo, {media:.0f}%)." if media is not None else ".") if atras else ""
    return {**base, "status": st,
            "texto": "No Transferegov aparecem " + " e ".join(partes) + "." + proporcao + " A prestação de contas é de responsabilidade da prefeitura ou do estado que recebeu; "
                     "o relatório pode ter sido entregue por outro meio, por isso cada caso precisa ser conferido.",
            "registros": regs[:30]}


def regra_entidades(favs):
    """Parte do dinheiro pago a associações, fundações e outras entidades privadas sem fins lucrativos."""
    base = {"id": "entidades", "titulo": "Repasses a entidades privadas"}
    total = sum(f["valor"] for f in favs.values())
    ent = sorted((f for f in favs.values() if f["grupo"] == "entidade" and f["valor"] > 0), key=lambda f: -f["valor"])
    if total <= 0:
        return {**base, "status": "nd", "texto": "Sem pagamentos registrados por favorecido.", "registros": []}
    v = sum(f["valor"] for f in ent)
    pct = v / total * 100
    regs = [{"nome": f["nome"], "doc": f["doc"], "natureza": f["natureza"], "municipio": f["municipio"], "uf": f["uf"], "valor": r2(f["valor"])} for f in ent[:15]]
    if not ent:
        return {**base, "status": "good", "texto": "Nenhum pagamento das emendas foi feito diretamente a entidades privadas sem fins lucrativos.", "registros": []}
    txt = (f"{fmt(v)} ({pct:.0f}% do que foi pago) foram para {len(ent)} {'entidade privada' if len(ent) == 1 else 'entidades privadas'} sem fins lucrativos. "
           "Esse caminho exige conferência mais cuidadosa porque quem executa não é um órgão público e a fiscalização depende da prestação de contas da própria entidade.")
    st = "warn" if (pct >= 25 and v >= 5_000_000) or ent[0]["valor"] >= 10_000_000 else "good"
    return {**base, "status": st, "texto": txt, "registros": regs}


def regra_empresas(favs):
    """Pagamentos feitos diretamente a empresas privadas com dinheiro das emendas."""
    base = {"id": "empresas", "titulo": "Empresas que receberam direto"}
    emp = sorted((f for f in favs.values() if f["grupo"] == "empresa" and f["valor"] > 0), key=lambda f: -f["valor"])
    if not emp:
        return {**base, "status": "good", "texto": "Nenhum pagamento das emendas foi feito diretamente a empresas privadas.", "registros": []}
    v = sum(f["valor"] for f in emp)
    total = sum(f["valor"] for f in favs.values()) or 1
    grandes = [f for f in emp if f["valor"] >= 3_000_000]
    regs = [{"nome": f["nome"], "doc": f["doc"], "natureza": f["natureza"], "municipio": f["municipio"], "uf": f["uf"], "valor": r2(f["valor"])} for f in emp[:15]]
    txt = (f"{fmt(v)} foram pagos diretamente a {len(emp)} {'empresa' if len(emp) == 1 else 'empresas'}, em geral por compras feitas pelo próprio governo federal "
           "com o dinheiro da emenda.")
    if grandes:
        txt += f" {len(grandes)} {'recebeu' if len(grandes) == 1 else 'receberam'} R$ 3 milhões ou mais, o que vale conferir no contrato correspondente."
    st = "warn" if grandes or v / total >= 0.15 else "good"
    if v / total >= 0.15:
        txt += f" As empresas ficaram com {v / total * 100:.0f}% de tudo o que foi pago, bem acima do comum entre os deputados."
    return {**base, "status": st, "texto": txt, "registros": regs}


def regra_fora_estado(emendas_dep, uf_dep):
    """Parte das emendas destinada a cidades ou estados fora do estado que o deputado representa."""
    base = {"id": "fora_estado", "titulo": "Dinheiro enviado para fora do estado"}
    tot, fora, regs = 0.0, 0.0, []
    por_uf = Counter()
    for e in emendas_dep:
        if not e["ufs"]:
            continue
        tot += e["emp"]
        uf, _ = e["ufs"].most_common(1)[0]
        if uf != uf_dep:
            fora += e["emp"]
            por_uf[uf] += e["emp"]
            regs.append({"emenda": e["cod"], "ano": e["ano"], "local": e["local"], "valor": r2(e["emp"]), "link": LINK_EMENDA.format(e["cod"])})
    if tot <= 0:
        return {**base, "status": "nd", "texto": "As emendas não informam o estado de destino.", "registros": []}
    pct = fora / tot * 100
    if fora <= 0:
        return {**base, "status": "good", "texto": f"Todas as emendas com destino informado foram para {uf_dep}, o estado que o deputado representa.", "registros": []}
    ufs = ", ".join(u for u, _ in por_uf.most_common(4))
    txt = f"{pct:.0f}%" if pct >= 1 else "Menos de 1%"
    txt += f" do valor reservado ({fmt(fora)}) foi para fora de {uf_dep} ({ufs})."
    st = "warn" if pct >= 20 and fora >= 1_000_000 else "good"
    if st == "warn":
        txt += " Não é proibido, mas é incomum e vale entender o motivo."
    regs.sort(key=lambda r: -r["valor"])
    return {**base, "status": st, "texto": txt, "registros": regs[:20]}


def regra_inconsistencia(emendas_dep):
    """Emendas em que o Portal mostra mais dinheiro pago do que reservado."""
    base = {"id": "inconsistencia", "titulo": "Valores que não fecham"}
    regs = [{"emenda": e["cod"], "ano": e["ano"], "emp": r2(e["emp"]), "pago": r2(pago_total(e)), "link": LINK_EMENDA.format(e["cod"])}
            for e in emendas_dep if pago_total(e) > e["emp"] * 1.01 + 1000]
    if not regs:
        return {**base, "status": "good", "texto": "Em todas as emendas, o valor pago não passa do valor reservado.", "registros": []}
    return {**base, "status": "warn",
            "texto": f"Em {len(regs)} {'emenda' if len(regs) == 1 else 'emendas'} o Portal registra pagamento maior que o empenho. "
                     "Pode ser reforço de empenho, correção de dados ou erro de cadastro; precisa ser conferido no Portal.",
            "registros": regs[:20]}


def pontos(checks):
    return sum({"bad": 2, "warn": 1}.get(c["status"], 0) for c in checks)


# ---------------------------------------------------------------- montagem

def resumo_emenda(e, fav=None, conv=None, pix=None):
    local = e["locais"].most_common(1)[0][0] if e["locais"] else ""
    o = {"cod": e["cod"], "ano": e["ano"], "tipo": e["tipo"], "numero": e["numero"], "local": local,
         "funcao": e["funcoes"].most_common(1)[0][0] if e["funcoes"] else "", "acao": e["acoes"].most_common(1)[0][0] if e["acoes"] else "",
         "emp": r2(e["emp"]), "pago": r2(pago_total(e)), "pend": r2(pendente(e)), "canc": r2(e["rp_canc"]), "link": LINK_EMENDA.format(e["cod"])}
    if fav:
        top = sorted(fav.items(), key=lambda kv: -kv[1]["valor"])[:3]
        o["fav"] = [{"nome": f["nome"], "grupo": f["grupo"], "valor": r2(f["valor"])} for _, f in top if f["valor"] > 0]
    if conv:
        o["conv"] = [{"numero": c["numero"], "objeto": c["objeto"][:180], "convenente": c["convenente"], "valor": r2(c["valor"])} for c in conv[:3]]
    if pix:
        o["pix"] = []
        for p in pix[:5]:
            sit, fim = situacao_plano_pix(p)
            o["pix"].append({"plano": p.get("codigo_plano_acao"), "beneficiario": p.get("nome_beneficiario_plano_acao"), "situacao": sit,
                             "fim": fim.isoformat() if fim else None})
    return o


def soma(ems, filtro=None):
    t = {"emp": 0.0, "pago": 0.0, "pend": 0.0, "canc": 0.0, "n": 0}
    for e in ems:
        if filtro and not filtro(e):
            continue
        t["emp"] += e["emp"]
        t["pago"] += pago_total(e)
        t["pend"] += pendente(e)
        t["canc"] += e["rp_canc"]
        t["n"] += 1
    return {k: (r2(v) if k != "n" else v) for k, v in t.items()}


def main():
    log("Baixando emendas do Portal da Transparência")
    raw = baixar(URL_EMENDAS, timeout=900)
    z = zipfile.ZipFile(io.BytesIO(raw))
    ems = carregar_emendas(z)
    log(f"{len(ems)} emendas de {ANO_INI} em diante")
    fav = carregar_favorecidos(z, ems)
    conv = carregar_convenios(z, ems)
    log(f"favorecidos de {len(fav)} emendas, convênios de {len(conv)} emendas")
    pix = carregar_pix()
    deps, por_nome = carregar_deputados()
    ligados = autor_do_deputado(ems, por_nome)
    status["contagens"]["emendas"] = len(ems)
    status["contagens"]["emendas_ligadas_a_deputado"] = len(ligados)
    for e in ems.values():
        e["local"] = e["locais"].most_common(1)[0][0] if e["locais"] else ""

    # ---------------- emendas Pix: quadro nacional da prestação de contas
    quadro_pix = None
    if pix is not None:
        sit, val = Counter(), Counter()
        for cod, planos in pix.items():
            e = ems.get(cod)
            if not e or pago_total(e) <= 0:
                continue
            for p in planos:
                s_, _ = situacao_plano_pix(p)
                sit[s_] += 1
                val[s_] += (p.get("valor_custeio_plano_acao") or 0) + (p.get("valor_investimento_plano_acao") or 0)
        quadro_pix = {k: {"n": sit[k], "valor": r2(val[k])} for k in ("ok", "andamento", "atrasado", "sem_plano")}
    tot_pix = sum(x["valor"] for x in quadro_pix.values()) if quadro_pix else 0
    media_pix = quadro_pix["atrasado"]["valor"] / tot_pix * 100 if tot_pix else None

    # ---------------- por deputado
    por_dep = defaultdict(list)
    for cod, did in ligados.items():
        por_dep[did].append(ems[cod])
    lista = []
    for d in deps:
        mine = sorted(por_dep.get(d["id"], []), key=lambda e: (-e["ano"], -e["emp"]))
        favs = {}
        for e in mine:
            for doc, f in fav.get(e["cod"], {}).items():
                g = favs.setdefault(doc, {"doc": doc, "nome": f["nome"], "natureza": f["natureza"], "grupo": f["grupo"],
                                          "uf": f["uf"], "municipio": f["municipio"], "valor": 0.0})
                g["valor"] += f["valor"]
        checks = [regra_pix(mine, pix, media_pix), regra_entidades(favs), regra_empresas(favs), regra_fora_estado(mine, d.get("uf")), regra_inconsistencia(mine)]
        anos = {str(a): soma(mine, lambda e, a=a: e["ano"] == a) for a in ANOS}
        tipos = {t: soma(mine, lambda e, t=t: e["tipo"] == t) for t in INDIVIDUAIS}
        grupos = Counter()
        for f in favs.values():
            grupos[f["grupo"]] += f["valor"]
        munis = defaultdict(lambda: {"emp": 0.0, "pago": 0.0})
        for e in mine:
            for ib, m in e["munis"].items():
                mm = munis[ib]
                mm.update(nome=m["nome"], uf=m["uf"])
                mm["emp"] += m["emp"]
                mm["pago"] += m["pago"]
        areas = Counter()
        for e in mine:
            for fn, p in e["funcoes"].items():
                tot_p = sum(e["funcoes"].values()) or 1
                areas[fn] += e["emp"] * p / tot_p
        tot = soma(mine)
        pts = pontos(checks)
        ficha = {
            "id": d["id"], "nome": d["nome"], "partido": d.get("partido"), "uf": d.get("uf"), "foto": d.get("foto"),
            "total": tot, "anos": anos, "tipos": tipos, "checks": checks, "pontos": pts,
            "grupos": {k: r2(v) for k, v in grupos.most_common()},
            "areas": [[k, r2(v)] for k, v in areas.most_common(10) if v > 0],
            "municipios": sorted(([ib, m["nome"], m["uf"], r2(m["emp"]), r2(m["pago"])] for ib, m in munis.items()), key=lambda x: -x[3])[:40],
            "favorecidos": [{**{k: f[k] for k in ("doc", "nome", "natureza", "grupo", "uf", "municipio")}, "valor": r2(f["valor"])}
                            for f in sorted(favs.values(), key=lambda f: -f["valor"])[:25] if f["valor"] > 0],
            "emendas": [resumo_emenda(e, fav.get(e["cod"]), conv.get(e["cod"]), (pix or {}).get(e["cod"]) if e["tipo"] == "pix" else None) for e in mine],
        }
        salvar(os.path.join(OUT, "dep", f"{d['id']}.json"), ficha)
        lista.append({"id": d["id"], "nome": d["nome"], "partido": d.get("partido"), "uf": d.get("uf"), "foto": d.get("foto"),
                      "emp": tot["emp"], "pago": tot["pago"], "n": tot["n"], "pontos": pts,
                      "bad": sum(c["status"] == "bad" for c in checks), "warn": sum(c["status"] == "warn" for c in checks),
                      "anos": {a: [v["emp"], v["pago"]] for a, v in anos.items() if v["n"]}})
    salvar(os.path.join(OUT, "deputados.json"), {"anos": ANOS, "deputados": lista})

    # ---------------- visão nacional
    resumo = {"atualizado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M"), "anos": ANOS,
              "parcial": HOJE.year, "por_ano": {}, "fontes": {"emendas": URL_EMENDAS, "pix": URL_TE}}
    todas = list(ems.values())
    for a in ANOS:
        ea = [e for e in todas if e["ano"] == a]
        if not ea:
            continue
        ufs, munis, areas, autores, grupos, ents = Counter(), defaultdict(lambda: [0.0, 0.0, "", ""]), Counter(), Counter(), Counter(), Counter()
        nomes_ent = {}
        for e in ea:
            if e["ufs"]:
                ufs[e["ufs"].most_common(1)[0][0]] += e["emp"]
            for ib, m in e["munis"].items():
                mm = munis[ib]
                mm[0] += m["emp"]
                mm[1] += m["pago"]
                mm[2], mm[3] = m["nome"], m["uf"]
            tot_p = sum(e["funcoes"].values()) or 1
            for fn, p in e["funcoes"].items():
                areas[fn] += e["emp"] * p / tot_p
            if e["tipo"] in INDIVIDUAIS:
                autores[e["cod"] in ligados and ligados[e["cod"]] or "x:" + e["autor"]] += e["emp"]
            for doc, f in fav.get(e["cod"], {}).items():
                grupos[f["grupo"]] += f["valor"]
                if f["grupo"] in ("entidade", "empresa"):
                    ents[doc] += f["valor"]
                    nomes_ent[doc] = (f["nome"], f["grupo"], f["municipio"], f["uf"])
        dep_por_id = {d["id"]: d for d in deps}
        top_aut = []
        for k, v in autores.most_common(15):
            if isinstance(k, int) or (isinstance(k, str) and not k.startswith("x:")):
                d = dep_por_id.get(k, {})
                top_aut.append({"id": k, "nome": d.get("nome"), "partido": d.get("partido"), "uf": d.get("uf"), "emp": r2(v)})
            else:
                top_aut.append({"id": None, "nome": k[2:].title(), "emp": r2(v)})
        resumo["por_ano"][str(a)] = {
            "total": soma(ea),
            "tipos": {t: soma(ea, lambda e, t=t: e["tipo"] == t) for t in TIPOS.values()},
            "ufs": [[k, r2(v)] for k, v in ufs.most_common()],
            "areas": [[k, r2(v)] for k, v in areas.most_common(12) if v > 0],
            "municipios": [[ib, m[2], m[3], r2(m[0]), r2(m[1])] for ib, m in sorted(munis.items(), key=lambda kv: -kv[1][0])[:15]],
            "autores": top_aut,
            "grupos": {k: r2(v) for k, v in grupos.most_common()},
            "entidades": [{"doc": doc, "nome": nomes_ent[doc][0], "grupo": nomes_ent[doc][1], "municipio": nomes_ent[doc][2], "uf": nomes_ent[doc][3], "valor": r2(v)}
                          for doc, v in ents.most_common(15)],
        }
    if quadro_pix:
        resumo["pix"] = quadro_pix
        resumo["pix_data"] = status.get("pix_data")
    resumo["sinais"] = sorted(({"id": x["id"], "nome": x["nome"], "partido": x["partido"], "uf": x["uf"], "pontos": x["pontos"], "bad": x["bad"], "warn": x["warn"], "emp": x["emp"]}
                               for x in lista if x["pontos"] > 0), key=lambda x: (-x["pontos"], -x["emp"]))[:40]
    resumo["grupos_nome"] = GRUPOS
    salvar(os.path.join(OUT, "resumo.json"), resumo)

    # ---------------- por cidade (todos os anos do período)
    munis = defaultdict(lambda: {"emp": 0.0, "pago": 0.0, "n": 0, "aut": Counter()})
    for e in todas:
        for ib, m in e["munis"].items():
            mm = munis[ib]
            mm["nome"], mm["uf"] = m["nome"], m["uf"]
            mm["emp"] += m["emp"]
            mm["pago"] += m["pago"]
            mm["n"] += 1
            if e["cod"] in ligados:
                mm["aut"][ligados[e["cod"]]] += m["emp"]
    salvar(os.path.join(OUT, "municipios.json"), [[ib, m["nome"], m["uf"], r2(m["emp"]), r2(m["pago"]), m["n"], [[k, r2(v)] for k, v in m["aut"].most_common(3)]]
                                                  for ib, m in sorted(munis.items(), key=lambda kv: -kv[1]["emp"])])
    status["duracao_s"] = round(time.time() - T0)
    salvar(os.path.join(OUT, "status.json"), status)
    log("Pronto")


if __name__ == "__main__":
    sys.exit(main())
