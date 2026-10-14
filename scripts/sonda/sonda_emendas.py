"""Sonda temporária: inspeciona as fontes de emendas parlamentares (roda só no GitHub Actions)."""
import collections, csv, io, json, sys, urllib.request, zipfile

UA = {"User-Agent": "Mozilla/5.0 radar-politico"}

def get(url, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type"), r.read()

def br(v):
    try:
        return float((v or "0").replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0

st, ct, b = get("https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO")
print("emendas:", st, ct, len(b))
z = zipfile.ZipFile(io.BytesIO(b))
for info in z.infolist():
    print("  arquivo:", info.filename, info.file_size)
for info in z.infolist():
    txt = z.read(info.filename).decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(txt), delimiter=";"))
    import os; os.makedirs("scripts/sonda/amostras", exist_ok=True)
    open("scripts/sonda/amostras/" + info.filename.replace("/", "_"), "w").write("\n".join(txt.splitlines()[:400]))
    print("\n=====", info.filename, "linhas:", len(rows))
    print("colunas:", list(rows[0].keys()))
    for r in rows[:3]:
        print(json.dumps(r, ensure_ascii=False))
    for col in rows[0].keys():
        vals = collections.Counter(r[col] for r in rows)
        if len(vals) <= 40:
            print(f"  [{col}] {len(vals)} valores:", vals.most_common(40))
        else:
            print(f"  [{col}] {len(vals)} valores distintos, ex:", [v for v, _ in vals.most_common(5)])
    ano_col = next((c for c in rows[0] if c.lower().startswith("ano")), None)
    vcols = [c for c in rows[0] if c.lower().startswith("valor")]
    if ano_col and vcols:
        tot = collections.defaultdict(lambda: collections.Counter())
        for r in rows:
            for c in vcols:
                tot[r[ano_col]][c] += br(r[c])
        for a in sorted(tot):
            print("  ", a, {k: round(v / 1e9, 2) for k, v in tot[a].items()}, "bi")

for url in ["https://api.transferegov.gestao.gov.br/transferenciasespeciais/plano_acao_especial?limit=2",
            "https://api.transferegov.gestao.gov.br/transferenciasespeciais/",
            "https://dadosabertos.camara.leg.br/api/v2/deputados?itens=2"]:
    try:
        st, ct, b = get(url, 60)
        print("\n", url, st, ct, b[:1500].decode("utf-8", "replace"))
    except Exception as e:
        print("\n", url, "ERRO", e)
