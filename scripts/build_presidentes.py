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
import urllib.parse
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
# Blocos: os 3 primeiros medem resultados na vida da população e entram no placar.
# Os 3 seguintes ajudam a explicar esses resultados e não entram no placar.
BLOCOS = [
    {"nome": "Poder de compra", "tipo": "resultado",
     "descricao": "Se a renda cresce acima dos preços, permitindo comprar mais e pagar as despesas básicas."},
    {"nome": "Emprego e renda", "tipo": "resultado",
     "descricao": "Geração de empregos, evolução dos salários reais e qualidade das oportunidades de trabalho."},
    {"nome": "Pobreza e desigualdade", "tipo": "resultado",
     "descricao": "Se a pobreza diminui e se os ganhos chegam à população de baixa renda."},
    {"nome": "Sustentabilidade fiscal", "tipo": "fator",
     "descricao": "Se gastos, impostos e dívida pública seguem uma trajetória sustentável ou podem limitar os próximos governos."},
    {"nome": "Inflação e juros", "tipo": "fator",
     "descricao": "Tendência dos preços e dos juros, e o risco de perda futura do poder de compra."},
    {"nome": "Investimentos e produtividade", "tipo": "fator",
     "descricao": "Se o país investe e produz mais por trabalhador, criando condições para mais renda e emprego no futuro."},
]
AREAS = [b["nome"] for b in BLOCOS]
RESULTADOS = {b["nome"] for b in BLOCOS if b["tipo"] == "resultado"}
INDICADORES = [
    # 1. Poder de compra
    {"id": "salario_minimo", "nome": "Poder de compra do salário mínimo", "area": "Poder de compra", "fonte": "bcb_sm",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "R$ por mês, em valores de hoje", "casas": 0,
     "explica": "Quanto o salário mínimo compraria hoje, descontada toda a inflação desde então."},
    {"id": "comida", "nome": "Preço da comida", "area": "Poder de compra", "fonte": "bcb_ipca", "codigo": 1635,
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano (alimentos e bebidas)", "casas": 1,
     "explica": "Quanto a comida subiu por ano. Pesa mais para quem ganha menos, porque boa parte da renda vai para o mercado."},
    {"id": "tarifas", "nome": "Contas e tarifas", "area": "Poder de compra", "fonte": "bcb_ipca", "codigo": 4449,
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano (preços monitorados)", "casas": 1,
     "explica": "Alta de preços que dependem de decisão ou regra do governo: gasolina, luz, água, gás de cozinha, ônibus, remédios e planos de saúde."},
    {"id": "endividamento", "nome": "Famílias endividadas", "area": "Poder de compra", "fonte": "bcb", "codigo": 29037,
     "melhor": "menor", "tipo": "variacao", "unidade": "% da renda de um ano devida aos bancos", "casas": 1,
     "explica": "Quanto as famílias devem aos bancos em relação ao que ganham em 12 meses. Dívida alta tira dinheiro do consumo. Série desde 2005."},
    # 2. Emprego e renda
    {"id": "carteira", "nome": "Trabalhadores com carteira assinada", "area": "Emprego e renda", "fonte": "sidra_carteira",
     "melhor": "maior", "tipo": "variacao", "unidade": "% de quem trabalha", "casas": 1,
     "explica": "Dos brasileiros que trabalham, quantos são empregados de empresas privadas com carteira. Mede a qualidade do emprego. Pesquisa do IBGE desde 2012."},
    {"id": "renda_trabalho", "nome": "Renda média do trabalho", "area": "Emprego e renda", "fonte": "sidra_renda",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "R$ por mês, descontada a inflação", "casas": 0,
     "explica": "Quanto ganha, em média, quem trabalha, já descontada a inflação. Pesquisa do IBGE desde 2012."},
    {"id": "ocupacao", "nome": "Adultos trabalhando", "area": "Emprego e renda", "fonte": "wb", "codigo": "SL.EMP.TOTL.SP.ZS",
     "melhor": "maior", "tipo": "variacao", "unidade": "% da população com 15 anos ou mais", "casas": 1,
     "explica": "De todos os adultos, quantos de fato trabalham. Não depende de quem procura emprego, então é difícil de distorcer. Série longa, cobre todos os mandatos."},
    # 3. Pobreza e desigualdade
    {"id": "pobreza", "nome": "Pobreza", "area": "Pobreza e desigualdade", "fonte": "wb", "codigo": "SI.POV.UMIC",
     "melhor": "menor", "tipo": "variacao", "unidade": "% da população", "casas": 1,
     "explica": "Pessoas vivendo com menos de US$ 6,85 por dia, linha de pobreza do Banco Mundial para países de renda média como o Brasil."},
    {"id": "extrema_pobreza", "nome": "Extrema pobreza", "area": "Pobreza e desigualdade", "fonte": "wb", "codigo": "SI.POV.DDAY",
     "melhor": "menor", "tipo": "variacao", "unidade": "% da população", "casas": 1,
     "explica": "Pessoas vivendo com menos de US$ 2,15 por dia."},
    {"id": "gini", "nome": "Desigualdade de renda", "area": "Pobreza e desigualdade", "fonte": "wb", "codigo": "SI.POV.GINI",
     "melhor": "menor", "tipo": "variacao", "unidade": "índice de Gini, de 0 a 100", "casas": 1,
     "explica": "Quanto maior, mais concentrada é a renda. Mostra se os ganhos chegaram a quem ganha menos."},
    # 4. Sustentabilidade fiscal
    {"id": "impostos", "nome": "Peso dos impostos", "area": "Sustentabilidade fiscal", "fonte": "imf", "codigo": "rev",
     "melhor": "menor", "tipo": "variacao", "unidade": "% de tudo o que o país produz", "casas": 1,
     "explica": "Impostos e contribuições arrecadados por União, estados e municípios, em proporção da economia."},
    {"id": "gasto_total", "nome": "Gasto público", "area": "Sustentabilidade fiscal", "fonte": "imf", "codigo": "exp",
     "melhor": "neutro", "tipo": "variacao", "unidade": "% de tudo o que o país produz", "casas": 1,
     "explica": "Tudo o que União, estados e municípios gastam. Sem selo de melhor ou pior: depende do retorno que traz."},
    {"id": "divida", "nome": "Dívida pública", "area": "Sustentabilidade fiscal", "fonte": "imf", "codigo": "GGXWDG_NGDP",
     "melhor": "menor", "tipo": "variacao", "unidade": "% de tudo o que o país produz", "casas": 1,
     "explica": "Dívida bruta do governo. Quanto maior, mais impostos vão para pagar juros e menos sobra para os próximos governos."},
    # 5. Inflação e juros
    {"id": "inflacao", "nome": "Inflação", "area": "Inflação e juros", "fonte": "bcb_ipca", "codigo": 433,
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano (IPCA)", "casas": 1,
     "explica": "Quanto os preços subiram por ano, em média, durante o mandato."},
    {"id": "selic", "nome": "Juros básicos (Selic)", "area": "Inflação e juros", "fonte": "bcb_selic",
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano", "casas": 1,
     "explica": "Média da Selic no mandato. Ela puxa os juros do cartão, do crediário e do financiamento."},
    # 6. Investimentos e produtividade
    {"id": "investimento", "nome": "Investimento", "area": "Investimentos e produtividade", "fonte": "wb", "codigo": "NE.GDI.FTOT.ZS",
     "melhor": "maior", "tipo": "variacao", "unidade": "% de tudo o que o país produz", "casas": 1,
     "explica": "Quanto o país investe em fábricas, máquinas, obras e moradias. Investimento de hoje é emprego e renda de amanhã."},
    {"id": "produtividade", "nome": "Produtividade do trabalho", "area": "Investimentos e produtividade", "fonte": "wb", "codigo": "SL.GDP.PCAP.EM.KD",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "US$ produzidos por trabalhador por ano", "casas": 0,
     "explica": "Quanto cada trabalhador produz, em média. Sem ganho de produtividade, salários não sobem de forma sustentável."},
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


def _por_ano(mensal, desde=(1994, 7)):
    anos = {}
    for a, m, v in mensal:
        if (a, m) >= desde:
            anos.setdefault(a, []).append((m, v))
    return anos


def ipca_anual(codigo):
    """Variação acumulada no ano (só anos completos), a partir de uma série mensal do IPCA ou de um grupo dele."""
    out = {}
    for a, meses in _por_ano(serie_bcb(codigo, "01/01/1994"), (1995, 1)).items():
        if len(meses) < 12:
            continue
        f = 1.0
        for _, v in meses:
            f *= 1 + v / 100
        out[a] = round((f - 1) * 100, 2)
    return out


def selic_anual():
    """Média da Selic (anualizada) nos meses de cada ano completo."""
    out = {}
    for a, meses in _por_ano(serie_bcb(4189, "01/01/1994"), (1994, 7)).items():
        if len(meses) == 12 or (a == 1994 and len(meses) == 6):
            out[a] = round(sum(v for _, v in meses) / len(meses), 2)
    return out


def salario_minimo_real():
    """Salário mínimo de cada ano em reais de hoje (corrigido pelo IPCA até o último mês disponível)."""
    sm = {(a, m): v for a, m, v in serie_bcb(1619, "01/07/1994")}
    ipca = sorted((a, m, v) for a, m, v in serie_bcb(433, "01/07/1994"))
    indice, acc = {}, 1.0
    for a, m, v in ipca:
        acc *= 1 + v / 100
        indice[(a, m)] = acc
    ultimo = indice[max(indice)]
    out = {}
    for a, meses in _por_ano([(a, m, v) for (a, m), v in sm.items()], (1994, 7)).items():
        reais = [v * ultimo / indice[(a, m)] for m, v in meses if (a, m) in indice]
        if len(reais) == 12 or (a == 1994 and len(reais) == 6):
            out[a] = round(sum(reais) / len(reais), 2)
    return out


TRIMESTRAL = {}  # id -> [(ano, trimestre, valor)] para o dado mais recente do governo atual
MENSAL = {}      # id -> [(ano, mes, valor)]


def _sidra_trimestral(url, chave):
    linhas = json.loads(baixar(url))
    pontos = []
    for row in linhas[1:]:
        per = next((str(v) for k, v in row.items() if k.endswith("C") and str(v).isdigit() and len(str(v)) == 6), None)
        try:
            val = float(row.get("V"))
        except (TypeError, ValueError):
            continue
        if per:
            pontos.append((int(per[:4]), int(per[4:]), val))
    pontos.sort()
    TRIMESTRAL[chave] = pontos
    por_ano = {}
    for a, q, v in pontos:
        por_ano.setdefault(a, []).append(v)
    # ano conta com pelo menos 2 trimestres (a pesquisa teve lacunas na pandemia)
    return {a: round(sum(v) / len(v), 2) for a, v in por_ano.items() if len(v) >= 2 and (a < HOJE.year)}


def carteira_assinada():
    """IBGE, PNAD Contínua (tabela 4097): % dos ocupados que são empregados do setor privado com carteira."""
    return _sidra_trimestral("https://apisidra.ibge.gov.br/values/t/4097/n1/all/v/4108/p/all/c11913/31722?formato=json", "carteira")


def renda_trabalho():
    """IBGE, PNAD Contínua (tabela 5436): rendimento médio real habitual de todos os trabalhos."""
    return _sidra_trimestral("https://apisidra.ibge.gov.br/values/t/5436/n1/all/v/5933/p/all?formato=json", "renda_trabalho")


MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def mais_recente(inicio_mandato):
    """Dado mais recente possível de cada indicador para o governo atual (mensal ou trimestral, não só o último ano fechado)."""
    a0 = int(inicio_mandato[:4])
    out = {}
    # inflação, comida e tarifas: acumulado dos últimos 12 meses e média anualizada desde a posse
    for iid, cod in (("inflacao", 433), ("comida", 1635), ("tarifas", 4449)):
        try:
            mensal = sorted(serie_bcb(cod, f"01/01/{a0 - 1}"))
            ult = mensal[-12:]
            f12 = 1.0
            for _, _, v in ult:
                f12 *= 1 + v / 100
            desde = [v for a, m, v in mensal if a >= a0]
            fm = 1.0
            for v in desde:
                fm *= 1 + v / 100
            a, m, _ = mensal[-1]
            out[iid] = {"rotulo": f"12 meses até {MES[m - 1]}/{a}", "valor": round((f12 - 1) * 100, 2),
                        "media": round((fm ** (12 / len(desde)) - 1) * 100, 2) if desde else None, "quando": a + m / 12}
        except Exception as e:  # noqa: BLE001
            avisos.append(f"recente {iid}: {e}")
    try:
        mensal = sorted(serie_bcb(4189, f"01/01/{a0}"))
        a, m, v = mensal[-1]
        out["selic"] = {"rotulo": f"{MES[m - 1]}/{a}", "valor": v,
                        "media": round(sum(x for _, _, x in mensal) / len(mensal), 2), "quando": a + m / 12}
    except Exception as e:  # noqa: BLE001
        avisos.append(f"recente selic: {e}")
    try:
        mensal = sorted(serie_bcb(29037, f"01/01/{a0}"))
        a, m, v = mensal[-1]
        out["endividamento"] = {"rotulo": f"{MES[m - 1]}/{a}", "valor": v, "quando": a + m / 12}
    except Exception as e:  # noqa: BLE001
        avisos.append(f"recente endividamento: {e}")
    try:
        sm = sorted(serie_bcb(1619, f"01/01/{a0}"))
        a, m, v = sm[-1]
        out["salario_minimo"] = {"rotulo": f"{MES[m - 1]}/{a}", "valor": v, "quando": a + m / 12}  # já está em reais de hoje
    except Exception as e:  # noqa: BLE001
        avisos.append(f"recente salario_minimo: {e}")
    for iid in ("carteira", "renda_trabalho"):
        pts = TRIMESTRAL.get(iid)
        if pts:
            a, q, v = pts[-1]
            out[iid] = {"rotulo": f"{q}º trimestre de {a}", "valor": v, "quando": a + q * 3 / 12}
    return out


def projecoes():
    """Só para o governo atual. FMI (World Economic Outlook) e boletim Focus do Banco Central."""
    out = {"fmi": [], "focus": [], "avisos": []}
    anos = list(range(HOJE.year, HOJE.year + 4))
    imf = [("divida", "Dívida pública", "GGXWDG_NGDP", "% do PIB", "menor"),
           ("desemprego", "Desemprego", "LUR", "% da força de trabalho", "menor"),
           ("inflacao", "Inflação", "PCPIPCH", "% ao ano", "menor"),
           ("crescimento", "Crescimento da economia", "NGDP_RPCH", "% ao ano", "maior")]
    for iid, nome, cod, un, melhor in imf:
        try:
            j = json.loads(baixar(f"https://www.imf.org/external/datamapper/api/v1/{cod}/BRA"))
            vals = j.get("values", {}).get(cod, {}).get("BRA", {})
            pts = [(a, round(float(vals[str(a)]), 1)) for a in [HOJE.year - 1] + anos if str(a) in vals and vals[str(a)] is not None]
            if pts:
                out["fmi"].append({"id": iid, "nome": nome, "unidade": un, "melhor": melhor, "pontos": pts})
        except Exception as e:  # noqa: BLE001
            out["avisos"].append(f"FMI {cod}: {e}")
    focus = [("IPCA", "Inflação (IPCA)", "% no ano"), ("Selic", "Selic no fim do ano", "% ao ano"), ("PIB Total", "Crescimento da economia", "% no ano")]
    for ind, nome, un in focus:
        try:
            filtro = urllib.parse.quote(f"Indicador eq '{ind}' and baseCalculo eq 0")
            url = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
                   f"?$top=60&$filter={filtro}&$orderby=Data%20desc&$format=json&$select=Indicador,Data,DataReferencia,Mediana")
            dados = json.loads(baixar(url)).get("value", [])
            if not dados:
                continue
            ultima = dados[0]["Data"]
            pts = sorted((int(d["DataReferencia"]), round(float(d["Mediana"]), 2)) for d in dados
                         if d["Data"] == ultima and str(d["DataReferencia"]).isdigit() and int(d["DataReferencia"]) in anos)
            if pts:
                out["focus"].append({"nome": nome, "unidade": un, "data": ultima, "pontos": pts})
        except Exception as e:  # noqa: BLE001
            out["avisos"].append(f"Focus {ind}: {e}")
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
            elif ind["fonte"] == "bcb_ipca":
                br, lat = ipca_anual(ind["codigo"]), {}
            elif ind["fonte"] == "bcb_selic":
                br, lat = selic_anual(), {}
            elif ind["fonte"] == "bcb_sm":
                br, lat = salario_minimo_real(), {}
            elif ind["fonte"] == "sidra_carteira":
                br, lat = carteira_assinada(), {}
            elif ind["fonte"] == "sidra_renda":
                br, lat = renda_trabalho(), {}
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


