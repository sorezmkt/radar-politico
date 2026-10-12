#!/usr/bin/env python3
"""
Radar Político — presidentes.

Monta data/presidentes.json com indicadores que afetam a vida da população,
medidos no início e no fim de cada mandato presidencial desde 1995.

Fontes (séries oficiais e longas, iguais para todos os mandatos):
  - Banco Mundial (World Development Indicators): homicídios, mortalidade infantil,
    desemprego, PIB por habitante, inflação, pobreza extrema, desigualdade,
    gasto público em saúde e educação. Também traz a média da América Latina e Caribe
    para comparar com a região no mesmo período.
  - Banco Central do Brasil (SGS): Selic, IPCA e endividamento das famílias.

Não existe nota geral nem ranking geral de presidentes. Cada indicador compara os
mandatos entre si, e o visitante escolhe qual área quer ver.
"""
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(ROOT, "data", "presidentes.json")
UA = {"User-Agent": "RadarPolitico/1.0 (+https://github.com/sorezmkt/radar-politico)"}
HOJE = dt.date.today()
ANO_INICIAL = 1990
avisos = []


def baixar(url, tentativas=4, timeout=90):
    erro = None
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            erro = e
        except Exception as e:  # noqa: BLE001
            erro = e
        time.sleep(4 * (i + 1))
    raise erro


# --------------------------------------------------------------------- mandatos
# base = último ano antes de assumir; fim = último ano completo no cargo (None = em andamento)
MANDATOS = [
    {"id": "fhc1", "sigla": "FHC 1", "nome": "Fernando Henrique Cardoso", "curto": "FHC", "rotulo": "1º mandato", "partido": "PSDB",
     "inicio": "1995-01-01", "termino": "1998-12-31", "base": 1994, "fim": 1998,
     "contexto": ["Consolidação do Plano Real", "Crises financeiras da Ásia (1997) e da Rússia (1998)"]},
    {"id": "fhc2", "sigla": "FHC 2", "nome": "Fernando Henrique Cardoso", "curto": "FHC", "rotulo": "2º mandato", "partido": "PSDB",
     "inicio": "1999-01-01", "termino": "2002-12-31", "base": 1998, "fim": 2002,
     "contexto": ["Desvalorização do real e adoção do câmbio flutuante (1999)", "Crise de energia (2001)"]},
    {"id": "lula1", "sigla": "Lula 1", "nome": "Luiz Inácio Lula da Silva", "curto": "Lula", "rotulo": "1º mandato", "partido": "PT",
     "inicio": "2003-01-01", "termino": "2006-12-31", "base": 2002, "fim": 2006,
     "contexto": ["Alta internacional dos preços das commodities"]},
    {"id": "lula2", "sigla": "Lula 2", "nome": "Luiz Inácio Lula da Silva", "curto": "Lula", "rotulo": "2º mandato", "partido": "PT",
     "inicio": "2007-01-01", "termino": "2010-12-31", "base": 2006, "fim": 2010,
     "contexto": ["Crise financeira global (2008–2009)"]},
    {"id": "dilma1", "sigla": "Dilma 1", "nome": "Dilma Rousseff", "curto": "Dilma", "rotulo": "1º mandato", "partido": "PT",
     "inicio": "2011-01-01", "termino": "2014-12-31", "base": 2010, "fim": 2014,
     "contexto": ["Queda dos preços das commodities", "Protestos de junho de 2013"]},
    {"id": "dilma2", "sigla": "Dilma 2", "nome": "Dilma Rousseff", "curto": "Dilma", "rotulo": "2º mandato, interrompido", "partido": "PT",
     "inicio": "2015-01-01", "termino": "2016-05-12", "base": 2014, "fim": 2015,
     "contexto": ["Recessão de 2015–2016", "Afastada em maio de 2016 e destituída em agosto pelo impeachment"],
     "nota": "Mandato curto: só 2015 é um ano completo no cargo, então os números refletem um único ano."},
    {"id": "temer", "sigla": "Temer", "nome": "Michel Temer", "curto": "Temer", "rotulo": "Mandato após o impeachment", "partido": "MDB",
     "inicio": "2016-05-12", "termino": "2018-12-31", "base": 2016, "fim": 2018,
     "contexto": ["Saída da recessão de 2015–2016", "Teto de gastos (2016) e reforma trabalhista (2017)"],
     "nota": "Assumiu interinamente em maio de 2016 e em definitivo em agosto. A comparação usa 2016 como ponto de partida."},
    {"id": "bolsonaro", "sigla": "Bolsonaro", "nome": "Jair Bolsonaro", "curto": "Bolsonaro", "rotulo": "Mandato", "partido": "PSL, depois PL",
     "inicio": "2019-01-01", "termino": "2022-12-31", "base": 2018, "fim": 2022,
     "contexto": ["Pandemia de Covid-19 (2020–2022)", "Reforma da Previdência (2019)"]},
    {"id": "lula3", "sigla": "Lula 3", "nome": "Luiz Inácio Lula da Silva", "curto": "Lula", "rotulo": "3º mandato, em andamento", "partido": "PT",
     "inicio": "2023-01-01", "termino": None, "base": 2022, "fim": None,
     "contexto": []},
]

