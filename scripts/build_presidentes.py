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
import io
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
    # resultados observados na vida da população (contam no placar)
    {"nome": "Poder de compra", "tipo": "resultado", "secao": "principal",
     "descricao": "Se a renda de quem ganha pouco cresceu acima do custo de vida."},
    {"nome": "Emprego e renda", "tipo": "resultado", "secao": "principal",
     "descricao": "Desemprego, carteira assinada, trabalho precário e renda real do trabalho."},
    {"nome": "Pobreza e desigualdade", "tipo": "resultado", "secao": "principal",
     "descricao": "Se a pobreza caiu e se os ganhos chegaram à população de baixa renda."},
    # custo de vida e acesso ao consumo (contam no placar): o preço comparado ao salário mínimo
    {"nome": "Alimentação", "tipo": "resultado", "secao": "custo",
     "descricao": "Quantas horas de trabalho com salário mínimo custa a cesta básica."},
    {"nome": "Moradia e energia", "tipo": "resultado", "secao": "custo",
     "descricao": "Aluguel e conta de luz comparados ao salário mínimo."},
    {"nome": "Transporte e combustível", "tipo": "resultado", "secao": "custo",
     "descricao": "Passagem de ônibus e gasolina comparadas ao salário mínimo."},
    {"nome": "Bens de consumo", "tipo": "resultado", "secao": "custo",
     "descricao": "Celular, computador, eletrodomésticos, roupas, moto e carro comparados ao salário mínimo."},
    # fatores que explicam os resultados (não contam no placar)
    {"nome": "Sustentabilidade fiscal", "tipo": "fator", "secao": "fator",
     "descricao": "Receitas, gastos, resultado primário e dívida: desequilíbrios que podem limitar os próximos governos."},
    {"nome": "Inflação e juros", "tipo": "fator", "secao": "fator",
     "descricao": "Inflação geral, inflação das famílias de baixa renda e juros básicos."},
]
AREAS = [b["nome"] for b in BLOCOS]
RESULTADOS = {b["nome"] for b in BLOCOS if b["tipo"] == "resultado"}

# subitens do IPCA (IBGE, SIDRA, classificação 315) usados nos índices de acessibilidade
SUBITENS = {"alimentacao": 7171, "aluguel": 7448, "energia": 7485, "onibus": 7628, "celular": 7794,
            "computador": 7547, "eletro": 7522, "roupas": 7559, "moto": 7654, "carro": 7641}
ACESS_UNID = "índice de acessibilidade: compra com um salário mínimo (dez/1999 = 100)"
ACESS_EXPL = ("Quanto do item um salário mínimo compra, comparando a alta do salário com a alta do preço (IPCA). "
              "Se sobe, ficou mais acessível; se cai, ficou mais caro para quem ganha o mínimo.")

def _acess(iid, nome, area, sub, conf="média"):
    return {"id": iid, "nome": nome, "area": area, "fonte": "acess", "codigo": sub, "melhor": "maior", "tipo": "variacao",
            "pct": True, "unidade": ACESS_UNID, "casas": 0, "explica": ACESS_EXPL, "confianca": conf,
            "limite": "Mostra a variação de preço do item, não o preço em reais. Série do IBGE desde ago/1999.",
            "fonte_txt": "IBGE (IPCA por subitem) e Banco Central (salário mínimo)"}

