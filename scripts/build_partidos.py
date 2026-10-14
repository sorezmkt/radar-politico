#!/usr/bin/env python3
"""
Radar Político — robô de dados dos partidos.

Lê as prestações de contas anuais dos diretórios nacionais dos partidos, publicadas pelo
TSE no Portal de Dados Abertos, e gera os arquivos que as páginas de partidos leem:
  data/partidos/index.json      lista de partidos com os números de cada ano
  data/partidos/<slug>.json     ficha completa de cada partido
  data/partidos/status.json     diagnóstico da última execução

Fontes:
  - Prestação de contas anual partidária (receitas e despesas), arquivo do diretório nacional (_BR):
    https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas_anual_partidaria/prestacao_contas_anual_partidaria_<ano>.zip
  - Notas fiscais e comprovantes das despesas (link para o documento no SPCA):
    .../prestacao_contas_anual_partidaria_notafiscal_<ano>.zip
  - IPCA mensal do IBGE via API do Banco Central (série SGS 433), para comparar anos em valores de hoje
  - Situação cadastral de CNPJ dos maiores fornecedores: BrasilAPI / Minha Receita (mesmo cache do robô dos deputados)

Todas as regras de alerta são determinísticas: os mesmos dados de entrada geram sempre os mesmos alertas.
Roda no GitHub Actions toda semana (veja .github/workflows/atualizar-partidos.yml).
"""
import csv
import datetime as dt
import io
import json
import os
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict

csv.field_size_limit(10_000_000)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "partidos")
CACHE_DIR = os.path.join(ROOT, "cache")
CNPJ_CACHE = os.path.join(CACHE_DIR, "cnpj.json")
TSE = os.environ.get("TSE_BASE", "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas_anual_partidaria/")
UA = {"User-Agent": "RadarPolitico/1.0 (+https://github.com/sorezmkt/radar-politico)"}

HOJE = dt.date.today()
ANO_INICIO = int(os.environ.get("ANO_INICIO", "2022"))
ANOS_ELEITORAIS = {a for a in range(2000, 2100, 2)}  # eleições gerais e municipais se alternam a cada 2 anos
LIMITE_CNPJ_NOVOS = int(os.environ.get("LIMITE_CNPJ", "1500"))
TEMPO_MAX_CNPJ = 30 * 60
T0 = time.time()

status = {"avisos": [], "anos": {}, "contagens": {}, "fontes": {}}


def aviso(msg):
    print("AVISO:", msg, flush=True)
    status["avisos"].append(msg)


def log(msg):
    print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)


# ---------------------------------------------------------------- utilidades

def baixar(url, tentativas=4, timeout=600):
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                raise
            erro = e
        except Exception as e:  # noqa: BLE001
            erro = e
        time.sleep(4 * (i + 1))
    raise erro


