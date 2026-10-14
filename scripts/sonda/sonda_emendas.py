"""Sonda temporária 3: tabelas das transferências especiais."""
import collections, json, time, urllib.request
UA = {"User-Agent": "Mozilla/5.0 radar-politico"}
B = "https://api.transferegov.gestao.gov.br/transferenciasespeciais/"
def get(url, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())
def tudo(tab, select="*", passo=10000):
    out, off = [], 0
    t = time.time()
    while True:
        d = get(f"{B}{tab}?select={select}&limit={passo}&offset={off}&order=1")
        out += d
        if len(d) < passo: break
        off += passo
    print(f"{tab}: {len(out)} linhas em {time.time()-t:.0f}s")
    return out
pa = tudo("plano_acao_especial", passo=5000)
print(" situacao:", collections.Counter(r["situacao_plano_acao"] for r in pa).most_common())
print(" ano:", sorted(collections.Counter(r["ano_plano_acao"] for r in pa).items()))
print(" impedimento:", collections.Counter((r["motivo_impedimento_plano_acao"] or "")[:60] for r in pa).most_common(8))
cods = collections.Counter(r["numero_emenda_parlamentar_plano_acao"] for r in pa)
print(" emendas distintas:", len(cods), "planos por emenda max:", cods.most_common(3))
for tab in ["plano_trabalho_especial", "relatorio_gestao_novo_especial", "relatorio_gestao_especial", "plano_trabalho_analise_especial", "executor_especial"]:
    try:
        rows = tudo(tab, passo=5000)
    except Exception as e:
        print(tab, "ERRO", e); continue
    if not rows: continue
    print(" exemplo:", json.dumps(rows[0], ensure_ascii=False)[:800])
    for k in rows[0]:
        if any(x in k for x in ("situacao", "tipo", "parecer", "ind_")) and not k.startswith("texto"):
            print(f"  [{k}]", collections.Counter(str(r[k])[:70] for r in rows).most_common(12))
    if tab == "plano_trabalho_analise_especial":
        print("  reprovado>0:", sum(1 for r in rows if (r["valor_reprovado_analise_pt"] or 0) > 0))
    if tab == "plano_trabalho_especial":
        print("  fim execucao ex:", collections.Counter(str(r["data_fim_execucao_plano_trabalho"])[:4] for r in rows).most_common(10))