INDICADORES = [
    # 1. Poder de compra
    {"id": "salario_minimo", "nome": "Poder de compra do salário mínimo", "area": "Poder de compra", "fonte": "bcb_sm",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "R$ por mês, em valores de hoje (INPC)", "casas": 0,
     "explica": "O salário mínimo corrigido pela inflação das famílias que ganham até 5 salários mínimos (INPC). Mostra se o mínimo comprou mais ou menos.",
     "confianca": "alta", "limite": "Mede quem recebe o mínimo e aposentados que ganham o piso.", "fonte_txt": "Banco Central (salário mínimo) e IBGE (INPC)"},
    {"id": "endividamento", "nome": "Famílias endividadas", "area": "Poder de compra", "fonte": "bcb", "codigo": 29037,
     "melhor": "menor", "tipo": "variacao", "unidade": "% da renda de um ano devida aos bancos", "casas": 1,
     "explica": "Quanto as famílias devem aos bancos em relação ao que ganham em 12 meses. Dívida alta tira dinheiro das despesas básicas.",
     "confianca": "alta", "limite": "Série desde 2005. Não conta dívidas fora do sistema bancário (agiota, carnê de loja).", "fonte_txt": "Banco Central"},
    # 2. Emprego e renda
    {"id": "desemprego", "nome": "Desemprego", "area": "Emprego e renda", "fonte": "wb", "codigo": "SL.UEM.TOTL.ZS",
     "melhor": "menor", "tipo": "variacao", "unidade": "% de quem trabalha ou procura trabalho", "casas": 1,
     "explica": "Quem procurou emprego e não achou. Não conta quem desistiu de procurar, por isso vale olhar junto com a carteira assinada.",
     "confianca": "média", "limite": "Estimativa padronizada da OIT a partir das pesquisas do IBGE. A pesquisa mudou em 2012.", "fonte_txt": "Banco Mundial / OIT"},
    {"id": "carteira", "nome": "Trabalhadores com carteira assinada", "area": "Emprego e renda", "fonte": "sidra_carteira",
     "melhor": "maior", "tipo": "variacao", "unidade": "% de quem trabalha", "casas": 1,
     "explica": "Dos que trabalham, quantos são empregados de empresas privadas com carteira. Mede a qualidade do emprego.",
     "confianca": "alta", "limite": "Pesquisa do IBGE só existe desde 2012.", "fonte_txt": "IBGE (PNAD Contínua)"},
    {"id": "renda_trabalho", "nome": "Renda média do trabalho", "area": "Emprego e renda", "fonte": "sidra_renda",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "R$ por mês, descontada a inflação", "casas": 0,
     "explica": "Quanto ganha, em média, quem trabalha, já descontada a inflação.",
     "confianca": "alta", "limite": "Pesquisa do IBGE desde 2012. Média de todos os trabalhadores, não só os de baixa renda.", "fonte_txt": "IBGE (PNAD Contínua)"},
    # 3. Pobreza e desigualdade
    {"id": "pobreza", "nome": "Pobreza", "area": "Pobreza e desigualdade", "fonte": "wb", "codigo": "SI.POV.UMIC",
     "melhor": "menor", "tipo": "variacao", "unidade": "% da população", "casas": 1,
     "explica": "Pessoas vivendo com menos de US$ 6,85 por dia, linha do Banco Mundial para países como o Brasil.",
     "confianca": "alta", "limite": "Publicado com um ou dois anos de atraso.", "fonte_txt": "Banco Mundial (com dados do IBGE)"},
    {"id": "extrema_pobreza", "nome": "Extrema pobreza", "area": "Pobreza e desigualdade", "fonte": "wb", "codigo": "SI.POV.DDAY",
     "melhor": "menor", "tipo": "variacao", "unidade": "% da população", "casas": 1,
     "explica": "Pessoas vivendo com menos de US$ 2,15 por dia.",
     "confianca": "alta", "limite": "Publicado com um ou dois anos de atraso.", "fonte_txt": "Banco Mundial (com dados do IBGE)"},
    {"id": "renda_pobres", "nome": "Fatia da renda dos 20% mais pobres", "area": "Pobreza e desigualdade", "fonte": "wb", "codigo": "SI.DST.FRST.20",
     "melhor": "maior", "tipo": "variacao", "unidade": "% de toda a renda do país", "casas": 1,
     "explica": "Quanto da renda total fica com os 20% mais pobres. Se sobe, os ganhos chegaram a quem ganha menos.",
     "confianca": "alta", "limite": "Publicado com um ou dois anos de atraso.", "fonte_txt": "Banco Mundial (com dados do IBGE)"},
    # 4. Alimentação
    {"id": "cesta_horas", "nome": "Horas de trabalho para comprar a cesta básica", "area": "Alimentação", "fonte": "cesta",
     "melhor": "menor", "tipo": "variacao", "unidade": "horas de trabalho com salário mínimo", "casas": 0,
     "explica": "Quantas horas quem ganha o salário mínimo precisa trabalhar para comprar a cesta básica do DIEESE (jornada de 220 horas por mês).",
     "confianca": "alta", "limite": "Cesta da cidade de São Paulo, a série mais longa do DIEESE. Em outras capitais o valor muda.", "fonte_txt": "DIEESE (via Ipeadata) e Banco Central"},
    # 5. Moradia e energia
    _acess("acess_aluguel", "Aluguel", "Moradia e energia", "aluguel"),
    _acess("acess_energia", "Conta de luz", "Moradia e energia", "energia", "alta"),
    # 6. Transporte e combustível
    _acess("acess_onibus", "Passagem de ônibus", "Transporte e combustível", "onibus", "alta"),
    {"id": "litros_gasolina", "nome": "Litros de gasolina com um salário mínimo", "area": "Transporte e combustível", "fonte": "anp",
     "melhor": "maior", "tipo": "variacao", "pct": True, "unidade": "litros por salário mínimo", "casas": 0,
     "explica": "Quantos litros de gasolina comum um salário mínimo compra, pelo preço médio nos postos do país.",
     "confianca": "alta", "limite": "Levantamento de preços da ANP desde jul/2001.", "fonte_txt": "ANP e Banco Central"},
    # 7. Bens de consumo
    _acess("acess_celular", "Celular", "Bens de consumo", "celular"),
    _acess("acess_computador", "Computador", "Bens de consumo", "computador"),
    _acess("acess_eletro", "Eletrodomésticos", "Bens de consumo", "eletro"),
    _acess("acess_roupas", "Roupas", "Bens de consumo", "roupas", "alta"),
    _acess("acess_moto", "Moto", "Bens de consumo", "moto"),
    _acess("acess_carro", "Carro novo", "Bens de consumo", "carro"),
    # 9. Sustentabilidade fiscal
    {"id": "impostos", "nome": "Peso dos impostos", "area": "Sustentabilidade fiscal", "fonte": "imf", "codigo": "rev",
     "melhor": "menor", "tipo": "variacao", "unidade": "% de tudo o que o país produz", "casas": 1,
     "explica": "Impostos e contribuições de União, estados e municípios em proporção da economia.",
     "confianca": "alta", "limite": "Último ano pode ser estimativa do FMI.", "fonte_txt": "FMI"},
    {"id": "primario", "nome": "Resultado primário", "area": "Sustentabilidade fiscal", "fonte": "bcb_primario", "codigo": 5793,
     "melhor": "maior", "tipo": "variacao", "unidade": "% do PIB (negativo = gastou mais do que arrecadou, sem contar juros)", "casas": 1,
     "explica": "Se o governo arrecada mais do que gasta antes de pagar juros. Déficit seguido faz a dívida crescer.",
     "confianca": "alta", "limite": "Setor público consolidado, acumulado em 12 meses. Série do Banco Central desde 2002.", "fonte_txt": "Banco Central"},
    {"id": "divida", "nome": "Dívida pública", "area": "Sustentabilidade fiscal", "fonte": "imf", "codigo": "GGXWDG_NGDP",
     "melhor": "menor", "tipo": "variacao", "unidade": "% de tudo o que o país produz", "casas": 1,
     "explica": "Dívida bruta do governo. Quanto maior, mais imposto vai para juros e menos sobra para os próximos governos.",
     "confianca": "alta", "limite": "Último ano pode ser estimativa do FMI.", "fonte_txt": "FMI"},
    # 10. Inflação e juros
    {"id": "inpc", "nome": "Inflação de quem ganha menos (INPC)", "area": "Inflação e juros", "fonte": "bcb_ipca", "codigo": 188,
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano", "casas": 1,
     "explica": "Inflação das famílias que ganham até 5 salários mínimos, média do mandato.",
     "confianca": "alta", "limite": "Já está embutida no poder de compra do salário mínimo; aparece aqui como contexto, não entra no placar.", "fonte_txt": "IBGE (via Banco Central)"},
    {"id": "selic", "nome": "Juros básicos (Selic)", "area": "Inflação e juros", "fonte": "bcb_selic",
     "melhor": "menor", "tipo": "media", "unidade": "% ao ano", "casas": 1,
     "explica": "Média da Selic no mandato. Puxa os juros do cartão, do crediário e do financiamento.",
     "confianca": "alta", "limite": "Juros ao consumidor são bem maiores que a Selic.", "fonte_txt": "Banco Central"},
    # 11. Investimentos e produtividade
]

