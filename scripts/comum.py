"""
Regras compartilhadas pelos robôs dos deputados e dos partidos.

- situacao_cnpj: lê a situação cadastral da Receita levando em conta QUANDO ela mudou, para não aplicar
  a situação de hoje a pagamentos antigos.
- pontuar: soma os pontos dos alertas sem contar duas vezes o mesmo fornecedor.
"""
import datetime as dt

ATIVA = ("ATIVA", "ATIVO", "NAO ENCONTRADO", "")


def data_receita(s):
    """Datas da BrasilAPI (AAAA-MM-DD) e da Minha Receita (AAAA-MM-DD ou AAAA/MM/DD)."""
    s = (s or "")[:10].replace("/", "-")
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def precisa_reconsultar(info):
    """Entradas antigas do cache não guardavam a data da situação; só faz falta quando o CNPJ não está ativo."""
    return info.get("situacao", "") not in ATIVA and "data_situacao" not in info


def situacao_cnpj(info, ultimo_pagamento):
    """
    Devolve (tipo, texto):
      "antes"       CNPJ já estava baixado/inapto/suspenso quando o fornecedor ainda recebia
      "depois"      a situação mudou depois do último pagamento (informativo, não é sinal)
      "sem_data"    não está ativo hoje e a Receita não informou desde quando
      None          ativo ou sem informação
    """
    sit = (info or {}).get("situacao", "")
    if sit in ATIVA:
        return None, ""
    quando = data_receita(info.get("data_situacao"))
    nome = sit.lower()
    if quando is None:
        return "sem_data", f"CNPJ {nome} na Receita hoje (a Receita não informa desde quando)"
    if ultimo_pagamento and quando <= ultimo_pagamento:
        return "antes", f"CNPJ {nome} desde {quando:%d/%m/%Y}, antes do último pagamento ({ultimo_pagamento:%d/%m/%Y})"
    return "depois", f"CNPJ {nome} desde {quando:%d/%m/%Y}, depois do último pagamento"


PESO = {"bad": 2, "warn": 1}


def pontuar(alertas, chave_txt="encontrado"):
    """
    Soma 2 pontos por alerta vermelho e 1 por amarelo, do mais grave para o menos grave.
    Um alerta que aponta para os mesmos fornecedores de um alerta já contado (metade ou mais do valor dele)
    não soma de novo: ele continua visível, mas fica marcado como relacionado.
    Alertas sem fornecedor definido (padrões do ano, documentação em geral) são sinais independentes e sempre contam.
    Cada alerta pode trazer "_chaves": {fornecedor: valor}; o campo é retirado antes de salvar.
    Devolve (pontos, fatores), em que fatores lista o que gerou cada ponto.
    """
    contados, cobertos, total = [], set(), 0
    ordem = sorted(range(len(alertas)), key=lambda i: -PESO.get(alertas[i]["status"], 0))
    for i in ordem:
        a = alertas[i]
        ch = a.pop("_chaves", None) or {}
        p = PESO.get(a["status"], 0)
        if not p:
            continue
        if ch:
            tot = sum(ch.values()) or 1
            novo = sum(v for k, v in ch.items() if k not in cobertos)
            if novo / tot < 0.5:
                rel = next((c["titulo"] for c in contados if c["_k"] & set(ch)), contados[0]["titulo"] if contados else "")
                a["relacionado"] = rel
                a[chave_txt] = a[chave_txt].rstrip() + f" Os mesmos fornecedores já aparecem em \"{rel}\", então este alerta não soma pontos de novo."
                continue
            cobertos |= set(ch)
        total += p
        contados.append({"id": a["id"], "titulo": a["titulo"], "pontos": p, "_k": set(ch)})
    for c in contados:
        c.pop("_k")
    return total, contados


# ---------------------------------------------------------------- empresa recém-aberta

