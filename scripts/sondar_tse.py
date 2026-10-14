#!/usr/bin/env python3
"""Sondagem temporária 2: semântica dos campos na esfera nacional (arquivo _BR) e leiames."""
import csv, io, os, urllib.request, zipfile
from collections import Counter, defaultdict
csv.field_size_limit(10_000_000)
BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas_anual_partidaria/"
os.makedirs("sondagem", exist_ok=True)
out = open("sondagem/resumo2.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out, flush=True)
def get(n): return zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(urllib.request.Request(BASE + n, headers={"User-Agent": "RadarPolitico/1.0"}), timeout=900).read()))
def ler(z, fn):
    b = z.read(fn); t = b.decode("utf-8-sig") if b[:3] == b"\xef\xbb\xbf" else b.decode("latin-1")
    r = list(csv.reader(io.StringIO(t), delimiter=";")); return [dict(zip(r[0], x)) for x in r[1:] if len(x) == len(r[0])]
def v(s):
    s = (s or "0").replace(".", "").replace(",", ".") if "," in (s or "") else (s or "0")
    try: return float(s)
    except ValueError: return 0.0
z = get("prestacao_contas_anual_partidaria_2024.zip")
for fn in z.namelist():
    if fn.endswith(".pdf"):
        open("sondagem/" + fn, "wb").write(z.read(fn))
p("arquivos", z.namelist())
D = ler(z, "despesa_anual_2024_BR.csv")
R = ler(z, "receita_anual_2024_BR.csv")
p("despesas BR", len(D), "receitas BR", len(R))
p("esferas D", Counter(r["DS_TP_ESFERA_PARTIDARIA"] for r in D), "UF", Counter(r["SG_UF"] for r in D).most_common(5))
p("prestadores por partido", {k: len(v_) for k, v_ in sorted(defaultdict(set, {}).items())})
pp = defaultdict(set)
for r in D: pp[r["SG_PARTIDO"]].add(r["NR_CNPJ_PRESTADOR_CONTA"])
p("CNPJs prestadores por partido (D)", {k: sorted(x) for k, x in pp.items()})
cross = defaultdict(Counter); somas = defaultdict(float)
for r in D:
    cross[r["TP_DESPESA"]][r["DS_GASTO"]] += 1; somas[(r["TP_DESPESA"], r["DS_GASTO"])] += v(r["VR_GASTO"])
for tp, c in cross.items():
    p("== TP_DESPESA", tp, sum(c.values()))
    for g, n in c.most_common(400): p(f"   {n:7d}  R$ {somas[(tp,g)]:16,.0f}  {g}")
# multiplicidade de SQ_DESPESA
g = defaultdict(list)
for r in D: g[r["SQ_DESPESA"]].append(r)
mult = Counter(min(len(x), 10) for k, x in g.items() if k != "-1")
p("linhas por SQ_DESPESA", sorted(mult.items()))
ex = [x for k, x in g.items() if k != "-1" and len(x) > 1][:6]
for x in ex:
    p("  exemplo SQ", x[0]["SQ_DESPESA"], [(r["NM_FORNECEDOR"][:30], r["NR_DOCUMENTO"], r["DT_PAGAMENTO"], r["VR_GASTO"], r["VR_PAGAMENTO"], r["VR_DOCUMENTO"], r["DS_FONTE_DESPESA"]) for r in x])
tg = sum(v(r["VR_GASTO"]) for r in D); tpg = sum(v(r["VR_PAGAMENTO"]) for r in D); td = sum(v(r["VR_DOCUMENTO"]) for r in D)
tg1 = sum(v(x[0]["VR_GASTO"]) for k, x in g.items() if k != "-1")
p(f"soma VR_GASTO {tg:,.0f}  VR_PAGAMENTO {tpg:,.0f}  VR_DOCUMENTO {td:,.0f}  VR_GASTO 1 por SQ {tg1:,.0f}")
dif = sum(1 for r in D if r["VR_GASTO"] != r["VR_PAGAMENTO"]); p("linhas VR_GASTO != VR_PAGAMENTO", dif)
p("exemplos dif", [(r["VR_GASTO"], r["VR_PAGAMENTO"], r["VR_DOCUMENTO"]) for r in D if r["VR_GASTO"] != r["VR_PAGAMENTO"]][:15])
# receitas
cr = defaultdict(float); cn = Counter()
for r in R:
    k = (r["DS_TP_ORIGEM_DOACAO"], r["DS_TP_FONTE_RECURSO"], r["DS_TP_NATUREZA_RECURSO"], r["DS_RECEITA"]); cr[k] += v(r["VR_RECEITA"]); cn[k] += 1
p("== RECEITAS BR por origem/fonte/natureza/descricao")
for k, s in sorted(cr.items(), key=lambda x: -x[1])[:150]: p(f"   {cn[k]:7d} R$ {s:16,.0f} {k}")
p("maiores doadores BR", Counter({(r["SG_PARTIDO"], r["NM_DOADOR"]): v(r["VR_RECEITA"]) for r in R}).most_common(30))
# notas fiscais: ligação com despesas
zn = get("prestacao_contas_anual_partidaria_notafiscal_2024.zip")
p("nf arquivos", zn.namelist())
nfn = next(n for n in zn.namelist() if n.endswith("_BR.csv"))
N = ler(zn, nfn); p("nf BR", len(N))
sqs = set(g)
p("nf SQ presentes nas despesas", sum(1 for r in N if r["SQ_DESPESA"] in sqs), "SQ=-1:", sum(1 for r in N if r["SQ_DESPESA"] == "-1"))
p("nf amostras", [(r["SQ_DESPESA"], r["CD_TIPO_DESPESA"], r["NR_DOCUMENTO"], r["VR_DOCUMENTO"], r["NM_URL"][-60:]) for r in N[:5]])
cobre = defaultdict(lambda: [0, 0])
nsq = set(r["SQ_DESPESA"] for r in N)
for r in D:
    if r["TP_DESPESA"] == "G": cobre[r["SG_PARTIDO"]][0] += 1; cobre[r["SG_PARTIDO"]][1] += r["SQ_DESPESA"] in nsq
p("cobertura de documento por partido (gastos G):", dict(cobre))
out.close()