# ------------------------------------------------ nível de vida: referência adequada e escala de 0 a 100
# Cada indicador recebe uma nota de nível (0 = pior situação, 100 = padrão adequado), calculada sempre do mesmo jeito.
# "fixa": valor adequado definido por norma ou meta pública; "historica": melhor e pior momento do Brasil desde o início da série.
REFERENCIAS = {
    "salario_minimo": {"tipo": "smn", "texto": "100 = salário mínimo igual ao salário mínimo necessário calculado pelo DIEESE, o valor que cobriria as despesas básicas de uma família de 4 pessoas, como prevê a Constituição (art. 7º, IV)."},
    "endividamento": {"tipo": "historica", "texto": "Escala entre o menor e o maior endividamento das famílias registrado desde 2005."},
    "desemprego": {"tipo": "fixa", "bom": 5.0, "texto": "100 = desemprego de 5%, nível próximo da média dos países da OCDE; 0 = pior desemprego do Brasil desde 1995."},
    "carteira": {"tipo": "historica", "texto": "Escala entre a menor e a maior fatia de trabalhadores com carteira desde 2012."},
    "renda_trabalho": {"tipo": "historica", "texto": "Escala entre a menor e a maior renda real do trabalho desde 2012."},
    "pobreza": {"tipo": "ods", "texto": "100 = metade da pobreza de 2015, a meta 1.2 dos Objetivos de Desenvolvimento Sustentável da ONU para 2030; 0 = pior nível do Brasil desde 1995."},
    "extrema_pobreza": {"tipo": "fixa", "bom": 3.0, "texto": "100 = no máximo 3% da população, a meta do Banco Mundial para acabar com a extrema pobreza; 0 = pior nível do Brasil desde 1995."},
    "renda_pobres": {"tipo": "historica", "texto": "Escala entre a menor e a maior fatia de renda dos 20% mais pobres desde 1995."},
    "cesta_horas": {"tipo": "fixa", "bom": 55.0, "ruim": 220.0, "texto": "100 = cesta básica custando até 55 horas (25% de uma jornada de 220 horas; famílias de baixa renda gastam de 20% a 25% da renda com alimentação, segundo a POF/IBGE 2017-2018); 0 = cesta custando o mês inteiro de trabalho."},
}
for _iid in ("acess_aluguel", "acess_energia", "acess_onibus", "litros_gasolina", "acess_celular", "acess_computador",
             "acess_eletro", "acess_roupas", "acess_moto", "acess_carro"):
    REFERENCIAS[_iid] = {"tipo": "historica", "texto": "Não existe preço de referência oficial em reais para este item. A escala vai do momento em que ele esteve menos acessível (0) ao mais acessível (100) para quem ganha o salário mínimo, desde o início da série."}