# --------------------------------------------------------------------- indicadores
# tipo "variacao": compara o ano antes da posse com o último ano no cargo
# tipo "media": média dos anos no cargo (para inflação e juros, o nível importa mais que a mudança)
AREAS = ["Economia", "Trabalho", "Juros e dívidas", "Contas públicas", "Segurança", "Saúde", "Educação", "Social"]
INDICADORES = [
    {"id": "pib_pc", "nome": "PIB por habitante", "area": "Economia", "fonte": "wb", "codigo": "NY.GDP.PCAP.KD",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "US$ por pessoa (valores de 2015)", "casas": 0,
     "explica": "Riqueza produzida no país dividida pela população, descontada a inflação."},
    {"id": "ocupacao", "nome": "Pessoas trabalhando", "area": "Trabalho", "fonte": "wb", "codigo": "SL.EMP.TOTL.SP.ZS",
     "melhor": "maior", "tipo": "variacao", "unidade": "% da população com 15 anos ou mais", "casas": 1,
     "explica": "De todas as pessoas em idade de trabalhar, quantas estão de fato trabalhando. Não depende de quem está ou não procurando emprego, por isso é difícil de distorcer."},
    {"id": "desemprego", "nome": "Desemprego oficial", "area": "Trabalho", "fonte": "wb", "codigo": "SL.UEM.TOTL.ZS",
     "melhor": "menor", "tipo": "variacao", "unidade": "% de quem trabalha ou procura trabalho", "casas": 1,
     "explica": "Conta só quem procurou emprego e não achou. Quem desistiu de procurar fica fora da conta, por isso vale olhar junto com a taxa de pessoas trabalhando."},
    {"id": "vulneravel", "nome": "Trabalho precário", "area": "Trabalho", "fonte": "wb", "codigo": "SL.EMP.VULN.ZS",
     "melhor": "menor", "tipo": "variacao", "unidade": "% de quem trabalha", "casas": 1,
     "explica": "Quem trabalha por conta própria ou ajuda a família sem salário, em geral sem carteira, férias ou aposentadoria garantida."},
    {"id": "inflacao", "nome": "Inflação média", "area": "Economia", "fonte": "wb", "codigo": "FP.CPI.TOTL.ZG",
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano", "casas": 1,
     "explica": "Alta média dos preços ao consumidor por ano durante o mandato."},
    {"id": "juros_reais", "nome": "Juros reais médios", "area": "Juros e dívidas", "fonte": "bcb_juros",
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano acima da inflação", "casas": 1,
     "explica": "Taxa Selic descontada a inflação (IPCA). Juro real alto encarece crédito e dívidas."},
    {"id": "endividamento", "nome": "Endividamento das famílias", "area": "Juros e dívidas", "fonte": "bcb", "codigo": 29037,
     "melhor": "menor", "tipo": "variacao", "unidade": "% da renda de um ano", "casas": 1,
     "explica": "Quanto as famílias devem aos bancos em relação ao que ganham em 12 meses. Série começa em 2005."},
    {"id": "arrecadacao", "nome": "Impostos e contribuições", "area": "Contas públicas", "fonte": "imf", "codigo": "rev",
     "melhor": "menor", "tipo": "variacao", "unidade": "% do PIB arrecadado pelo governo", "casas": 1,
     "explica": "Tudo o que União, estados e municípios arrecadam, em proporção da economia. Quando sobe, cada brasileiro entrega uma fatia maior do que produz, seja por imposto novo, aumento de alíquota ou arrecadação maior."},
    {"id": "gasto_total", "nome": "Gasto público total", "area": "Contas públicas", "fonte": "imf", "codigo": "exp",
     "melhor": "neutro", "tipo": "variacao", "unidade": "% do PIB gasto pelo governo", "casas": 1,
     "explica": "Tudo o que União, estados e municípios gastam, em proporção da economia. Não recebe selo de melhor ou pior: gastar mais ou menos depende do retorno, que você compara com os outros indicadores."},
    {"id": "divida", "nome": "Dívida pública", "area": "Contas públicas", "fonte": "imf", "codigo": "GGXWDG_NGDP",
     "melhor": "menor", "tipo": "variacao", "unidade": "% do PIB", "casas": 1,
     "explica": "Dívida bruta de União, estados e municípios. Dívida maior significa mais juros pagos com dinheiro de impostos."},
    {"id": "homicidios", "nome": "Homicídios", "area": "Segurança", "fonte": "wb", "codigo": "VC.IHR.PSRC.P5",
     "melhor": "menor", "tipo": "variacao", "unidade": "por 100 mil habitantes", "casas": 1,
     "explica": "Assassinatos por 100 mil habitantes. Segurança pública também depende muito dos estados."},
    {"id": "mort_infantil", "nome": "Mortalidade infantil", "area": "Saúde", "fonte": "wb", "codigo": "SP.DYN.IMRT.IN",
     "melhor": "menor", "tipo": "variacao", "unidade": "mortes por mil nascidos vivos", "casas": 1,
     "explica": "Bebês que morrem antes de completar 1 ano."},
    {"id": "gasto_saude", "nome": "Gasto público em saúde por habitante", "area": "Saúde", "fonte": "wb", "codigo": "SH.XPD.GHED.PP.CD",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "US$ por pessoa (paridade de poder de compra)", "casas": 0,
     "explica": "Quanto governo federal, estados e municípios gastam com saúde por pessoa. Série começa em 2000."},
    {"id": "gasto_educ", "nome": "Gasto público em educação", "area": "Educação", "fonte": "wb", "codigo": "SE.XPD.TOTL.GD.ZS",
     "melhor": "maior", "tipo": "variacao", "unidade": "% do PIB", "casas": 1,
     "explica": "Gasto de todos os níveis de governo com educação, em proporção da economia."},
    {"id": "ensino_medio", "nome": "Jovens no ensino médio", "area": "Educação", "fonte": "wb", "codigo": "SE.SEC.NENR",
     "melhor": "maior", "tipo": "variacao", "unidade": "% matriculados na idade certa", "casas": 1,
     "explica": "Taxa líquida de matrícula no ensino secundário (fundamental II e médio)."},
    {"id": "pobreza", "nome": "Pobreza extrema", "area": "Social", "fonte": "wb", "codigo": "SI.POV.DDAY",
     "melhor": "menor", "tipo": "variacao", "unidade": "% da população", "casas": 1,
     "explica": "Pessoas vivendo com menos de US$ 2,15 por dia (linha internacional do Banco Mundial)."},
    {"id": "gini", "nome": "Desigualdade de renda", "area": "Social", "fonte": "wb", "codigo": "SI.POV.GINI",
     "melhor": "menor", "tipo": "variacao", "unidade": "índice de Gini, de 0 a 100", "casas": 1,
     "explica": "Quanto maior, mais concentrada é a renda."},
]