def medir(ind, serie, regiao, m, recente=None):
    ultimo = max(serie)
    fim = m["fim"] if m["fim"] else ultimo
    fim = min(fim, ultimo)
    if fim <= m["base"] and not recente:
        return None
    r = {"id": ind["id"]}
    # como recebeu e como entregou (vale para todos os indicadores)
    ab, vb = valor_ate(serie, m["base"], m["base"] - 2)
    af, vf = valor_ate(serie, fim, m["base"] + 1)
    rot = None
    if recente and recente.get("valor") is not None:
        af, vf, rot = recente["quando"], recente["valor"], recente["rotulo"]
    if vb is not None and vf is not None and af > ab:
        r["recebeu"] = {"ano": ab, "valor": vb}
        r["entregou"] = {"ano": int(af), "valor": vf} | ({"rotulo": rot} if rot else {})
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
        if recente and recente.get("media") is not None:
            r["media"] = recente["media"]
            r["anos"] = [m["base"] + 1, int(recente["quando"])]
            r["media_rotulo"] = f"desde a posse até {recente['rotulo'].split('até ')[-1]}"
        elif not anos:
            return None
        else:
            r["media"] = sum(serie[a] for a in anos) / len(anos)
            r["anos"] = [anos[0], anos[-1]]
        r["metrica"] = -r["media"] if ind["melhor"] == "menor" else r["media"]
        anos_r = [a for a in anos if a in regiao]
        if anos_r and len(anos_r) == len(anos):
            r["regiao_media"] = sum(regiao[a] for a in anos_r) / len(anos_r)
    else:
        ab, vb = valor_ate(serie, m["base"], m["base"] - 2)
        af, vf = valor_ate(serie, fim, m["base"] + 1)
        if recente and recente.get("valor") is not None:
            af, vf = recente["quando"], recente["valor"]
        if vb is None or vf is None or af <= ab:
            return None
        r["inicio"] = {"ano": ab, "valor": vb}
        r["fim"] = {"ano": int(af), "valor": vf}
        r["variacao"] = vf - vb
        if vb:
            r["variacao_pct"] = 100 * (vf - vb) / abs(vb)
        anos = af - ab
        base_metrica = r["variacao_pct"] if ind.get("pct") and vb else r["variacao"]
        por_ano = base_metrica / anos
        r["metrica"] = -por_ano if ind["melhor"] == "menor" else por_ano
        if ind["melhor"] == "neutro":
            r["metrica"] = None
        if ab in regiao and isinstance(af, int) and af in regiao:
            rv = regiao[af] - regiao[ab]
            r["regiao"] = {"inicio": regiao[ab], "fim": regiao[af], "variacao": rv,
                           "variacao_pct": 100 * rv / abs(regiao[ab]) if regiao[ab] else None}
    return r