def nota_nivel(ind, valor, serie, ano=None, smn_ratio=None):
    """Converte um valor em nota de nível de vida (0 a 100) pela referência do indicador."""
    ref = REFERENCIAS.get(ind["id"])
    if not ref or valor is None or not serie:
        return None
    menor_melhor = ind["melhor"] == "menor"
    vals = list(serie.values())
    pior = max(vals) if menor_melhor else min(vals)
    if ref["tipo"] == "smn":
        return round(max(0.0, min(100.0, smn_ratio))) if smn_ratio is not None else None
    if ref["tipo"] == "historica":
        bom = min(vals) if menor_melhor else max(vals)
    elif ref["tipo"] == "ods":
        if 2015 not in serie:
            return None
        bom = serie[2015] / 2
    else:
        bom = ref["bom"]
        pior = ref.get("ruim", pior)
    if bom == pior:
        return None
    return round(max(0.0, min(100.0, 100 * (valor - pior) / (bom - pior))))


# ------------------------------------------------ tags de atenção histórica
# Critério: choque externo ou desastre natural de grande escala, reconhecido por fonte oficial, que alterou
# preços, emprego ou renda no período. A tag só contextualiza: não muda nenhuma nota.
TAGS = [
    {"id": "asia_russia", "nome": "Crises financeiras da Ásia e da Rússia", "inicio": "1997-07", "fim": "1999-01",
     "impactos": "Fuga de capitais, alta forte dos juros e pressão sobre o emprego.",
     "afeta": ["desemprego", "selic"], "fonte": "Banco Central do Brasil (Relatórios Anuais 1997 e 1998)"},
    {"id": "energia_2001", "nome": "Crise de energia e racionamento", "inicio": "2001-06", "fim": "2002-02",
     "impactos": "Corte obrigatório de consumo de energia, freio na produção e no emprego.",
     "afeta": ["desemprego", "acess_energia"], "fonte": "Câmara de Gestão da Crise de Energia Elétrica (2001)"},
    {"id": "crise_2008", "nome": "Crise financeira global", "inicio": "2008-09", "fim": "2009-12",
     "impactos": "Queda das exportações e do crédito, demissões no fim de 2008 e início de 2009.",
     "afeta": ["desemprego", "carteira", "renda_trabalho"], "fonte": "IBGE e Banco Central do Brasil"},
    {"id": "hidrica_2014", "nome": "Crise hídrica no Sudeste", "inicio": "2014-01", "fim": "2015-12",
     "impactos": "Seca nos reservatórios, energia mais cara (bandeiras tarifárias) e falta de água em São Paulo.",
     "afeta": ["acess_energia"], "fonte": "Agência Nacional de Águas e ANEEL"},
    {"id": "covid", "nome": "Pandemia de Covid-19", "inicio": "2020-03", "fim": "2022-12",
     "impactos": "Paralisação da atividade, perda de empregos em 2020, auxílio emergencial alterando pobreza e renda, e alta de preços de alimentos.",
     "afeta": ["desemprego", "carteira", "renda_trabalho", "pobreza", "extrema_pobreza", "cesta_horas"], "fonte": "Organização Mundial da Saúde e IBGE"},
    {"id": "ucrania", "nome": "Guerra na Ucrânia", "inicio": "2022-02", "fim": "2022-12",
     "impactos": "Alta mundial de combustíveis, fertilizantes e alimentos.",
     "afeta": ["litros_gasolina", "cesta_horas", "inpc"], "fonte": "FMI (World Economic Outlook, out/2022)"},
    {"id": "rs_2024", "nome": "Enchentes no Rio Grande do Sul", "inicio": "2024-04", "fim": "2024-07",
     "impactos": "Maior desastre climático do estado: perdas na produção, alta pontual de alimentos e efeito sobre o emprego regional.",
     "afeta": ["cesta_horas", "inpc"], "fonte": "Defesa Civil do RS e IBGE"},
]


def tags_do_mandato(m):
    ini = m["inicio"][:7]
    fim = (m["termino"] or HOJE.isoformat())[:7]
    return [t["id"] for t in TAGS if t["inicio"] <= fim and t["fim"] >= ini]

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


def codigo_imf_primario():
    try:
        lista = json.loads(baixar("https://www.imf.org/external/datamapper/api/v1/indicators")).get("indicators", {})
    except Exception as e:  # noqa: BLE001
        avisos.append(f"lista de indicadores do FMI: {e}")
        return None
    cands = [(k, v.get("label", "")) for k, v in lista.items() if "primary" in str(v.get("label", "")).lower()
             and ("balance" in str(v.get("label", "")).lower() or "net lending" in str(v.get("label", "")).lower())]
    if cands:
        avisos_info.append(f"FMI resultado primário: {cands[0][0]} ({cands[0][1]})")
        return cands[0][0]
    avisos.append("FMI: indicador de resultado primário não encontrado na lista")
    return None


def serie_imf(codigo):
    """FMI (World Economic Outlook). Descarta o ano corrente e projeções."""
    if codigo == "auto_primario":
        codigo = codigo_imf_primario()
        if not codigo:
            return {}
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
    ipca = sorted((a, m, v) for a, m, v in serie_bcb(188, "01/07/1994"))  # INPC: inflação de quem ganha até 5 mínimos
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


# ------------------------------------------------ custo de vida: preços comparados ao salário mínimo

_CACHE = {}


def sm_mensal():
    if "sm" not in _CACHE:
        _CACHE["sm"] = {(a, m): v for a, m, v in serie_bcb(1619, "01/07/1994")}
    return _CACHE["sm"]