# --------------------------------------------------------------------- coleta


def serie_wb(codigo):
    """Brasil e América Latina e Caribe, por ano."""
    url = (f"https://api.worldbank.org/v2/country/BRA;LCN/indicator/{codigo}"
           f"?format=json&date={ANO_INICIAL}:{HOJE.year}&per_page=1000")
    j = json.loads(baixar(url))
    if not isinstance(j, list) or len(j) < 2 or not j[1]:
        raise ValueError(f"sem dados para {codigo}")
    br, lat = {}, {}
    for o in j[1]:
        if o.get("value") is None:
            continue
        alvo = br if o.get("countryiso3code") == "BRA" else lat
        alvo[int(o["date"])] = float(o["value"])
    return br, lat


def serie_bcb(codigo, inicio="01/01/1990"):
    fim = HOJE.strftime("%d/%m/%Y")
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={inicio}&dataFinal={fim}"
    dados = json.loads(baixar(url))
    out = []
    for d in dados:
        try:
            dia, mes, ano = d["data"].split("/")
            out.append((int(ano), int(mes), float(d["valor"])))
        except (KeyError, ValueError):
            continue
    return out


def serie_imf(codigo):
    """FMI (World Economic Outlook). Descarta o ano corrente e projeções."""
    j = json.loads(baixar(f"https://www.imf.org/external/datamapper/api/v1/{codigo}/BRA"))
    vals = j.get("values", {}).get(codigo, {}).get("BRA", {})
    return {int(a): float(v) for a, v in vals.items() if v is not None and int(a) < HOJE.year and int(a) >= ANO_INICIAL}


