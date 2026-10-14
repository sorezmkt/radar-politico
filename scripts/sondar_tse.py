#!/usr/bin/env python3
"""Sondagem temporária: resume a estrutura dos arquivos de contas partidárias do TSE em sondagem/."""
import csv, io, os, re, sys, urllib.request, zipfile
from collections import Counter, defaultdict
csv.field_size_limit(10_000_000)
BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas_anual_partidaria/"
ARQS = [f"prestacao_contas_anual_partidaria_{a}.zip" for a in (2021, 2022, 2023, 2024, 2025)] + \
       [f"prestacao_contas_anual_partidaria_notafiscal_{a}.zip" for a in (2024,)]
os.makedirs("sondagem", exist_ok=True)
out = open("sondagem/resumo.txt", "w", encoding="utf-8")
def p(*a):
    print(*a, file=out, flush=True)
for nome in ARQS:
    p("=" * 100); p(nome)
    try:
        raw = urllib.request.urlopen(urllib.request.Request(BASE + nome, headers={"User-Agent": "RadarPolitico/1.0"}), timeout=900).read()
    except Exception as e:
        p("  ERRO", e); continue
    p("  bytes", len(raw))
    z = zipfile.ZipFile(io.BytesIO(raw))
    tipos = defaultdict(list)
    for i in z.infolist():
        tipo = re.sub(r"_(\d{4}|[A-Z]{2}|BRASIL)(?=[_.])", "", i.filename)
        tipos[tipo].append((i.filename, i.file_size))
    for tipo, fs in tipos.items():
        p(f"  tipo {tipo}: {len(fs)} arquivos, {sum(s for _, s in fs)} bytes; ex {fs[:3]}")
    for tipo, fs in tipos.items():
        if not tipo.lower().endswith(".csv"):
            continue
        # junta todos os arquivos do tipo (prefere _BR / BRASIL se houver)
        rows, cab = [], None
        for fn, _ in fs:
            b = z.read(fn)
            t = b.decode("latin-1") if b[:3] != b"\xef\xbb\xbf" else b.decode("utf-8-sig")
            r = list(csv.reader(io.StringIO(t), delimiter=";"))
            if not r:
                continue
            cab = r[0]
            rows += [x for x in r[1:] if len(x) == len(cab)]
        p("-" * 80); p(" ", tipo, "linhas", len(rows))
        p("  colunas", cab)
        for r in rows[:2]:
            p("  amostra", dict(zip(cab, r)))
        for k, c in enumerate(cab):
            vals = Counter(r[k] for r in rows)
            if len(vals) <= 60:
                p(f"  distintos {c}: {dict(vals.most_common(60))}")
            else:
                p(f"  {c}: {len(vals)} distintos, ex: {[v[:60] for v,_ in vals.most_common(6)]}")
        # totais por partido na esfera nacional, se der
        ie = next((k for k, c in enumerate(cab) if c.startswith("DS_TP_ESF")), None)
        iv = next((k for k, c in enumerate(cab) if c.startswith("VR_")), None)
        ip = cab.index("SG_PARTIDO") if "SG_PARTIDO" in cab else None
        if ie is not None and iv is not None and ip is not None:
            tot = Counter()
            for r in rows:
                if "NAC" in r[ie].upper():
                    try:
                        tot[r[ip]] += float(r[iv].replace(".", "").replace(",", ".")) if "," in r[iv] else float(r[iv])
                    except ValueError:
                        pass
            p(f"  total nacional por partido ({cab[iv]}):", {k: round(v) for k, v in tot.most_common()})
out.close()