def subitens_ipca():
    """Índice de preço (dez/1999 = 100) de cada subitem do IPCA, juntando as tabelas do IBGE de 1999 até hoje."""
    if "sub" in _CACHE:
        return _CACHE["sub"]
    cods = ",".join(str(c) for c in SUBITENS.values())
    var = {}
    for t in (655, 2938, 1419, 7060):
        url = f"https://apisidra.ibge.gov.br/values/t/{t}/n1/all/v/63/p/all/c315/{cods}?formato=json"
        try:
            linhas = json.loads(baixar(url, timeout=180))
        except Exception as e:  # noqa: BLE001
            avisos.append(f"IPCA subitens tabela {t}: {e}")
            continue
        for row in linhas[1:]:
            vals = [str(v) for k, v in row.items() if k.endswith("C")]
            per = next((v for v in vals if v.isdigit() and len(v) == 6 and v[:2] in ("19", "20")), None)
            cat = next((int(v) for v in vals if v.isdigit() and int(v) in SUBITENS.values()), None)
            try:
                val = float(row.get("V"))
            except (TypeError, ValueError):
                continue
            if per and cat:
                var.setdefault(cat, {})[(int(per[:4]), int(per[4:]))] = val
    idx = {}
    for cat, mv in var.items():
        nivel, serie = 100.0, {}
        for (a, m) in sorted(mv):
            if (a, m) <= (1999, 12):
                if (a, m) == (1999, 12):
                    serie[(a, m)] = 100.0
                continue
            nivel *= 1 + mv[(a, m)] / 100
            serie[(a, m)] = nivel
        idx[cat] = serie
    _CACHE["sub"] = idx
    return idx


def _anual_media(mensal_dict):
    por_ano = {}
    for (a, m), v in mensal_dict.items():
        por_ano.setdefault(a, []).append(v)
    return {a: round(sum(v) / len(v), 2) for a, v in por_ano.items() if len(v) == 12}


def acessibilidade_mensal(sub):
    """Quanto do item um salário mínimo compra, com dez/1999 = 100."""
    cat = SUBITENS[sub]
    precos = subitens_ipca().get(cat, {})
    sm = sm_mensal()
    if (1999, 12) not in precos or (1999, 12) not in sm:
        return {}
    base = sm[(1999, 12)] / precos[(1999, 12)]
    return {k: round(100 * (sm[k] / p) / base, 2) for k, p in precos.items() if k in sm}


def gasolina_mensal():
    """Preço médio mensal da gasolina comum no Brasil (ANP), desde jul/2001."""
    if "gas" in _CACHE:
        return _CACHE["gas"]
    import openpyxl
    urls = ["https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/2001-2012/mensal-brasil-2001-a-2012.xlsx",
            "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/mensal/mensal-brasil-desde-jan2013.xlsx"]
    out = {}
    for url in urls:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(baixar(url, timeout=180)), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"ANP {url.rsplit('/', 1)[-1]}: {e}")
            continue
        antes, amostra = len(out), []
        for ws in wb.worksheets:
            cab = None
            for row in ws.iter_rows(values_only=True):
                cels = [" ".join(norm_txt(c).upper().split()) if c is not None else "" for c in row]
                if len(amostra) < 12 and any(cels):
                    amostra.append([c for c in cels if c][:6])
                if cab is None:
                    if any("PRODUTO" in c for c in cels) and any("PRECO MEDIO REVENDA" in c for c in cels):
                        cab = cels
                        i_mes = next(i for i, c in enumerate(cab) if c in ("MES", "DATA") or c.startswith("MES") or c.startswith("DATA"))
                        i_prod = next(i for i, c in enumerate(cab) if "PRODUTO" in c)
                        i_preco = next(i for i, c in enumerate(cab) if "PRECO MEDIO REVENDA" in c)
                    continue
                prod = cels[i_prod] if i_prod < len(cels) else ""
                if "GASOLINA" not in prod or "ADITIVADA" in prod or "PREMIUM" in prod or "AVIACAO" in prod:
                    continue
                d, preco = row[i_mes], row[i_preco]
                try:
                    preco = float(preco)
                except (TypeError, ValueError):
                    continue
                if isinstance(d, (dt.date, dt.datetime)):
                    out[(d.year, d.month)] = preco
                elif isinstance(d, str) and len(d) >= 7:
                    try:
                        dd = dt.datetime.strptime(d.strip()[:10], "%d/%m/%Y") if "/" in d else dt.datetime.fromisoformat(d.strip()[:10])
                        out[(dd.year, dd.month)] = preco
                    except ValueError:
                        pass
        if len(out) == antes:
            avisos.append(f"ANP {url.rsplit('/', 1)[-1]}: nenhuma linha de gasolina; início da planilha: {amostra}")
    if not out:
        raise ValueError("planilhas da ANP sem gasolina comum")
    _CACHE["gas"] = out
    return out


def litros_mensal():
    sm, gas = sm_mensal(), gasolina_mensal()
    return {k: round(sm[k] / p, 1) for k, p in gas.items() if k in sm and p > 0}


def norm_txt(t):
    import unicodedata
    return unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()


