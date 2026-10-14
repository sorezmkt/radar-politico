"""Sonda temporária 2: casamento de nomes e Transferegov."""
import collections, csv, io, json, re, unicodedata, urllib.request, zipfile
UA = {"User-Agent": "Mozilla/5.0 radar-politico"}
def get(url, timeout=300, h=None):
    req = urllib.request.Request(url, headers={**UA, **(h or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()
def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]", " ", s).split()
def br(v):
    try: return float((v or "0").replace(".", "").replace(",", "."))
    except ValueError: return 0.0
deps = []
pag = 1
while True:
    _, _, b = get(f"https://dadosabertos.camara.leg.br/api/v2/deputados?itens=100&pagina={pag}")
    d = json.loads(b)["dados"]
    if not d: break
    deps += d; pag += 1
print("deputados", len(deps))
_, _, b = get("https://legis.senado.leg.br/dadosabertos/senador/lista/atual.json", h={"Accept": "application/json"})
sen = json.loads(b)["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
sen_nomes = {" ".join(norm(s["IdentificacaoParlamentar"]["NomeParlamentar"])) for s in sen}
print("senadores", len(sen_nomes))
_, _, b = get("https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO")
z = zipfile.ZipFile(io.BytesIO(b))
rows = list(csv.DictReader(io.StringIO(z.read("EmendasParlamentares.csv").decode("latin-1")), delimiter=";"))
aut = collections.defaultdict(lambda: collections.Counter())
for r in rows:
    if r["Ano da Emenda"] >= "2023" and r["Tipo de Emenda"].startswith("Emenda Individual"):
        aut[" ".join(norm(r["Nome do Autor da Emenda"]))][r["Código do Autor da Emenda"]] += 1
print("autores individuais 2023+", len(aut))
nomes_dep = collections.Counter(" ".join(norm(d["nome"])) for d in deps)
ok = [d for d in deps if " ".join(norm(d["nome"])) in aut]
print("deputados casados por nome:", len(ok), "ambíguos na Câmara:", [n for n, c in nomes_dep.items() if c > 1], "também senador:", [n for n in nomes_dep if n in sen_nomes])
print("sem emenda individual 2023+:", [d["nome"] for d in deps if " ".join(norm(d["nome"])) not in aut][:80])
print("autores com 2 códigos:", [(n, c) for n, c in aut.items() if len(c) > 1][:20])
sobra = [n for n in aut if n not in nomes_dep and n not in sen_nomes]
print("autores que não são deputado nem senador atual:", len(sobra), sobra[:60])
fav = list(csv.DictReader(io.StringIO(z.read("EmendasParlamentares_PorFavorecido.csv").decode("latin-1")), delimiter=";"))
pf = collections.Counter((r["Tipo de Emenda"], r["Natureza Jurídica"]) for r in fav if r["Tipo Favorecido"] == "Pessoa Fisica")
print("PF por tipo/natureza:", pf.most_common(10))
print("PF exemplos:", [ (r["Favorecido"], r["Valor Recebido"], r["Nome do Autor da Emenda"]) for r in fav if r["Tipo Favorecido"]=="Pessoa Fisica"][:10])
nat = collections.Counter()
for r in fav:
    if r["Ano/Mês"] >= "202301": nat[r["Natureza Jurídica"]] += br(r["Valor Recebido"])
print("natureza 2023+ (mi):", [(k, round(v/1e6)) for k, v in nat.most_common(52)])
pix = [r for r in rows if "Especiais" in r["Tipo de Emenda"] and r["Ano da Emenda"] >= "2020"]
print("emendas pix linhas", len(pix), "códigos", len({r['Código da Emenda'] for r in pix}))
_, h, b = get("https://api.transferegov.gestao.gov.br/transferenciasespeciais/plano_acao_especial?limit=1&select=id_plano_acao", h={"Prefer": "count=exact"})
print("plano_acao total:", h.get("Content-Range"))
_, _, b = get("https://api.transferegov.gestao.gov.br/transferenciasespeciais/")
sw = json.loads(b)
for p, d in sw["paths"].items():
    print("endpoint", p, list(d.get("get", {}).get("parameters", []))[:0])
for nome, df in sw.get("definitions", {}).items():
    print("def", nome, list(df.get("properties", {}).keys()))