def anual_ultimo_mes(mensal):
    """Valor de dezembro (ou do último mês disponível no ano)."""
    out = {}
    for a, m, v in sorted(mensal):
        out[a] = v
    return out


def juros_reais():
    selic = serie_bcb(4189, "01/01/1994")  # Selic acumulada no mês, anualizada (% a.a.)
    ipca = serie_bcb(433, "01/01/1994")    # IPCA mensal (%)
    por_ano_selic, por_ano_ipca = {}, {}
    for a, m, v in selic:
        por_ano_selic.setdefault(a, []).append(v)
    for a, m, v in ipca:
        por_ano_ipca.setdefault(a, []).append(v)
    out = {}
    for a in sorted(por_ano_selic):
        meses_ipca = por_ano_ipca.get(a, [])
        if len(por_ano_selic[a]) < 12 or len(meses_ipca) < 12:
            continue  # só anos completos
        s = sum(por_ano_selic[a]) / len(por_ano_selic[a]) / 100
        i = 1.0
        for v in meses_ipca:
            i *= 1 + v / 100
        out[a] = round(((1 + s) / i - 1) * 100, 2)
    return out


def coletar():
    series = {}
    for ind in INDICADORES:
        try:
            if ind["fonte"] == "wb":
                br, lat = serie_wb(ind["codigo"])
            elif ind["fonte"] == "imf":
                br, lat = serie_imf(ind["codigo"]), {}
            elif ind["fonte"] == "bcb":
                br, lat = anual_ultimo_mes(serie_bcb(ind["codigo"], "01/01/2005")), {}
                # o último ano só conta se já tiver dezembro
                if br and max(br) == HOJE.year:
                    br.pop(max(br))
            else:
                br, lat = juros_reais(), {}
            if not br:
                raise ValueError("série vazia")
            series[ind["id"]] = (br, lat)
            print(f"ok {ind['id']}: {min(br)}–{max(br)}", flush=True)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"{ind['id']}: {e}")
            print("AVISO", ind["id"], e, flush=True)
    return series


# --------------------------------------------------------------------- cálculo


def valor_ate(serie, ano, minimo):
    """Valor do ano pedido ou, se faltar, do ano disponível mais próximo antes dele (até o mínimo)."""
    for a in range(ano, minimo - 1, -1):
        if a in serie:
            return a, serie[a]
    return None, None