def ipea_metadados():
    if "ipea_meta" not in _CACHE:
        _CACHE["ipea_meta"] = json.loads(baixar("http://www.ipeadata.gov.br/api/odata4/Metadados", timeout=300)).get("value", [])
    return _CACHE["ipea_meta"]


def smn_mensal():
    """Salário mínimo necessário do DIEESE (Ipeadata), em R$ correntes."""
    if "smn" in _CACHE:
        return _CACHE["smn"]
    todas = ipea_metadados()
    meta = [x for x in todas if "necessari" in norm_txt(x.get("SERNOME")) and "salario" in norm_txt(x.get("SERNOME"))
            and "r$" in norm_txt(x.get("UNINOME") or "r$")]
    meta.sort(key=lambda x: ("nominal" not in norm_txt(x.get("SERNOME")), len(x.get("SERNOME") or "")))
    if not meta:
        parecidas = [(x.get("SERCODIGO"), x.get("SERNOME")) for x in todas if "dieese" in norm_txt(x.get("SERCODIGO")) and "salari" in norm_txt(x.get("SERNOME"))][:10]
        raise ValueError(f"série do salário mínimo necessário não encontrada no Ipeadata; séries do DIEESE com 'salário': {parecidas}")
    serie = meta[0]
    vals = json.loads(baixar(f"http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{serie['SERCODIGO']}')")).get("value", [])
    out = {}
    for v in vals:
        try:
            d = dt.date.fromisoformat(str(v["VALDATA"])[:10])
            out[(d.year, d.month)] = float(v["VALVALOR"])
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise ValueError("salário mínimo necessário sem valores")
    avisos_info.append(f"salário mínimo necessário: {serie['SERCODIGO']}: {serie['SERNOME']}")
    _CACHE["smn"] = out
    return out


def smn_ratio():
    """Salário mínimo como % do salário mínimo necessário: média anual e último mês."""
    sm, smn = sm_mensal(), smn_mensal()
    mensal = {k: 100 * sm[k] / v for k, v in smn.items() if k in sm and v > 0}
    return _anual_media(mensal), (mensal[max(mensal)] if mensal else None)


def cesta_mensal():
    """Custo da cesta básica do DIEESE em São Paulo (Ipeadata), em horas de trabalho de quem ganha o mínimo."""
    if "cesta" in _CACHE:
        return _CACHE["cesta"]
    base = "http://www.ipeadata.gov.br/api/odata4"
    todas = ipea_metadados()
    meta = [x for x in todas if "cesta" in norm_txt(x.get("SERNOME")) and "sao paulo" in norm_txt(x.get("SERNOME"))]
    cands = [x for x in meta if norm_txt(x.get("PERNOME") or x.get("SERPERIODICIDADE") or "mensal").startswith("mensal")
             and "r$" in norm_txt(x.get("UNINOME")) and ("gasto" in norm_txt(x.get("SERNOME")) or "custo" in norm_txt(x.get("SERNOME")) or "valor" in norm_txt(x.get("SERNOME")))]
    if not cands:
        cands = [x for x in meta if "r$" in (x.get("UNINOME") or "").lower()]
    if not cands:
        raise ValueError(f"série da cesta não encontrada; candidatas: {[(x.get('SERCODIGO'), x.get('SERNOME'), x.get('UNINOME')) for x in meta][:8]}")
    serie = cands[0]
    status_cesta = f"{serie['SERCODIGO']}: {serie['SERNOME']}"
    vals = json.loads(baixar(f"{base}/ValoresSerie(SERCODIGO='{serie['SERCODIGO']}')")).get("value", [])
    sm = sm_mensal()
    out = {}
    for v in vals:
        try:
            d = dt.date.fromisoformat(str(v["VALDATA"])[:10])
            preco = float(v["VALVALOR"])
        except (KeyError, TypeError, ValueError):
            continue
        k = (d.year, d.month)
        if k in sm and k >= (1994, 7) and sm[k] > 0:
            out[k] = round(preco / (sm[k] / 220), 1)
    if not out:
        raise ValueError("cesta sem valores")
    avisos_info.append(f"cesta básica: {status_cesta}")
    _CACHE["cesta"] = out
    return out


avisos_info = []

MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def mais_recente(inicio_mandato):
    """Dado mais recente possível de cada indicador para o governo atual (mensal ou trimestral, não só o último ano fechado)."""
    a0 = int(inicio_mandato[:4])
    out = {}
    # inflação, comida e tarifas: acumulado dos últimos 12 meses e média anualizada desde a posse
    for iid, cod in (("inflacao", 433), ("inpc", 188)):
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
    try:
        mensal = sorted(serie_bcb(5793, f"01/01/{a0}"))
        a, m, v = mensal[-1]
        out["primario"] = {"rotulo": f"12 meses até {MES[m - 1]}/{a}", "valor": -v, "quando": a + m / 12}
    except Exception as e:  # noqa: BLE001
        avisos.append(f"recente primario: {e}")
    for ind in INDICADORES:
        try:
            if ind["fonte"] == "acess":
                mensal = acessibilidade_mensal(ind["codigo"])
            elif ind["fonte"] == "anp":
                mensal = litros_mensal()
            elif ind["fonte"] == "cesta":
                mensal = cesta_mensal()
            else:
                continue
        except Exception as e:  # noqa: BLE001
            avisos.append(f"recente {ind['id']}: {e}")
            continue
        if mensal:
            a, m = max(mensal)
            out[ind["id"]] = {"rotulo": f"{MES[m - 1]}/{a}", "valor": mensal[(a, m)], "quando": a + m / 12}
    for iid in ("carteira", "renda_trabalho"):
        pts = TRIMESTRAL.get(iid)
        if pts:
            a, q, v = pts[-1]
            out[iid] = {"rotulo": f"{q}º trimestre de {a}", "valor": v, "quando": a + q * 3 / 12}
    return out