def main():
    series = coletar()
    atual = next(m for m in MANDATOS if m["fim"] is None)
    recentes = mais_recente(atual["inicio"])
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
            r = medir(ind, br, lat, m, recentes.get(ind["id"]) if m["fim"] is None else None)
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
        area_de = {i["id"]: i["area"] for i in INDICADORES}
        vs = [r.get("veredito") for k, r in m["indicadores"].items() if r.get("veredito") and area_de[k] in RESULTADOS]
        m["placar"] = {"melhor": vs.count("melhor"), "pior": vs.count("pior"), "igual": vs.count("igual"), "total": len(vs)}
        m["areas"] = {}
        for area in AREAS:
            notas = [m["indicadores"][i["id"]]["nota"] for i in INDICADORES
                     if i["area"] == area and i["id"] in m["indicadores"] and "nota" in m["indicadores"][i["id"]]]
            m["areas"][area] = round(sum(notas) / len(notas)) if notas else None

    # herança: como estava cada indicador ao assumir, comparado à média histórica, e se vinha melhorando ou piorando
    for ind in INDICADORES:
        if ind["id"] not in series or ind["melhor"] == "neutro":
            continue
        br = series[ind["id"]][0]
        media_hist = sum(br.values()) / len(br)
        for m in mandatos:
            ab, vb = valor_ate(br, m["base"], m["base"] - 2)
            if vb is None:
                continue
            pior_que_media = vb > media_hist if ind["melhor"] == "menor" else vb < media_hist
            h = {"ano": ab, "valor": vb, "media_historica": round(media_hist, 2),
                 "situacao": "pior" if pior_que_media else "melhor"}
            a2, v2 = valor_ate(br, ab - 2, ab - 3)
            if v2 is not None and abs(vb - v2) > max(abs(v2) * 0.01, 1e-9):
                piorando = (vb > v2) if ind["melhor"] == "menor" else (vb < v2)
                h["tendencia"] = "piorando" if piorando else "melhorando"
                h["desde"] = a2
            m.setdefault("heranca", {})[ind["id"]] = h

    saida = {
        "atualizado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M"),
        "areas": AREAS,
        "blocos": BLOCOS,
        "projecao": projecoes(),
        "indicadores": [{k: v for k, v in i.items() if k not in ("fonte", "codigo")} |
                        {"fonte": {"wb": "Banco Mundial", "imf": "FMI (World Economic Outlook)", "sidra_carteira": "IBGE (PNAD Contínua)",
                                   "sidra_renda": "IBGE (PNAD Contínua)"}.get(i["fonte"], "Banco Central do Brasil")}
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
