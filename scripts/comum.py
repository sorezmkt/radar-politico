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
