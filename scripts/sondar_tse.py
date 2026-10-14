#!/usr/bin/env python3
"""Sondagem temporária: mostra a estrutura dos arquivos de contas partidárias do TSE."""
import csv, io, sys, urllib.request, zipfile
from collections import Counter
csv.field_size_limit(10_000_000)
BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas_anual_partidaria/"
ARQS = sys.argv[1:] or [f"prestacao_contas_anual_partidaria_{a}.zip" for a in (2022, 2023, 2024, 2025)]
for nome in ARQS:
    print("=" * 100, "\n", nome, flush=True)
    try:
        raw = urllib.request.urlopen(urllib.request.Request(BASE + nome, headers={"User-Agent": "RadarPolitico/1.0"}), timeout=900).read()
    except Exception as e:
        print("  ERRO", e); continue
    print("  bytes", len(raw))
    z = zipfile.ZipFile(io.BytesIO(raw))
    for i in z.infolist():
        print("  -", i.filename, i.file_size)
    for i in z.infolist():
        if not i.filename.lower().endswith((".csv", ".txt")):
            continue
        b = z.read(i.filename)
        for enc in ("utf-8-sig", "latin-1"):
            try:
                t = b.decode(enc); break
            except UnicodeDecodeError:
                pass
        print("-" * 80, "\n ", i.filename, "enc", enc)
        linhas = t.splitlines()
        sep = ";" if linhas[0].count(";") >= linhas[0].count(",") else ","
        rows = list(csv.reader(io.StringIO(t), delimiter=sep))
        cab = rows[0]
        print("  linhas", len(rows) - 1)
        print("  colunas", cab)
        for r in rows[1:4]:
            print("  amostra", dict(zip(cab, r)))
        for c in cab:
            vals = Counter(r[cab.index(c)] for r in rows[1:] if len(r) == len(cab))
            if len(vals) <= 40:
                print(f"  distintos {c}: {dict(vals.most_common(40))}")
            else:
                print(f"  {c}: {len(vals)} distintos, ex: {[v for v,_ in vals.most_common(5)]}")