def medir(ind, serie, regiao, m):
    ultimo = max(serie)
    fim = m["fim"] if m["fim"] else ultimo
    fim = min(fim, ultimo)
    if fim <= m["base"]:
        return None
    r = {"id": ind["id"]}
    # como recebeu e como entregou (vale para todos os indicadores)
    ab, vb = valor_ate(serie, m["base"], m["base"] - 2)
    af, vf = valor_ate(serie, fim, m["base"] + 1)
    if vb is not None and vf is not None and af > ab:
        r["recebeu"] = {"ano": ab, "valor": vb}
        r["entregou"] = {"ano": af, "valor": vf}
        dif = vf - vb
        tolerancia = max(abs(vb) * 0.01, 10 ** -ind.get("casas", 1) / 2)
        if ind["melhor"] == "neutro":
            pass
        elif abs(dif) < tolerancia:
            r["veredito"] = "igual"
        else:
            r["veredito"] = "melhor" if (dif < 0) == (ind["melhor"] == "menor") else "pior"
    if ind["tipo"] == "media":
        anos = [a for a in range(m["base"] + 1, fim + 1) if a in serie]
        if not anos:
            return None
        r["media"] = sum(serie[a] for a in anos) / len(anos)
        r["anos"] = [anos[0], anos[-1]]
        r["metrica"] = -r["media"] if ind["melhor"] == "menor" else r["media"]
        anos_r = [a for a in anos if a in regiao]
        if anos_r and len(anos_r) == len(anos):
            r["regiao_media"] = sum(regiao[a] for a in anos_r) / len(anos_r)
    else:
        ab, vb = valor_ate(serie, m["base"], m["base"] - 2)
        af, vf = valor_ate(serie, fim, m["base"] + 1)
        if vb is None or vf is None or af <= ab:
            return None
        r["inicio"] = {"ano": ab, "valor": vb}
        r["fim"] = {"ano": af, "valor": vf}
        r["variacao"] = vf - vb
        if vb:
            r["variacao_pct"] = 100 * (vf - vb) / abs(vb)
        anos = af - ab
        base_metrica = r["variacao_pct"] if ind.get("pct") and vb else r["variacao"]
        por_ano = base_metrica / anos
        r["metrica"] = -por_ano if ind["melhor"] == "menor" else por_ano
        if ind["melhor"] == "neutro":
            r["metrica"] = None
        if ab in regiao and af in regiao:
            rv = regiao[af] - regiao[ab]
            r["regiao"] = {"inicio": regiao[ab], "fim": regiao[af], "variacao": rv,
                           "variacao_pct": 100 * rv / abs(regiao[ab]) if regiao[ab] else None}
    return r


def main():
    series = coletar()
    mandatos = []
    for m in MANDATOS:
        mandatos.append({k: v for k, v in m.items()} | {"indicadores": {}, "em_andamento": m["fim"] is None})

    # mede cada indicador em cada mandato e compara os mandatos entre si
    for ind in INDICADORES:
        if ind["id"] not in series:
            continue
        br, lat = series[ind["id"]]
        medidos = []
        for m in mandatos:
            r = medir(ind, br, lat, m)
            if r:
                m["indicadores"][ind["id"]] = r
                medidos.append(r)
        if ind["melhor"] == "neutro":
            for r in medidos:
                r.pop("metrica", None)
            continue
        ordem = sorted(medidos, key=lambda r: -r["metrica"])
        n = len(ordem)
        for pos, r in enumerate(ordem, 1):
            r["posicao"], r["total"] = pos, n
            r["nota"] = round(100 * (n - pos) / (n - 1)) if n > 1 else 50
            del r["metrica"]

    # nota de cada área = média das notas dos seus indicadores (0 = pior resultado entre os mandatos, 100 = melhor)
    for m in mandatos:
        vs = [r.get("veredito") for r in m["indicadores"].values() if r.get("veredito")]
        m["placar"] = {"melhor": vs.count("melhor"), "pior": vs.count("pior"), "igual": vs.count("igual"), "total": len(vs)}
        m["areas"] = {}
        for area in AREAS:
            notas = [m["indicadores"][i["id"]]["nota"] for i in INDICADORES
                     if i["area"] == area and i["id"] in m["indicadores"]]
            m["areas"][area] = round(sum(notas) / len(notas)) if notas else None

    saida = {
        "atualizado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M"),
        "areas": AREAS,
        "indicadores": [{k: v for k, v in i.items() if k not in ("fonte", "codigo")} |
                        {"fonte": {"wb": "Banco Mundial", "imf": "FMI (World Economic Outlook)"}.get(i["fonte"], "Banco Central do Brasil")}
                        for i in INDICADORES],
        # gráficos a partir de 1994 (inflação a partir de 1995, para a hiperinflação não achatar o resto da série)
        "series": {k: {"brasil": sorted((a, x) for a, x in v[0].items() if a >= (1995 if k == "inflacao" else 1994)),
                       "regiao": sorted((a, x) for a, x in v[1].items() if a >= (1995 if k == "inflacao" else 1994))}
                   for k, v in series.items()},
        "mandatos": mandatos,
        "avisos": avisos,
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"pronto: {len(series)} de {len(INDICADORES)} indicadores; avisos: {avisos}")


if __name__ == "__main__":
    main()