def cenarios_projecao(series, recentes, proj):
    """Trajetórias possíveis para o governo atual. Estimativas, nunca resultados."""
    out = []
    anos = list(range(HOJE.year + 1, HOJE.year + 4))
    # 1. Poder de compra: regra do salário mínimo (Lei 14.663/2023, com ganho real limitado entre 0,6% e 2,5% pela Lei 15.077/2024)
    try:
        sm0 = recentes["salario_minimo"]["valor"]
        pib = {}
        try:
            pib.update(serie_wb("NY.GDP.MKTP.KD.ZG")[0])
        except Exception as e:  # noqa: BLE001
            avisos.append(f"PIB para projeção: {e}")
        for f in proj.get("focus", []):
            if f["nome"].startswith("Crescimento"):
                for a, v in f["pontos"]:
                    pib.setdefault(a, v)
        base, pess, otim = [], [], []
        vb = vp = vo = sm0
        for a in anos:
            g = pib.get(a - 2)
            ganho = max(0.6, min(2.5, g)) if g is not None else 0.6
            vb *= 1 + ganho / 100
            vp *= 1.006
            vo *= 1.025
            base.append([a, round(vb)]); pess.append([a, round(vp)]); otim.append([a, round(vo)])
        out.append({"id": "poder_compra", "nome": "Poder de compra do salário mínimo", "unidade": "R$ por mês, em valores de hoje",
                    "atual": round(sm0), "horizonte": f"{anos[0]} a {anos[-1]}",
                    "cenarios": {"base": base, "pessimista": pess, "otimista": otim},
                    "premissas": "Regra de reajuste em vigor: inflação (INPC) mais o crescimento do PIB de dois anos antes, com ganho real entre 0,6% e 2,5% ao ano. Cenário base usa o PIB observado e a expectativa do mercado; pessimista usa o ganho mínimo (0,6%); otimista, o máximo (2,5%).",
                    "riscos": "Mudança na regra pelo Congresso; inflação acima do previsto entre um reajuste e outro.",
                    "incerteza": "média", "fonte": "Leis 14.663/2023 e 15.077/2024, IBGE/Banco Mundial (PIB) e boletim Focus"})
    except Exception as e:  # noqa: BLE001
        avisos.append(f"cenário poder de compra: {e}")
    # 2. Emprego: FMI
    lur = next((f for f in proj.get("fmi", []) if f["id"] == "desemprego"), None)
    if lur:
        lur = lur | {"pontos": [p for p in lur["pontos"] if p[0] >= HOJE.year]}
        out.append({"id": "emprego", "nome": "Desemprego", "unidade": "% da força de trabalho", "horizonte": f"{lur['pontos'][0][0]} a {lur['pontos'][-1][0]}",
                    "cenarios": {"base": lur["pontos"]},
                    "premissas": "Projeção do FMI no World Economic Outlook mais recente.",
                    "riscos": "Juros altos por mais tempo e desaceleração mundial podem elevar o desemprego.",
                    "incerteza": "média", "fonte": "FMI"})
    # 3. Pobreza: tendência recente (estimativa própria, sem projeção oficial)
    pob = series.get("pobreza", ({}, {}))[0]
    if len(pob) >= 3:
        ult = sorted(pob)[-3:]
        a1, v1 = ult[-1], pob[ult[-1]]
        tend = (pob[ult[-1]] - pob[ult[0]]) / (ult[-1] - ult[0])
        anos_p = list(range(a1 + 1, HOJE.year + 3))
        cen = {"base": [], "pessimista": [], "otimista": []}
        for a in anos_p:
            k = a - a1
            cen["otimista"].append([a, round(max(0.0, v1 + tend * k), 1)])
            cen["base"].append([a, round(max(0.0, v1 + tend * k * 0.5), 1)])
            cen["pessimista"].append([a, round(v1, 1)])
        out.append({"id": "pobreza", "nome": "Pobreza", "unidade": "% da população (US$ 6,85 por dia)", "atual": round(v1, 1),
                    "atual_ano": a1, "horizonte": f"{anos_p[0]} a {anos_p[-1]}", "cenarios": cen,
                    "premissas": f"Não existe projeção oficial de pobreza. Estimativa do Radar Político a partir da tendência de {ult[0]} a {ult[-1]} ({tend:+.1f} ponto por ano): otimista mantém a tendência, base mantém metade dela, pessimista supõe estagnação.",
                    "riscos": "Mudanças em programas de transferência de renda, inflação de alimentos e desemprego mudam esse quadro rapidamente.",
                    "incerteza": "alta", "fonte": "Banco Mundial (dados observados) e cálculo do Radar Político"})
    # 4. Inflação: mercado e FMI
    ipca = next((f for f in proj.get("focus", []) if f["nome"].startswith("Inflação")), None)
    imf_inf = next((f for f in proj.get("fmi", []) if f["id"] == "inflacao"), None)
    if ipca or imf_inf:
        cen = {}
        if ipca:
            cen["base"] = ipca["pontos"]
        if imf_inf:
            cen["alternativo (FMI)"] = [p for p in imf_inf["pontos"] if p[0] >= HOJE.year]
        out.append({"id": "inflacao", "nome": "Inflação (IPCA)", "unidade": "% no ano", "horizonte": "próximos 3 anos",
                    "cenarios": cen, "premissas": "Mediana das expectativas do mercado (boletim Focus do Banco Central) e projeção do FMI.",
                    "riscos": "Câmbio, preço de alimentos e de combustíveis e a política fiscal.", "incerteza": "média",
                    "fonte": "Banco Central (Focus) e FMI"})
    # 5. Sustentabilidade fiscal: dívida pelo FMI
    div = next((f for f in proj.get("fmi", []) if f["id"] == "divida"), None)
    if div:
        div = div | {"pontos": [p for p in div["pontos"] if p[0] >= HOJE.year]}
        out.append({"id": "fiscal", "nome": "Dívida pública", "unidade": "% do PIB", "horizonte": f"{div['pontos'][0][0]} a {div['pontos'][-1][0]}",
                    "cenarios": {"base": div["pontos"]},
                    "premissas": "Projeção do FMI, que considera as regras fiscais em vigor e a trajetória de juros.",
                    "riscos": "Juros mais altos e déficits maiores aceleram a alta; superávits a contêm.", "incerteza": "média", "fonte": "FMI"})
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
            elif ind["fonte"] == "acess":
                br, lat = _anual_media(acessibilidade_mensal(ind["codigo"])), {}
            elif ind["fonte"] == "bcb_primario":
                br, lat = {a: -v for a, m, v in serie_bcb(5793, "01/01/2001") if m == 12}, {}
            elif ind["fonte"] == "anp":
                br, lat = _anual_media(litros_mensal()), {}
            elif ind["fonte"] == "cesta":
                br, lat = _anual_media(cesta_mensal()), {}
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

    # nível de vida: situação real ao assumir e ao sair, pela referência de cada indicador
    try:
        smn_anual, smn_ult = smn_ratio()
    except Exception as e:  # noqa: BLE001
        avisos.append(f"salário mínimo necessário: {e}")
        smn_anual, smn_ult = {}, None
    for m in mandatos:
        for ind in INDICADORES:
            r = m["indicadores"].get(ind["id"])
            if not r or ind["id"] not in series or ind["id"] not in REFERENCIAS:
                continue
            serie = series[ind["id"]][0]
            for lado, chave in (("recebeu", "nivel_inicio"), ("entregou", "nivel_fim")):
                x = r.get(lado)
                if not x:
                    continue
                ratio = None
                if ind["id"] == "salario_minimo":
                    ratio = smn_ult if (lado == "entregou" and x.get("rotulo")) else smn_anual.get(x["ano"])
                    if ratio is not None:
                        r["smn_" + lado] = round(ratio, 1)
                r[chave] = nota_nivel(ind, x["valor"], serie, smn_ratio=ratio)
        m["nivel"], m["nivel_inicio"] = {}, {}
        for area in AREAS:
            if area not in RESULTADOS:
                continue
            for chave, destino in (("nivel_fim", m["nivel"]), ("nivel_inicio", m["nivel_inicio"])):
                ns = [m["indicadores"][i["id"]][chave] for i in INDICADORES if i["area"] == area and i["id"] in m["indicadores"]
                      and m["indicadores"][i["id"]].get(chave) is not None]
                destino[area] = round(sum(ns) / len(ns)) if ns else None
        for chave, origem in (("nivel_geral", m["nivel"]), ("nivel_geral_inicio", m["nivel_inicio"])):
            vs = [v for v in origem.values() if v is not None]
            m[chave] = round(sum(vs) / len(vs)) if len(vs) >= 4 else None
            m[chave + "_areas"] = len(vs)
        m["tags"] = tags_do_mandato(m)

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

    proj = projecoes()
    proj["cenarios"] = cenarios_projecao(series, recentes, proj)
    saida = {
        "atualizado": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M"),
        "areas": AREAS,
        "blocos": BLOCOS,
        "projecao": proj,
        "referencias": REFERENCIAS,
        "tags": TAGS,
        "indicadores": [{k: v for k, v in i.items() if k not in ("fonte", "codigo", "fonte_txt")} | {"fonte": i.get("fonte_txt", "")}
                        for i in INDICADORES],
        # gráficos a partir de 1994 (inflação a partir de 1995, para a hiperinflação não achatar o resto da série)
        "series": {k: {"brasil": sorted((a, x) for a, x in v[0].items() if a >= (1995 if k == "inflacao" else 1994)),
                       "regiao": sorted((a, x) for a, x in v[1].items() if a >= (1995 if k == "inflacao" else 1994))}
                   for k, v in series.items()},
        "mandatos": mandatos,
        "avisos": avisos,
        "info": avisos_info,
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    print(f"pronto: {len(series)} de {len(INDICADORES)} indicadores; avisos: {avisos}")


if __name__ == "__main__":
    main()