def norm(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().upper().strip()


def slug(sg):
    return re.sub(r"[^a-z0-9]", "", norm(sg).lower())


def vazio(s):
    s = (s or "").strip()
    return s in ("", "#NULO#", "#NULO", "-1", "-4", "#NE#")


def limpo(s):
    return "" if vazio(s) else s.strip()


def num(s):
    s = (s or "").strip()
    if vazio(s):
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def data_br(s):
    try:
        return dt.datetime.strptime((s or "")[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def ler_csv(z, nome):
    """Lê um CSV do zip do TSE (separador ';'). Os arquivos vêm em Latin-1 ou UTF-8 conforme o ano."""
    b = z.read(nome)
    try:
        t = b.decode("utf-8-sig")
    except UnicodeDecodeError:
        t = b.decode("latin-1")
    rd = csv.reader(io.StringIO(t, newline=""), delimiter=";")
    cab = [c.strip().strip('"') for c in next(rd)]
    for v in rd:
        if len(v) == len(cab):
            yield dict(zip(cab, v))


def percentil(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return vals[int(round(p * (len(vals) - 1)))]


def pct_rank(v, vals):
    """Fração dos valores estritamente menores que v."""
    vals = [x for x in vals if x is not None]
    return sum(1 for x in vals if x < v) / len(vals) if vals else 0.0


def salvar(caminho, obj):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def r2(v):
    return round(v, 2)


def fmt_doc(d):
    d = re.sub(r"\D", "", d or "")
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:  # CPF de pessoa física: mostra só o miolo, como fazem os portais oficiais
        return f"***.{d[3:6]}.{d[6:9]}-**"
    return ""


def brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


def dec(v, casas=1):
    return f"{v:.{casas}f}".replace(".", ",")


def pc(v, casas=1):
    return dec(v * 100, casas) + "%"


def brl_curto(v):
    a = abs(v)
    if a >= 1e9:
        return f"R$ {v / 1e9:.1f} bi".replace(".", ",")
    if a >= 1e6:
        return f"R$ {v / 1e6:.1f} mi".replace(".", ",")
    if a >= 1e3:
        return f"R$ {v / 1e3:.0f} mil"
    return brl(v)


def titulo(s):
    s = (s or "").strip()
    if not s:
        return ""
    if s.isupper() or s.islower():
        menores = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "A", "O"}
        s = " ".join(w.capitalize() if w.upper() not in menores or i == 0 else w.lower() for i, w in enumerate(s.split()))
        s = re.sub(r"\b(Ltda|Me|Epp|Eireli|S/a|S\.a\.?|Sa)\b", lambda m: m.group(0).upper(), s)
    return s


# ---------------------------------------------------------------- classificação

SUFIXOS = (" - ORDINÁRIAS", " - ORDINARIAS", " - MULHERES", " - DESPESAS ELEITORAIS", " - ELEITORAIS")


def finalidade(ds):
    u = ds.upper()
    if u.endswith(" - MULHERES") or "PARTICIPAÇÃO DA MULHER" in u or "PARTICIPACAO DA MULHER" in norm(u):
        return "mulheres"
    if u.endswith("ELEITORAIS"):
        return "eleitoral"
    return "ordinaria"


def base_gasto(ds):
    """Tira o sufixo de finalidade (ordinária, mulheres, eleitoral) da descrição do gasto."""
    s = ds.strip()
    for suf in SUFIXOS:
        if s.upper().endswith(suf):
            return s[: -len(suf)].strip()
    return s


# categorias amplas mostradas na página, a partir do início da descrição oficial
CATEGORIAS = [
    ("PESSOAL", "Pessoal e encargos"),
    ("SERVIÇOS TÉCNICO-PROFISSIONAIS - SERVIÇOS DE CONSULTORIA JURÍDICA", "Advocacia e consultoria jurídica"),
    ("SERVIÇOS TÉCNICO-PROFISSIONAIS - SERVIÇOS CONTÁBEIS", "Contabilidade"),
    ("SERVIÇOS TÉCNICO-PROFISSIONAIS - SERVIÇOS DE INFORMÁTICA", "Informática"),
    ("SERVIÇOS TÉCNICO-PROFISSIONAIS", "Outros serviços técnicos e profissionais"),
    ("FUNDAÇÃO DE PESQUISA", "Repasse à fundação partidária"),
    ("TRANSPORTES E VIAGENS", "Viagens e transporte"),
    ("PROPAGANDA", "Propaganda e publicidade"),
    ("DESPESAS COM PUBLICIDADE", "Propaganda e publicidade"),
    ("OUTRAS DESPESAS COM PROPAGANDA", "Propaganda e publicidade"),
    ("PRODUÇÃO DE AUDIOVISUAIS", "Propaganda e publicidade"),
    ("RÁDIO E TELEVISÃO", "Propaganda e publicidade"),
    ("DESPESAS COM IMPULSIONAMENTO", "Propaganda e publicidade"),
    ("DESPESAS COM CRIAÇÃO E INCLUSÃO DE PÁGINAS", "Propaganda e publicidade"),
    ("EVENTOS", "Eventos, congressos e seminários"),
    ("CONGRESSOS", "Eventos, congressos e seminários"),
    ("SEMINÁRIOS", "Eventos, congressos e seminários"),
    ("PESQUISAS", "Pesquisas de opinião"),
    ("ALUGUÉIS", "Aluguéis e condomínios"),
    ("RECOLHIMENTOS AO ERÁRIO", "Devoluções ao Tesouro e multas"),
    ("DESPESAS JUDICIAIS", "Despesas judiciais"),
    ("DEPÓSITOS RESTITUÍVEIS", "Despesas judiciais"),
    ("TRIBUTOS", "Tributos"),
    ("DESPESAS FINANCEIRAS", "Tarifas bancárias e juros"),
    ("ATIVO PERMANENTE", "Compra de bens (imóveis, móveis e equipamentos)"),
    ("TELECOMUNICAÇÕES", "Água, luz, telefone e internet"),
    ("ENERGIA", "Água, luz, telefone e internet"),
    ("ÁGUA", "Água, luz, telefone e internet"),
    ("LANCHES", "Alimentação"),
    ("MATERIA", "Materiais"),
    ("OUTRAS DESPESAS GERAIS", "Outras despesas gerais"),
    ("OUTROS", "Outras despesas gerais"),
]


def categoria(ds):
    u = (ds or "").upper()
    for pref, nome in CATEGORIAS:
        if u.startswith(pref):
            return nome
    return "Outras despesas"


# gastos que não são compras de bens ou serviços (ficam fora das regras de fornecedor)
NAO_FORNECEDOR = ("PESSOAL", "TRIBUTOS", "DESPESAS FINANCEIRAS", "FUNDAÇÃO DE PESQUISA", "RECOLHIMENTOS AO ERÁRIO",
                  "DEPÓSITOS RESTITUÍVEIS", "TRANSFERÊNCIAS", "ASSUNÇÃO", "OBRIGAÇÕES DIVERSAS", "ADIANTAMENTOS")
# categorias que naturalmente se repetem com o mesmo valor (folha, contas mensais, aluguel)
REPETEM = NAO_FORNECEDOR + ("ALUGUÉIS", "TELECOMUNICAÇÕES", "ENERGIA", "ÁGUA", "SEGUROS", "ASSINATURAS",
                            "SERVIÇOS DE LIMPEZA", "SEGURANÇA E VIGILÂNCIA")
GENERICAS = ("OUTRAS DESPESAS GERAIS", "OUTROS ORDINÁRIAS", "OUTROS ", "OBRIGAÇÕES DIVERSAS - OUTRAS")
DOC_GENERICO = re.compile(r"^(S\s*/?\s*N|SN|0+|-|\.|X+|NULO|#NULO#?|SEM\s*N.*|NAO\s*HA|N/?A)$", re.I)


PUBLICO = re.compile(r"\b(TRIBUNAL|MINISTERIO|RECEITA FEDERAL|TESOURO|SECRETARIA|PREFEITURA|GOVERNO D[OAE]|UNIAO FEDERAL|PARTIDO|DIRETORIO|COMISSAO PROVISORIA|CAMARA DOS DEPUTADOS|SENADO FEDERAL)\b")


def compra(ds, r=None):
    """Compra de bens e serviços de um fornecedor privado (fora pessoal, tributos, repasses, órgãos públicos e o próprio partido)."""
    if (ds or "").upper().startswith(NAO_FORNECEDOR):
        return False
    if r is not None:
        doc = re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", ""))
        if len(doc) == 14 and doc[:8] == re.sub(r"\D", "", r.get("NR_CNPJ_PRESTADOR_CONTA", ""))[:8]:
            return False
        if PUBLICO.search(norm(r.get("NM_FORNECEDOR"))):
            return False
    return True


def bucket_receita(r):
    ds = r["DS_RECEITA"].upper()
    org = r["DS_TP_ORIGEM_DOACAO"].upper()
    if "COTAS RECEBIDAS" in ds and "FUNDO PARTID" in ds:
        return "fp", "Fundo Partidário (dinheiro público)"
    if "COTAS RECEBIDAS" in ds and "FUNDO ESPECIAL" in ds:
        return "fefc", "Fundo Eleitoral (dinheiro público)"
    if "CONTRIBUIÇÕES - DE PARLAMENTARES" in ds or "CONTRIBUIÇÕES - DE FILIADOS" in ds or ds.startswith("CONTRIBUIÇÕES"):
        return "contrib", "Contribuições de filiados e parlamentares"
    if ds.startswith("DOAÇÕES") and ("FÍSICAS" in ds or "PESSOAS F" in org):
        return "pf", "Doações de pessoas físicas"
    if "FINANCIAMENTO COLETIVO" in ds:
        return "pf", "Doações de pessoas físicas"
    if "TRANSFER" in ds or "DIREÇ" in ds or "PARTIDOS POL" in org:
        return "intra", "Repasses de outras direções do partido"
    if "SOBRAS" in ds:
        return "sobras", "Sobras de campanha e da fundação"
    if "JUROS" in ds or "RENDIMENTOS" in ds:
        return "rend", "Rendimentos de aplicações"
    if "ORIGEM NÃO IDENTIFICADA" in ds or "FONTES VEDADAS" in ds:
        return "irreg", "Origem não identificada ou fonte vedada"
    return "outras", "Outras receitas"


# ---------------------------------------------------------------- IPCA

def carregar_ipca():
    """Fator para levar valores de cada ano a preços de dezembro do último ano disponível."""
    try:
        raw = baixar(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial=01/01/{ANO_INICIO}", tentativas=3, timeout=60)
        serie = json.loads(raw)
        indice, acum = {}, 1.0
        for p in serie:
            d = dt.datetime.strptime(p["data"], "%d/%m/%Y").date()
            acum *= 1 + float(p["valor"]) / 100
            indice[(d.year, d.month)] = acum
        ult = max(indice)
        fat = {}
        for a in range(ANO_INICIO, ult[0] + 1):
            meses = [indice[(a, m)] for m in range(1, 13) if (a, m) in indice]
            if meses:  # preço médio do ano -> preço do último mês disponível
                fat[a] = indice[ult] / (sum(meses) / len(meses))
        status["fontes"]["ipca"] = f"IPCA até {ult[1]:02d}/{ult[0]}"
        return fat, f"{ult[1]:02d}/{ult[0]}"
    except Exception as e:  # noqa: BLE001
        aviso(f"IPCA indisponível ({e}); comparações entre anos ficam em valores nominais")
        return {}, None


# ---------------------------------------------------------------- leitura dos arquivos do TSE

def carregar_ano(ano):
    try:
        raw = baixar(TSE + f"prestacao_contas_anual_partidaria_{ano}.zip")
    except urllib.error.HTTPError as e:
        aviso(f"{ano}: arquivo de contas ainda não publicado pelo TSE (HTTP {e.code})")
        return None
    z = zipfile.ZipFile(io.BytesIO(raw))
    nomes = z.namelist()
    dsp = next((n for n in nomes if re.search(rf"despesa_anual_{ano}_BR\.csv$", n)), None)
    rec = next((n for n in nomes if re.search(rf"receita_anual_{ano}_BR\.csv$", n)), None)
    if not dsp or not rec:
        aviso(f"{ano}: arquivos do diretório nacional não encontrados no zip ({len(nomes)} arquivos)")
        return None
    despesas = list(ler_csv(z, dsp))
    receitas = list(ler_csv(z, rec))
    geracao = next((r["DT_GERACAO"] for r in despesas if r.get("DT_GERACAO")), "")
    # comprovantes (link para o documento no SPCA)
    nf_sq, nf_chave, tem_nf = {}, {}, False
    try:
        zn = zipfile.ZipFile(io.BytesIO(baixar(TSE + f"prestacao_contas_anual_partidaria_notafiscal_{ano}.zip")))
        nfn = next((n for n in zn.namelist() if re.search(r"_BR\.csv$", n)), None)
        if nfn:
            tem_nf = True
            for r in ler_csv(zn, nfn):
                url = limpo(r.get("NM_URL"))
                if not url.startswith("https://"):
                    continue
                sq = limpo(r.get("SQ_DESPESA"))
                if sq:
                    nf_sq.setdefault(sq, url)
                chave = (re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", "")), limpo(r.get("NR_DOCUMENTO")), round(num(r.get("VR_DOCUMENTO")), 2))
                nf_chave.setdefault(chave, url)
    except urllib.error.HTTPError as e:
        aviso(f"{ano}: arquivo de comprovantes não publicado (HTTP {e.code})")
    except Exception as e:  # noqa: BLE001
        aviso(f"{ano}: falha ao ler comprovantes ({e})")
    status["anos"][ano] = {"despesas": len(despesas), "receitas": len(receitas), "comprovantes": len(nf_sq) + len(nf_chave), "geracao": geracao}
    log(f"{ano}: {len(despesas)} despesas, {len(receitas)} receitas, {len(nf_sq)} comprovantes ligados por sequencial")
    return {"despesas": despesas, "receitas": receitas, "geracao": geracao, "nf_sq": nf_sq, "nf_chave": nf_chave, "tem_nf": tem_nf}


def valor_despesa(r):
    g = num(r.get("VR_GASTO"))
    return g if g > 0 else num(r.get("VR_PAGAMENTO"))


def link_doc(r, A):
    sq = limpo(r.get("SQ_DESPESA"))
    if sq and sq in A["nf_sq"]:
        return A["nf_sq"][sq]
    chave = (re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", "")), limpo(r.get("NR_DOCUMENTO")), round(num(r.get("VR_DOCUMENTO")), 2))
    return A["nf_chave"].get(chave, "")


def registro(r, A, valor=None):
    """Linha de despesa no formato exibido na página."""
    return {
        "data": limpo(r.get("DT_PAGAMENTO")),
        "fornecedor": titulo(limpo(r.get("NM_FORNECEDOR"))) or "Fornecedor não informado",
        "doc": fmt_doc(r.get("NR_CPF_CNPJ_FORNECEDOR")),
        "descricao": limpo(r.get("DS_GASTO")),
        "numero": limpo(r.get("NR_DOCUMENTO")),
        "tipo_doc": limpo(r.get("DS_TP_DOCUMENTO")),
        "fonte": limpo(r.get("DS_FONTE_DESPESA")),
        "valor": r2(valor if valor is not None else valor_despesa(r)),
        "url": link_doc(r, A),
    }


# ---------------------------------------------------------------- CNPJ

def consultar_cnpjs(cnpjs):
    try:
        with open(CNPJ_CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except (FileNotFoundError, ValueError):
        cache = {}
    limite_idade = (HOJE - dt.timedelta(days=60)).isoformat()
    novos = [c for c in sorted(cnpjs) if c not in cache or cache[c].get("ts", "") < limite_idade]
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
        time.sleep(0.35)
    salvar(CNPJ_CACHE, cache)
    status["contagens"]["cnpj_consultados_agora"] = feitos
    status["fontes"]["cnpj"] = len(cache) > 0
    return cache


# ---------------------------------------------------------------- montagem por partido e ano

def resumo_ano(sg, ano, D, R, A):
    G = [r for r in D if r.get("TP_DESPESA") == "G" and valor_despesa(r) > 0]
    T = [r for r in D if r.get("TP_DESPESA") == "D" and valor_despesa(r) > 0]
    sem_mov = not G and not T and not any(num(r.get("VR_RECEITA")) > 0 for r in R)

    # receitas
    buckets, rot = defaultdict(float), {}
    estimavel, total_rec = 0.0, 0.0
    doadores = defaultdict(float)
    nomes_doador = {}
    for r in R:
        v = num(r.get("VR_RECEITA"))
        if v <= 0:
            continue
        if "ESTIM" in r.get("DS_TP_NATUREZA_RECURSO", "").upper():
            estimavel += v
            continue
        k, nome = bucket_receita(r)
        buckets[k] += v
        rot[k] = nome
        total_rec += v
        dk = re.sub(r"\D", "", r.get("NR_CPF_CNPJ_DOADOR", "")) or norm(r.get("NM_DOADOR"))
        proprio = len(dk) == 14 and dk[:8] == re.sub(r"\D", "", r.get("NR_CNPJ_PRESTADOR_CONTA", ""))[:8]
        if k in ("pf", "contrib", "outras") and not proprio and "TRIBUNAL SUPERIOR ELEITORAL" not in r.get("NM_DOADOR", "").upper():
            doadores[dk] += v
            nomes_doador[dk] = titulo(limpo(r.get("NM_DOADOR"))) or "Não informado"
    publico = buckets.get("fp", 0) + buckets.get("fefc", 0)
    receitas = {
        "total": r2(total_rec),
        "publico": r2(publico),
        "estimavel": r2(estimavel),
        "por_origem": [{"id": k, "nome": rot[k], "valor": r2(v)} for k, v in sorted(buckets.items(), key=lambda x: -x[1])],
        "maiores_doadores": [{"nome": nomes_doador[k], "tipo": "PJ" if len(k) == 14 else "PF", "valor": r2(v)}
                             for k, v in sorted(doadores.items(), key=lambda x: -x[1])[:10]],
    }

    # gastos com bens, serviços e pessoal
    total_g = sum(valor_despesa(r) for r in G)
    por_fonte = defaultdict(float)
    cats = defaultdict(lambda: [0.0, defaultdict(float)])
    mensal = [0.0] * 12
    finalid = defaultdict(float)
    for r in G:
        v = valor_despesa(r)
        por_fonte[limpo(r.get("DS_FONTE_DESPESA")) or "Não informada"] += v
        ds = limpo(r.get("DS_GASTO"))
        c = cats[categoria(ds)]
        c[0] += v
        c[1][titulo(base_gasto(ds))] += v
        d = data_br(r.get("DT_PAGAMENTO"))
        if d and d.year == ano:
            mensal[d.month - 1] += v
        finalid[finalidade(ds)] += v

    # fornecedores (somente compras de bens e serviços)
    forn = defaultdict(lambda: {"valor": 0.0, "n": 0, "cats": Counter(), "nome": "", "doc": "", "primeiro": None})
    for r in G:
        ds = limpo(r.get("DS_GASTO"))
        if not compra(ds, r):
            continue
        doc = re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", ""))
        k = doc or norm(r.get("NM_FORNECEDOR"))
        f = forn[k]
        v = valor_despesa(r)
        f["valor"] += v
        f["n"] += 1
        f["cats"][categoria(ds)] += v
        f["nome"] = f["nome"] or titulo(limpo(r.get("NM_FORNECEDOR")))
        f["doc"] = doc
        d = data_br(r.get("DT_PAGAMENTO"))
        if d and (f["primeiro"] is None or d < f["primeiro"]):
            f["primeiro"] = d
    total_compras = sum(f["valor"] for f in forn.values())

    # transferências (para candidatos e outras direções do partido)
    tr = defaultdict(float)
    tr_fonte = defaultdict(float)
    destinos = defaultdict(float)
    nomes_dest = {}
    for r in T:
        v = valor_despesa(r)
        ds = r.get("DS_GASTO", "").upper()
        if "CANDIDATAS NEGRAS" in ds:
            k = "Candidatas negras"
        elif "CANDIDATAS" in ds:
            k = "Candidatas mulheres"
        elif "CANDIDATOS NEGROS" in ds:
            k = "Candidatos negros"
        elif "CANDIDATO" in ds:
            k = "Demais candidatos"
        elif "ESTADUAL" in ds:
            k = "Direções estaduais"
        elif "MUNICIPAL" in ds:
            k = "Direções municipais"
        else:
            k = "Outras direções"
        tr[k] += v
        tr_fonte[limpo(r.get("DS_FONTE_DESPESA")) or "Não informada"] += v
        dk = re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", "")) or norm(r.get("NM_FORNECEDOR"))
        destinos[dk] += v
        nomes_dest[dk] = titulo(limpo(r.get("NM_FORNECEDOR"))) or "Não informado"
    total_t = sum(tr.values())
    cand = sum(v for k, v in tr.items() if k.startswith("Cand") or k.startswith("Demais"))

    # devoluções ao Tesouro e multas (irregularidades já reconhecidas pela Justiça Eleitoral)
    devol = defaultdict(float)
    for r in G:
        ds = r.get("DS_GASTO", "").upper()
        if ds.startswith("RECOLHIMENTOS AO ERÁRIO"):
            devol[titulo(ds.split(" - ", 1)[-1])] += valor_despesa(r)

    # aplicações obrigatórias do Fundo Partidário (Lei 9.096/95, art. 44)
    fp_gasto = defaultdict(float)
    for r in G + T:
        if "FUNDO PARTID" in r.get("DS_FONTE_DESPESA", "").upper():
            ds = r.get("DS_GASTO", "").upper()
            v = valor_despesa(r)
            fp_gasto["total"] += v
            if ds.startswith("FUNDAÇÃO DE PESQUISA"):
                fp_gasto["fundacao"] += v
            if finalidade(ds) == "mulheres":
                fp_gasto["mulheres"] += v

    return {
        "sem_movimento": sem_mov,
        "receitas": receitas,
        "gastos": {
            "total": r2(total_g),
            "por_fonte": {k: r2(v) for k, v in sorted(por_fonte.items(), key=lambda x: -x[1])},
            "categorias": [{"nome": n, "valor": r2(c[0]), "itens": [{"nome": s, "valor": r2(v)} for s, v in sorted(c[1].items(), key=lambda x: -x[1])[:6]]}
                           for n, c in sorted(cats.items(), key=lambda x: -x[1][0])],
            "mensal": [r2(v) for v in mensal],
            "finalidade": {k: r2(v) for k, v in finalid.items()},
            "compras": r2(total_compras),
            "n": len(G),
        },
        "fornecedores_raw": forn,
        "transferencias": {
            "total": r2(total_t),
            "candidatos": r2(cand),
            "direcoes": r2(total_t - cand),
            "por_destino": [{"nome": k, "valor": r2(v)} for k, v in sorted(tr.items(), key=lambda x: -x[1])],
            "por_fonte": {k: r2(v) for k, v in sorted(tr_fonte.items(), key=lambda x: -x[1])},
            "maiores": [{"nome": nomes_dest[k], "doc": fmt_doc(k), "valor": r2(v)} for k, v in sorted(destinos.items(), key=lambda x: -x[1])[:10]],
        },
        "devolucoes": {"total": r2(sum(devol.values())), "itens": [{"nome": k, "valor": r2(v)} for k, v in sorted(devol.items(), key=lambda x: -x[1])]},
        "fundo_partidario": {
            "recebido": r2(buckets.get("fp", 0)),
            "aplicado": r2(fp_gasto["total"]),
            "fundacao": r2(fp_gasto["fundacao"]),
            "mulheres": r2(fp_gasto["mulheres"]),
        },
    }


# ---------------------------------------------------------------- regras de alerta

def alerta(id_, titulo_, st, encontrado, regra, verificar, conclusao, dados=None, valor=None):
    return {"id": id_, "titulo": titulo_, "status": st, "encontrado": encontrado, "regra": regra,
            "verificar": verificar, "conclusao": conclusao, "dados": dados or [], "valor": r2(valor) if valor else None}


def regra_duplicidade(G, A):
    """Alerta 1. O mesmo documento pago mais vezes do que o valor dele, ou pagamentos iguais ao mesmo fornecedor no mesmo dia."""
    por_sq = defaultdict(list)
    for r in G:
        por_sq[limpo(r.get("SQ_DESPESA")) or id(r)].append(r)
    docs = []  # um item por lançamento (várias linhas do mesmo sequencial são parcelas do mesmo lançamento)
    for sq, rs in por_sq.items():
        r0 = rs[0]
        ds = limpo(r0.get("DS_GASTO"))
        if ds.upper().startswith(REPETEM) or not compra(ds, r0):
            continue
        pago = sum(valor_despesa(x) for x in rs)
        vdoc = num(r0.get("VR_DOCUMENTO")) or pago
        if pago < 1000:
            continue
        docs.append({"sq": sq, "r": r0, "pago": pago, "vdoc": vdoc, "data": data_br(r0.get("DT_PAGAMENTO"))})
    fortes_k, fracos_k = defaultdict(list), defaultdict(list)
    for d in docs:
        r = d["r"]
        cnpj = re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", ""))
        if not cnpj:
            continue
        nd = limpo(r.get("NR_DOCUMENTO"))
        if nd and not DOC_GENERICO.match(nd) and len(re.sub(r"\D", "", nd)) >= 2:
            fortes_k[(cnpj, re.sub(r"^0+", "", nd), round(d["vdoc"], 2))].append(d)
        if d["pago"] >= 5000 and not r.get("DS_GASTO", "").upper().startswith("TRANSPORTES E VIAGENS"):
            fracos_k[(cnpj, limpo(r.get("DT_PAGAMENTO")), round(d["pago"], 2))].append(d)
    # documento repetido: mesmo fornecedor, número e valor, lançado em datas próximas (até 10 dias),
    # e a soma paga passa do valor do documento (se não passa, é o mesmo documento dividido entre fontes de recurso)
    fortes = []
    for g in fortes_k.values():
        if len(g) < 2:
            continue
        g = sorted(g, key=lambda d: d["data"] or dt.date.min)
        bloco = [g[0]]
        for d in g[1:] + [None]:
            if d is not None and d["data"] and bloco[-1]["data"] and (d["data"] - bloco[-1]["data"]).days <= 10:
                bloco.append(d)
                continue
            if len(bloco) > 1:
                excesso = sum(x["pago"] for x in bloco) - bloco[0]["vdoc"]
                if excesso >= 0.5 * bloco[0]["vdoc"]:
                    fortes.append((excesso, bloco))
            bloco = [d] if d is not None else []
    vistos = {d["sq"] for _, b in fortes for d in b}
    fracos = []
    for g in fracos_k.values():
        g = [d for d in g if d["sq"] not in vistos]
        if len(g) > 1:
            fracos.append((sum(d["pago"] for d in g[1:]), g))
    fortes.sort(key=lambda x: -x[0]); fracos.sort(key=lambda x: -x[0])
    exc_f = sum(e for e, _ in fortes)
    exc_w = sum(e for e, _ in fracos)
    if exc_f < 10000 and exc_w < 100000:
        txt = "Nenhum documento pago mais de uma vez." if not fortes else f"{len(fortes)} {'documento pago' if len(fortes) == 1 else 'documentos pagos'} de novo em valor pequeno ({brl_curto(exc_f)}), abaixo do limite do alerta."
        if fracos:
            txt += f" Há {len(fracos)} {'caso menor' if len(fracos) == 1 else 'casos menores'} de pagamentos de mesmo valor ao mesmo fornecedor no mesmo dia ({brl_curto(exc_w)}), abaixo do limite do alerta."
        dados = [{"grupo": "Mesmo documento, pago de novo", "registros": [registro(d["r"], A, d["pago"]) for d in b[:4]]} for _, b in fortes[:3]]
        dados += [{"grupo": "Mesmo valor, mesmo dia", "registros": [registro(d["r"], A, d["pago"]) for d in g[:4]]} for _, g in fracos[:3]]
        return alerta("duplicidade", "Possíveis pagamentos duplicados", "good", txt, REGRA_DUP, "", "Nenhuma possível duplicidade relevante encontrada.", dados)
    dados = [{"grupo": "Mesmo documento, pago de novo", "registros": [registro(d["r"], A, d["pago"]) for d in b[:4]]} for _, b in fortes[:6]]
    dados += [{"grupo": "Mesmo valor, mesmo dia", "registros": [registro(d["r"], A, d["pago"]) for d in g[:4]]} for _, g in fracos[:max(2, 8 - len(dados))]]
    st = "bad" if exc_f >= 50000 else "warn"
    partes = []
    if fortes:
        partes.append(f"{len(fortes)} {'documento foi pago' if len(fortes) == 1 else 'documentos foram pagos'} mais de uma vez em poucos dias, com o mesmo fornecedor, número e valor, somando {brl_curto(exc_f)} além do valor do documento")
    if fracos and exc_w >= 100000 or (fortes and fracos):
        partes.append(f"{len(fracos)} {'caso' if len(fracos) == 1 else 'casos'} de pagamentos de mesmo valor ao mesmo fornecedor no mesmo dia, com números de documento diferentes ou genéricos ({brl_curto(exc_w)})")
    return alerta("duplicidade", "Possíveis pagamentos duplicados", st, "; ".join(partes) + ".", REGRA_DUP,
                  "Se os lançamentos são a mesma obrigação registrada duas vezes, parcelas de um mesmo contrato ou serviços diferentes que custam o mesmo valor.",
                  "Há possível duplicidade a verificar. Os registros disponíveis não permitem concluir que houve pagamento indevido.",
                  dados, exc_f + exc_w)


REGRA_DUP = ("Olha as compras de bens e serviços de fornecedores privados. Documento pago de novo: o mesmo fornecedor, número de documento e valor aparecem em lançamentos com até 10 dias de distância, "
             "e a soma paga passa em pelo menos 50% o valor do documento (quando não passa, é só o mesmo documento dividido entre fontes de recurso). "
             "Pagamentos iguais no mesmo dia: mesmo fornecedor, data e valor, a partir de R$ 5 mil, fora viagens. Folha, tributos, tarifas, aluguel e contas mensais ficam de fora porque se repetem por natureza. "
             "Fica amarelo quando os documentos pagos de novo somam R$ 10 mil ou quando os pagamentos iguais no mesmo dia somam R$ 100 mil, e vermelho quando os documentos pagos de novo somam R$ 50 mil.")


def regra_fora_padrao(G, A, ref, fator):
    """Alerta 2. Documentos muito acima do que todos os partidos pagam na mesma subcategoria."""
    achados = []
    por_sq = {}
    for r in G:
        sq = limpo(r.get("SQ_DESPESA")) or str(id(r))
        if sq in por_sq:
            continue
        ds = limpo(r.get("DS_GASTO"))
        if not compra(ds, r):
            continue
        v = num(r.get("VR_DOCUMENTO")) or valor_despesa(r)
        por_sq[sq] = (r, v)
    for sq, (r, v) in por_sq.items():
        k = base_gasto(limpo(r.get("DS_GASTO")))
        st = ref.get(k)
        if not st:
            continue
        vr = v * fator
        if vr >= 100000 and vr > st["p995"] and vr > 30 * st["mediana"]:
            achados.append((vr / st["mediana"], r, v, st))
    if not achados:
        return alerta("fora_padrao", "Valores fora do padrão", "good",
                      "Nenhum documento muito acima do que os partidos costumam pagar na mesma categoria.", REGRA_FP, "",
                      "Nenhum valor fora do padrão.")
    achados.sort(key=lambda x: -x[2])
    total = sum(v for _, _, v, _ in achados)
    dados = []
    for vezes, r, v, st in achados[:8]:
        reg = registro(r, A, v)
        reg["comparacao"] = f"{vezes:.0f} vezes a mediana de {brl(st['mediana'])} paga pelos partidos nesta categoria ({st['n']} documentos comparados)"
        dados.append({"grupo": titulo(base_gasto(limpo(r.get('DS_GASTO')))), "registros": [reg]})
    st = "bad" if len(achados) >= 5 and total >= 5_000_000 else "warn"
    return alerta("fora_padrao", "Valores fora do padrão", st,
                  f"{len(achados)} {'documento custa' if len(achados) == 1 else 'documentos custam'} bem mais do que o normal para a categoria, somando {brl_curto(total)}.",
                  REGRA_FP,
                  "Se o serviço tem tamanho, duração ou quantidade que justifiquem o valor (um contrato anual, um evento nacional, uma campanha inteira) e se há outros orçamentos ou referências de preço.",
                  "Valores altos não significam irregularidade. Indicam onde a comparação com contratos parecidos vale a pena.",
                  dados, total)


REGRA_FP = ("Para cada tipo de compra, junta os documentos de todos os diretórios nacionais em todos os anos, corrigidos pela inflação, e calcula a mediana e o valor que só 0,5% dos documentos ultrapassa. "
            "Entra no alerta o documento de R$ 100 mil ou mais que passa desse limite e custa mais de 30 vezes a mediana. Só tipos de gasto com pelo menos 50 documentos são comparados, e pagamentos a órgãos públicos ficam de fora. "
            "Fica vermelho quando há 5 documentos ou mais e eles somam R$ 5 milhões no ano.")


def regra_concentracao(forn, total_compras, refs_ano, forn_ant):
    """Alerta 3. Quanto o maior fornecedor e os cinco maiores representam nas compras do partido."""
    if total_compras <= 0 or not forn:
        return alerta("concentracao", "Concentração de pagamentos", "nd", "Sem compras de bens e serviços no ano.", REGRA_CONC, "", "Sem dados para avaliar.")
    ords = sorted(forn.values(), key=lambda f: -f["valor"])
    top1 = ords[0]["valor"] / total_compras
    top5 = sum(f["valor"] for f in ords[:5]) / total_compras
    pr = pct_rank(top1, refs_ano)
    st = "bad" if pr >= .9 else "warn" if pr >= .75 else "good"
    dados = [{"grupo": "Maiores fornecedores", "registros": [
        {"fornecedor": f["nome"] or "Não informado", "doc": fmt_doc(f["doc"]), "valor": r2(f["valor"]),
         "descricao": f"{pc(f['valor'] / total_compras)} das compras · {f['n']} lançamentos", "url": ""} for f in ords[:5]]}]
    extra = ""
    k0 = ords[0]["doc"]
    if forn_ant is not None and k0 and k0 not in forn_ant and top1 >= .3:
        extra = f" O maior fornecedor do ano não recebeu nada do diretório nacional no ano anterior."
        if st == "good":
            st = "warn"
    return alerta("concentracao", "Concentração de pagamentos", st,
                  f"O maior fornecedor, {ords[0]['nome'] or 'não informado'}, recebeu {pc(top1)} das compras de bens e serviços, e os cinco maiores receberam {pc(top5)}. "
                  f"A concentração no maior fornecedor é maior que a de {pc(pr, 0)} dos diretórios nacionais no mesmo ano.{extra}",
                  REGRA_CONC,
                  "Se os contratos principais passaram por cotação ou concorrência e se o fornecedor tem estrutura compatível com o volume recebido.",
                  "Concentração alta pode ser normal (um escritório de advocacia que cuida de todo o partido, por exemplo). Mostra onde está a maior parte do dinheiro.",
                  dados, ords[0]["valor"])


REGRA_CONC = ("Considera só compras de bens e serviços de fornecedores privados (fora pessoal, tributos, tarifas, repasse à fundação, devoluções, órgãos públicos e o próprio partido). Calcula a fatia do maior fornecedor e compara com todos os diretórios nacionais do mesmo ano: "
              "fica amarelo quem está acima de 75% deles e vermelho quem está acima de 90%. Também fica amarelo quando o maior fornecedor, com 30% ou mais das compras, não recebia nada no ano anterior.")


def regra_temporal(ano, resumo, historico, fator_ano, fatores):
    """Alerta 4. Mês com gasto muito acima do normal e categorias que saltaram em relação ao próprio histórico."""
    mensal = resumo["gastos"]["mensal"]
    ativos = [v for v in mensal if v > 0]
    achados, dados = [], []
    if len(ativos) >= 6:
        med = statistics.median(ativos)
        for i, v in enumerate(mensal):
            eleitoral = ano in ANOS_ELEITORAIS and 7 <= i + 1 <= 10
            if v > 3 * med and v - med >= 500_000 and not eleitoral:
                achados.append(f"{MESES[i]}: {brl_curto(v)}, {dec(v / med)} vezes o mês típico do ano ({brl_curto(med)})")
    # mesmo tipo de ano (eleitoral x não eleitoral) para a comparação ser justa
    comparavel = [a for a in historico if a < ano and (a in ANOS_ELEITORAIS) == (ano in ANOS_ELEITORAIS)]
    saltos = []
    if comparavel:
        a0 = max(comparavel)
        ant = {c["nome"]: c["valor"] * fatores.get(a0, 1) for c in historico[a0]["gastos"]["categorias"]}
        for c in resumo["gastos"]["categorias"]:
            atual = c["valor"] * fator_ano
            antes = ant.get(c["nome"], 0)
            if atual - antes >= 1_000_000 and (antes == 0 or atual / antes >= 2.5):
                saltos.append((atual - antes, c["nome"], antes, atual))
        saltos.sort(reverse=True)
        for d_, nome, antes, atual in saltos[:5]:
            achados.append(f"{nome}: de {brl_curto(antes)} em {a0} para {brl_curto(atual)} em {ano}" + (f" ({dec(atual / antes)} vezes)" if antes else " (não havia gasto)"))
    if not achados:
        txt = "Nenhum mês muito acima do normal e nenhuma categoria que tenha saltado em relação ao ano comparável anterior."
        if not comparavel:
            txt = "Nenhum mês muito acima do normal. Ainda não há ano anterior do mesmo tipo (eleitoral ou não) para comparar categorias."
        return alerta("temporal", "Padrões no tempo", "good", txt, REGRA_TEMP, "", "Nenhum padrão atípico encontrado.")
    st = "bad" if len(achados) >= 3 else "warn"
    dados = [{"grupo": "O que mudou", "linhas": achados}]
    return alerta("temporal", "Padrões no tempo", st,
                  f"{len(achados)} {'mudança chamou' if len(achados) == 1 else 'mudanças chamaram'} atenção na comparação com o próprio histórico do partido.",
                  REGRA_TEMP,
                  "O motivo do aumento: mudança de sede, novo contrato, congresso nacional, troca de gestão ou fusão com outro partido.",
                  "Mudanças grandes têm muitas explicações legítimas. A comparação aponta onde perguntar.",
                  dados)


REGRA_TEMP = ("Dois testes. Mês atípico: um mês com gasto mais de 3 vezes a mediana dos meses do ano e pelo menos R$ 500 mil acima dela; os meses de julho a outubro dos anos de eleição não entram, porque o gasto sobe por natureza. "
              "Salto de categoria: uma categoria que cresceu R$ 1 milhão ou mais e ficou 2,5 vezes maior que no último ano do mesmo tipo (ano de eleição com ano de eleição), com valores corrigidos pela inflação. "
              "Fica vermelho a partir de 3 mudanças.")


def regra_documental(G, A, ref_doc, parcial=False):
    """Alerta 5. Lançamentos sem número de documento, sem comprovante publicado ou com descrição genérica."""
    total = sum(valor_despesa(r) for r in G)
    if total <= 0:
        return alerta("documental", "Inconsistências documentais", "nd", "Sem gastos no ano.", REGRA_DOC, "", "Sem dados para avaliar."), {}
    sem_num, sem_comp, generico, sem_forn = [], [], [], []
    usa_comp = A["tem_nf"] and not parcial  # no ano em curso o arquivo de comprovantes chega atrasado
    base = 0.0
    for r in G:
        ds = limpo(r.get("DS_GASTO")).upper()
        if ds.startswith(("DESPESAS FINANCEIRAS", "TRIBUTOS", "PESSOAL", "RECOLHIMENTOS")) or not compra("", r):
            continue  # tarifas, impostos, folha, órgãos públicos e o próprio partido costumam não ter nota fiscal
        v = valor_despesa(r)
        base += v
        tem_comp = bool(link_doc(r, A)) if usa_comp else False
        nd = limpo(r.get("NR_DOCUMENTO"))
        if (not nd or DOC_GENERICO.match(nd)) and not tem_comp:
            sem_num.append((v, r))
        if usa_comp and not tem_comp:
            sem_comp.append((v, r))
        if ds.startswith(GENERICAS):
            generico.append((v, r))
        if not re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", "")):
            sem_forn.append((v, r))
    soma = lambda xs: sum(v for v, _ in xs)  # noqa: E731
    base = base or 1
    ind = {
        "sem_numero": soma(sem_num) / base,
        "sem_comprovante": soma(sem_comp) / base if usa_comp else None,
        "generico": soma(generico) / base,
        "sem_fornecedor": soma(sem_forn) / base,
    }
    linhas, piores = [], []
    nomes = {"sem_numero": "sem número de documento (ou com número genérico, como S/N) e sem comprovante publicado",
             "sem_comprovante": "sem comprovante publicado pelo TSE",
             "generico": "com descrição genérica (outras despesas gerais)",
             "sem_fornecedor": "sem CPF ou CNPJ do fornecedor"}
    nivel = 0
    for k, v in ind.items():
        if v is None:
            continue
        refs = ref_doc.get(k, [])
        pr = pct_rank(v, refs) if refs else 0
        s = 2 if (pr >= .9 and v >= .10) else 1 if (pr >= .75 and v >= .03) else 0
        nivel = max(nivel, s)
        linhas.append(f"{pc(v)} do valor gasto {nomes[k]}" + (f", mais que {pc(pr, 0)} dos diretórios nacionais" if s else ""))
        if s:
            piores.append(k)
    st = ["good", "warn", "bad"][nivel]
    exemplos = {"sem_numero": sem_num, "sem_comprovante": sem_comp, "generico": generico, "sem_fornecedor": sem_forn}
    dados = [{"grupo": "Indicadores do ano", "linhas": linhas}]
    for k in piores[:2]:
        xs = sorted(exemplos[k], key=lambda x: -x[0])[:5]
        dados.append({"grupo": "Maiores lançamentos " + nomes[k], "registros": [registro(r, A, v) for v, r in xs]})
    if not usa_comp:
        linhas.append("O arquivo de comprovantes do TSE ainda não está completo para este ano, então esse indicador não foi calculado.")
    return alerta("documental", "Inconsistências documentais", st,
                  "Os lançamentos com documentação incompleta ficaram " + ("acima do padrão dos outros partidos." if nivel else "dentro do padrão dos outros partidos."),
                  REGRA_DOC,
                  "Se os documentos existem no processo de prestação de contas (podem ter sido anexados de outra forma) e o que foi comprado nos lançamentos genéricos.",
                  "Documentação incompleta nos dados abertos não prova que o documento não existe. A Justiça Eleitoral pode ter acesso a peças que não estão nos arquivos públicos.",
                  dados), ind


REGRA_DOC = ("Fora tarifas bancárias, tributos, folha, devoluções e pagamentos a órgãos públicos, mede a fatia do valor gasto em lançamentos sem comprovante no arquivo de notas fiscais do TSE, sem número de documento e sem comprovante, "
             "com descrição genérica ou sem CPF/CNPJ do fornecedor. No ano em curso o indicador de comprovante não é calculado, porque o arquivo do TSE chega atrasado. Cada indicador é comparado com todos os diretórios nacionais do mesmo ano: amarelo acima de 75% deles (e pelo menos 3% do valor), vermelho acima de 90% (e pelo menos 10%).")


def regra_cnpj(forn, cache, ano):
    """Sinal extra (o mesmo usado com os deputados): fornecedor com CNPJ inativo ou aberto pouco antes do primeiro pagamento."""
    achados = []
    for f in sorted(forn.values(), key=lambda f: -f["valor"])[:40]:
        c = f["doc"]
        if len(c) != 14 or c not in cache or f["valor"] < 10000:
            continue
        info = cache[c]
        flags = []
        sit = info.get("situacao", "")
        if sit and sit not in ("ATIVA", "ATIVO") and f["valor"] >= 100000:
            flags.append(f"CNPJ {sit.lower()} na Receita hoje")
        ab = info.get("abertura", "")
        try:
            abd = dt.date.fromisoformat(ab[:10])
            if f["primeiro"] and 0 <= (f["primeiro"] - abd).days < 180:
                flags.append(f"empresa aberta {(f['primeiro'] - abd).days} dias antes do primeiro pagamento")
        except ValueError:
            pass
        if flags:
            achados.append((f, flags))
    if not achados:
        return alerta("cnpj", "Situação dos fornecedores na Receita", "good",
                      "Os maiores fornecedores com CNPJ estão ativos e nenhum foi aberto pouco antes de começar a receber.", REGRA_CNPJ, "",
                      "Nenhum sinal na situação cadastral.")
    total = sum(f["valor"] for f, _ in achados)
    st = "bad" if any(f["valor"] >= 100000 and any("dias antes" in x for x in fl) for f, fl in achados) else "warn"
    dados = [{"grupo": "Fornecedores", "registros": [
        {"fornecedor": f["nome"], "doc": fmt_doc(f["doc"]), "valor": r2(f["valor"]), "descricao": "; ".join(fl).capitalize(), "url": ""} for f, fl in achados[:8]]}]
    return alerta("cnpj", "Situação dos fornecedores na Receita", st,
                  f"{len(achados)} dos maiores fornecedores {'tem' if len(achados) == 1 else 'têm'} algum sinal na situação cadastral, somando {brl_curto(total)} recebidos.",
                  REGRA_CNPJ,
                  "Quando a empresa encerrou as atividades (pode ter sido depois dos pagamentos) e se a empresa recém-aberta já tinha estrutura para entregar o serviço.",
                  "Sinal cadastral não é prova de irregularidade. Empresas fecham depois de prestar serviços e empresas novas podem ser legítimas.",
                  dados, total)


REGRA_CNPJ = ("Consulta na Receita Federal, via BrasilAPI e Minha Receita, os 40 maiores fornecedores com CNPJ que receberam R$ 10 mil ou mais no ano. Sinaliza CNPJ que não está ativo hoje (para quem recebeu R$ 100 mil ou mais) e empresa aberta menos de 180 dias antes do primeiro pagamento do partido. "
              "Fica vermelho quando uma empresa recém-aberta recebeu R$ 100 mil ou mais.")


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def nivel_risco(alertas):
    pontos = sum(2 if a["status"] == "bad" else 1 if a["status"] == "warn" else 0 for a in alertas)
    return pontos, ("alto" if pontos >= 6 else "moderado" if pontos >= 3 else "baixo")


# ---------------------------------------------------------------- principal

def main():
    os.makedirs(OUT, exist_ok=True)
    fatores, ipca_ref = carregar_ipca()
    anos = {}
    for ano in range(ANO_INICIO, HOJE.year + 1):
        a = carregar_ano(ano)
        if a:
            anos[ano] = a
    if not anos:
        aviso("Nenhum ano disponível; nada foi gerado")
        salvar(os.path.join(OUT, "status.json"), status)
        sys.exit(1)

    # agrupa por partido (sigla) dentro de cada ano
    por_partido = defaultdict(dict)
    nomes, cnpjs = {}, {}
    for ano, A in anos.items():
        dd, rr = defaultdict(list), defaultdict(list)
        for r in A["despesas"]:
            dd[r["SG_PARTIDO"].strip()].append(r)
        for r in A["receitas"]:
            rr[r["SG_PARTIDO"].strip()].append(r)
        for sg in set(dd) | set(rr):
            if not sg:
                continue
            por_partido[sg][ano] = (dd.get(sg, []), rr.get(sg, []))
            amostra = (dd.get(sg) or rr.get(sg))[0]
            nomes[sg] = titulo(amostra.get("NM_PARTIDO", sg))
            cnpjs[sg] = amostra.get("NR_CNPJ_PRESTADOR_CONTA", "")

    # referência de preços por subcategoria (todos os partidos, todos os anos, corrigido pela inflação)
    valores = defaultdict(list)
    for sg, porano in por_partido.items():
        for ano, (D, _) in porano.items():
            f = fatores.get(ano, 1)
            vistos = set()
            for r in D:
                if r.get("TP_DESPESA") != "G":
                    continue
                sq = limpo(r.get("SQ_DESPESA")) or str(id(r))
                if sq in vistos:
                    continue
                vistos.add(sq)
                ds = limpo(r.get("DS_GASTO"))
                if not compra(ds, r):
                    continue
                v = num(r.get("VR_DOCUMENTO")) or valor_despesa(r)
                if v > 0:
                    valores[base_gasto(ds)].append(v * f)
    ref_preco = {k: {"mediana": statistics.median(v), "p995": percentil(v, .995), "n": len(v)} for k, v in valores.items() if len(v) >= 50}
    log(f"Referência de preços: {len(ref_preco)} tipos de gasto com 30+ documentos")

    # resumo de cada partido e ano
    resumos = defaultdict(dict)
    for sg, porano in por_partido.items():
        for ano, (D, R) in sorted(porano.items()):
            resumos[sg][ano] = resumo_ano(sg, ano, D, R, anos[ano])

    # CNPJs dos maiores fornecedores de cada partido
    precisa = set()
    for sg, porano in resumos.items():
        for ano, rs in porano.items():
            for f in sorted(rs["fornecedores_raw"].values(), key=lambda f: -f["valor"])[:40]:
                if len(f["doc"]) == 14 and f["valor"] >= 10000:
                    precisa.add(f["doc"])
    cache_cnpj = consultar_cnpjs(precisa)

    # referências entre partidos de cada ano (concentração e documentação)
    ref_conc, ref_doc = defaultdict(list), defaultdict(lambda: defaultdict(list))
    docs_ind = {}
    for sg, porano in resumos.items():
        for ano, rs in porano.items():
            forn = rs["fornecedores_raw"]
            tot = sum(f["valor"] for f in forn.values())
            if tot >= 100000:
                ref_conc[ano].append(max(f["valor"] for f in forn.values()) / tot)
    # o indicador documental precisa ser calculado antes para servir de referência
    for sg, porano in por_partido.items():
        for ano, (D, _) in porano.items():
            G = [r for r in D if r.get("TP_DESPESA") == "G" and valor_despesa(r) > 0]
            if sum(valor_despesa(r) for r in G) < 100000:
                continue
            _, ind = regra_documental(G, anos[ano], {}, dt.date(ano + 1, 6, 30) >= HOJE)
            docs_ind[(sg, ano)] = ind
            for k, v in ind.items():
                if v is not None:
                    ref_doc[ano][k].append(v)

    # alertas e arquivos por partido
    lista = []
    for sg in sorted(resumos):
        porano = resumos[sg]
        ficha = {"sg": sg, "slug": slug(sg), "nome": nomes[sg], "cnpj": fmt_doc(cnpjs[sg]), "anos": {}}
        resumo_lista = {}
        for ano in sorted(porano):
            rs = porano[ano]
            D, _ = por_partido[sg][ano]
            G = [r for r in D if r.get("TP_DESPESA") == "G" and valor_despesa(r) > 0]
            A = anos[ano]
            forn = rs.pop("fornecedores_raw")
            forn_ant = None
            if ano - 1 in por_partido[sg]:
                forn_ant = {re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR", "")) for r in por_partido[sg][ano - 1][0] if r.get("TP_DESPESA") == "G"}
            if rs["sem_movimento"] or rs["gastos"]["total"] < 1000:
                alertas = []
            else:
                alertas = [
                    regra_duplicidade(G, A),
                    regra_fora_padrao(G, A, ref_preco, fatores.get(ano, 1)),
                    regra_concentracao(forn, rs["gastos"]["compras"], ref_conc[ano], forn_ant),
                    regra_temporal(ano, rs, {a: resumos[sg][a] for a in resumos[sg] if a < ano}, fatores.get(ano, 1), fatores),
                    regra_documental(G, A, ref_doc[ano], dt.date(ano + 1, 6, 30) >= HOJE)[0],
                    regra_cnpj(forn, cache_cnpj, ano),
                ]
            pontos, nivel = nivel_risco(alertas)
            tot_compras = rs["gastos"]["compras"] or 1
            fornecedores = []
            for f in sorted(forn.values(), key=lambda f: -f["valor"])[:15]:
                flags = []
                info = cache_cnpj.get(f["doc"]) if len(f["doc"]) == 14 else None
                if info:
                    sit = info.get("situacao", "")
                    if sit and sit not in ("ATIVA", "ATIVO"):
                        flags.append(f"CNPJ {sit.lower()}")
                    try:
                        abd = dt.date.fromisoformat(info.get("abertura", "")[:10])
                        if f["primeiro"] and 0 <= (f["primeiro"] - abd).days < 180:
                            flags.append("empresa recém-aberta")
                    except ValueError:
                        pass
                fornecedores.append({"nome": f["nome"] or "Não informado", "doc": fmt_doc(f["doc"]), "valor": r2(f["valor"]),
                                     "pct": round(f["valor"] / tot_compras * 100, 1), "categoria": f["cats"].most_common(1)[0][0], "n": f["n"], "flags": flags})
            rs["fornecedores"] = fornecedores
            rs["alertas"] = alertas
            rs["risco"] = {"pontos": pontos, "nivel": nivel}
            rs["referencia"] = A["geracao"]
            rs["comprovantes"] = A["tem_nf"]
            rs["eleitoral"] = ano in ANOS_ELEITORAIS
            rs["parcial"] = dt.date(ano + 1, 6, 30) >= HOJE
            ficha["anos"][ano] = rs
            resumo_lista[ano] = {
                "receita": rs["receitas"]["total"], "publico": rs["receitas"]["publico"], "gasto": rs["gastos"]["total"],
                "transferencias": rs["transferencias"]["total"], "devolucoes": rs["devolucoes"]["total"],
                "pontos": pontos, "nivel": nivel, "alertas": sum(1 for a in alertas if a["status"] in ("warn", "bad")),
                "sem_movimento": rs["sem_movimento"],
            }
        salvar(os.path.join(OUT, f"{ficha['slug']}.json"), ficha)
        lista.append({"sg": sg, "slug": ficha["slug"], "nome": nomes[sg], "anos": resumo_lista})

    idx = {
        "atualizado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M"),
        "anos": sorted(anos),
        "eleitorais": sorted(a for a in anos if a in ANOS_ELEITORAIS),
        # o partido entrega a conta anual até 30 de junho do ano seguinte; antes disso o arquivo traz só o que já foi enviado
        "parciais": sorted(a for a in anos if dt.date(a + 1, 6, 30) >= HOJE),
        "referencias": {str(a): A["geracao"] for a, A in anos.items()},
        "ipca": {"fatores": {str(k): round(v, 4) for k, v in fatores.items()}, "ate": ipca_ref},
        "regras": {"duplicidade": REGRA_DUP, "fora_padrao": REGRA_FP, "concentracao": REGRA_CONC, "temporal": REGRA_TEMP, "documental": REGRA_DOC, "cnpj": REGRA_CNPJ},
        "partidos": lista,
    }
    salvar(os.path.join(OUT, "index.json"), idx)
    status["contagens"]["partidos"] = len(lista)
    status["duracao_s"] = round(time.time() - T0)
    status["executado_em"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    salvar(os.path.join(OUT, "status.json"), status)
    log(f"Pronto: {len(lista)} partidos, anos {sorted(anos)}")


if __name__ == "__main__":
    main()