# divisões da CNAE (2 primeiros dígitos) que combinam com cada tipo de gasto; tipos amplos demais ficam de fora
CNAE_COMPATIVEL = {
    "Advocacia e consultoria jurídica": {"69"},
    "Contabilidade": {"69"},
    "Informática": {"62", "63", "95"},
    "Propaganda e publicidade": {"18", "58", "59", "60", "63", "73", "74", "82", "90"},
    "Divulgação do mandato": {"18", "58", "59", "60", "63", "73", "74", "82", "90"},
    "Pesquisas de opinião": {"70", "72", "73", "74", "82"},
    "Consultorias e pesquisas": {"62", "63", "69", "70", "72", "73", "74", "82", "85", "94"},
    "Viagens e transporte": {"47", "49", "50", "51", "52", "55", "77", "79"},
    "Eventos, congressos e seminários": {"55", "56", "73", "77", "79", "82", "90", "93"},
    "Combustíveis": {"46", "47"},
    "Locação de veículos": {"49", "77"},
    "Segurança": {"80"},
    "Hospedagem": {"55"},
    "Alimentação": {"10", "47", "56"},
    "Aluguéis e condomínios": {"68", "77"},
}


def campos_receita(j):
    """Campos da BrasilAPI / Minha Receita guardados no cache de CNPJ."""
    def cod(x):
        return str(x.get("codigo") if isinstance(x, dict) else x or "").zfill(7)
    try:
        capital = float(j.get("capital_social") or 0)
    except (TypeError, ValueError):
        capital = 0.0
    return {
        "data_situacao": j.get("data_situacao_cadastral") or "",
        "cnae": str(j.get("cnae_fiscal") or "").zfill(7) if j.get("cnae_fiscal") else "",
        "cnae_desc": j.get("cnae_fiscal_descricao") or "",
        "cnaes2": [cod(x) for x in (j.get("cnaes_secundarios") or []) if cod(x).strip("0")],
        "capital": capital,
    }


def precisa_detalhe(info):
    """Entradas antigas do cache não têm atividade nem capital social; só fazem falta para empresas recém-abertas."""
    return "capital" not in info


def dias_desde_abertura(info, primeiro_pagamento):
    ab = data_receita((info or {}).get("abertura"))
    if ab is None or primeiro_pagamento is None:
        return None
    return (primeiro_pagamento - ab).days


def sinais_empresa_nova(info, valor, ultimo_pagamento, categoria):
    """
    Sinais independentes que tornam uma empresa recém-aberta mais relevante:
      - nenhuma atividade registrada na Receita (principal ou secundária) combina com o tipo de gasto;
      - capital social menor que 2% do que a empresa recebeu (recebeu mais de 50 vezes o próprio capital);
      - a empresa foi baixada, ficou inapta ou suspensa até 1 ano depois do último pagamento.
    Devolve a lista de textos explicando cada sinal encontrado.
    """
    info = info or {}
    sinais = []
    esperadas = CNAE_COMPATIVEL.get(categoria)
    cnaes = [c for c in [info.get("cnae", "")] + list(info.get("cnaes2", [])) if c]
    if esperadas and cnaes and not any(c[:2] in esperadas for c in cnaes):
        desc = info.get("cnae_desc") or info.get("cnae", "")
        sinais.append(f"atividade registrada na Receita ({desc.lower()}) não combina com {categoria.lower()}")
    cap = info.get("capital")
    if isinstance(cap, (int, float)) and cap > 0 and valor > 50 * cap:
        sinais.append(f"capital social de R$ {cap:,.0f}".replace(",", ".") + f", {valor / cap:.0f} vezes menor que o valor recebido")
    if info.get("situacao", "") not in ATIVA:
        quando = data_receita(info.get("data_situacao"))
        if quando and ultimo_pagamento and 0 <= (quando - ultimo_pagamento).days <= 365:
            sinais.append(f"empresa {info['situacao'].lower()} em {quando:%d/%m/%Y}, menos de 1 ano depois do último pagamento")
    return sinais


def aberta_ha_pouco(info, primeiro_pagamento, dias=180):
    d = dias_desde_abertura(info, primeiro_pagamento)
    return d is not None and d < dias
