"""
Testes das regras de alerta com lançamentos de exemplo.
Rodar na raiz do projeto:  python -m unittest discover -s tests
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import build_partidos as bp  # noqa: E402
from comum import pontuar, situacao_cnpj  # noqa: E402

PARTIDO = "11222333000100"
A = {"nf_sq": {}, "nf_chave": {}, "tem_nf": True}


def lanc(sq, valor, data="10/03/2025", forn="Fornecedor Exemplo LTDA", cnpj="44555666000177", doc="123",
         gasto="SERVIÇOS TÉCNICO-PROFISSIONAIS - OUTROS SERVIÇOS TÉCNICOS E PROFISSIONAIS - ORDINÁRIAS", vdoc=None, fonte="Fundo Partidário"):
    return {"SQ_DESPESA": str(sq), "VR_GASTO": f"{valor:.2f}".replace(".", ","), "VR_PAGAMENTO": "0", "VR_DOCUMENTO": f"{(vdoc or valor):.2f}".replace(".", ","),
            "DT_PAGAMENTO": data, "NM_FORNECEDOR": forn, "NR_CPF_CNPJ_FORNECEDOR": cnpj, "NR_DOCUMENTO": doc, "DS_GASTO": gasto,
            "DS_FONTE_DESPESA": fonte, "NR_CNPJ_PRESTADOR_CONTA": PARTIDO, "TP_DESPESA": "G", "DS_TP_DOCUMENTO": "Nota Fiscal"}


class Duplicidade(unittest.TestCase):
    def test_documento_dividido_entre_fontes_nao_e_duplicidade(self):
        G = [lanc(1, 30000, vdoc=50000, fonte="Fundo Partidário"), lanc(2, 20000, vdoc=50000, fonte="Outros Recursos")]
        self.assertEqual(bp.regra_duplicidade(G, A)["status"], "good")

    def test_excedente_de_pagamento_repetido(self):
        G = [lanc(i, 45000, data=f"{10 + i}/03/2025") for i in range(3)]
        a = bp.regra_duplicidade(G, A)
        self.assertEqual(a["valor"], 90000)  # pagos R$ 135 mil para um documento de R$ 45 mil
        self.assertEqual(a["status"], "bad")
        self.assertIn("possível excedente de R$ 90.000,00", a["dados"][0]["grupo"])

    def test_mesmo_valor_mesmo_dia_com_documentos_diferentes_so_fica_listado(self):
        G = [lanc(1, 60000, doc="10"), lanc(2, 60000, doc="11"), lanc(3, 60000, doc="12")]
        a = bp.regra_duplicidade(G, A)
        self.assertEqual(a["status"], "good")
        self.assertTrue(any("conferência" in g["grupo"] for g in a["dados"]))

    def test_despesa_judicial_nao_entra(self):
        G = [lanc(i, 45000, data=f"{10 + i}/03/2025", gasto="DESPESAS JUDICIAIS - ORDINÁRIAS") for i in range(3)]
        self.assertEqual(bp.regra_duplicidade(G, A)["status"], "good")


class Classificacao(unittest.TestCase):
    def test_despesa_judicial_nao_e_compra(self):
        r = lanc(1, 2_000_000, forn="Banco do Brasil", gasto="DESPESAS JUDICIAIS - ORDINÁRIAS")
        self.assertFalse(bp.compra(r["DS_GASTO"], r))

    def test_proprio_partido_e_orgao_publico_nao_sao_compra(self):
        r1 = lanc(1, 1000, cnpj=PARTIDO[:8] + "000255")
        r2 = lanc(2, 1000, forn="TRIBUNAL SUPERIOR ELEITORAL", cnpj="00509018000113")
        self.assertFalse(bp.compra(r1["DS_GASTO"], r1))
        self.assertFalse(bp.compra(r2["DS_GASTO"], r2))

    def test_judiciais_ficam_fora_da_concentracao_e_aparecem_no_texto(self):
        D = [lanc(1, 8_000_000, forn="Banco do Brasil", cnpj="00000000597570", gasto="DESPESAS JUDICIAIS - ORDINÁRIAS"),
             lanc(2, 500_000, forn="Escritório A", cnpj="11111111000111"), lanc(3, 400_000, forn="Agência B", cnpj="22222222000122")]
        rs = bp.resumo_ano("XX", 2025, D, [], A)
        self.assertNotIn("00000000597570", rs["fornecedores_raw"])
        self.assertEqual(rs["gastos"]["judiciais"], 8_000_000)
        self.assertEqual(rs["gastos"]["total"], 8_900_000)  # continua no total de gastos
        a = bp.regra_concentracao(rs["fornecedores_raw"], rs["gastos"]["compras"], [0.2, 0.3], None, rs["gastos"]["judiciais"])
        self.assertIn("despesas judiciais ficaram fora", a["encontrado"])


class Pontuacao(unittest.TestCase):
    def al(self, id_, st, chaves=None):
        return {"id": id_, "titulo": id_, "status": st, "encontrado": "x.", "_chaves": chaves}

    def test_mesmo_fornecedor_conta_uma_vez(self):
        als = [self.al("concentracao", "bad", {"F1": 100}), self.al("fora_padrao", "bad", {"F1": 90}), self.al("cnpj", "warn", {"F1": 50})]
        pts, fat = pontuar(als)
        self.assertEqual(pts, 2)
        self.assertEqual([f["id"] for f in fat], ["concentracao"])
        self.assertEqual(als[1]["relacionado"], "concentracao")
        self.assertNotIn("_chaves", als[0])

    def test_sinais_independentes_somam(self):
        als = [self.al("concentracao", "bad", {"F1": 100}), self.al("fora_padrao", "warn", {"F2": 90}), self.al("documental", "warn")]
        self.assertEqual(pontuar(als)[0], 4)


class Cnpj(unittest.TestCase):
    def test_situacao_na_epoca(self):
        ult = dt.date(2024, 5, 1)
        self.assertEqual(situacao_cnpj({"situacao": "BAIXADA", "data_situacao": "2025-01-10"}, ult)[0], "depois")
        self.assertEqual(situacao_cnpj({"situacao": "BAIXADA", "data_situacao": "2023-01-10"}, ult)[0], "antes")
        self.assertEqual(situacao_cnpj({"situacao": "INAPTA", "data_situacao": ""}, ult)[0], "sem_data")
        self.assertIsNone(situacao_cnpj({"situacao": "ATIVA"}, ult)[0])

    def test_empresa_recem_aberta_sozinha_fica_no_maximo_amarelo(self):
        forn = {"44555666000177": {"doc": "44555666000177", "nome": "Nova LTDA", "valor": 500000, "primeiro": dt.date(2025, 3, 1), "ultimo": dt.date(2025, 6, 1), "cats": __import__("collections").Counter({"Outras despesas": 1})}}
        cache = {"44555666000177": {"situacao": "ATIVA", "abertura": "2025-02-01", "data_situacao": "2025-02-01"}}
        self.assertEqual(bp.regra_cnpj(forn, cache, 2025)["status"], "warn")

    def forn_novo(self, valor, cat="Propaganda e publicidade"):
        from collections import Counter
        return {"44555666000177": {"doc": "44555666000177", "nome": "Nova LTDA", "valor": valor, "primeiro": dt.date(2025, 3, 1),
                                   "ultimo": dt.date(2025, 6, 1), "cats": Counter({cat: valor})}}

    def test_empresa_nova_com_valor_alto_e_outro_sinal_fica_vermelha(self):
        cache = {"44555666000177": {"situacao": "ATIVA", "abertura": "2025-02-01", "cnae": "4781400", "cnae_desc": "Comércio varejista de artigos do vestuário",
                                    "cnaes2": [], "capital": 500000}}
        a = bp.regra_cnpj(self.forn_novo(600000), cache, 2025)
        self.assertEqual(a["status"], "bad")
        self.assertIn("não combina com propaganda", a["dados"][0]["registros"][0]["descricao"])

    def test_capital_social_minusculo_conta_como_sinal(self):
        cache = {"44555666000177": {"situacao": "ATIVA", "abertura": "2025-02-01", "cnae": "7311400", "cnaes2": [], "capital": 1000}}
        self.assertEqual(bp.regra_cnpj(self.forn_novo(600000), cache, 2025)["status"], "bad")

    def test_empresa_nova_compativel_e_com_capital_fica_amarela(self):
        cache = {"44555666000177": {"situacao": "ATIVA", "abertura": "2025-02-01", "cnae": "7311400", "cnaes2": [], "capital": 100000}}
        self.assertEqual(bp.regra_cnpj(self.forn_novo(600000), cache, 2025)["status"], "warn")

    def test_empresa_nova_com_sinal_mas_valor_menor_fica_amarela(self):
        cache = {"44555666000177": {"situacao": "ATIVA", "abertura": "2025-02-01", "cnae": "7311400", "cnaes2": [], "capital": 1000}}
        self.assertEqual(bp.regra_cnpj(self.forn_novo(200000), cache, 2025)["status"], "warn")

    def test_empresa_que_fechou_depois_nao_acende(self):
        forn = {"44555666000177": {"doc": "44555666000177", "nome": "Antiga LTDA", "valor": 500000, "primeiro": dt.date(2022, 3, 1), "ultimo": dt.date(2022, 6, 1)}}
        cache = {"44555666000177": {"situacao": "BAIXADA", "abertura": "2010-01-01", "data_situacao": "2024-08-01"}}
        self.assertEqual(bp.regra_cnpj(forn, cache, 2022)["status"], "good")


class Documental(unittest.TestCase):
    def test_um_lancamento_grande_nao_leva_ao_vermelho_sozinho(self):
        G = [lanc(1, 900_000, doc="SN")] + [lanc(i, 1000, doc=str(i)) for i in range(2, 102)]
        refs = {"sem_numero": [0.0] * 20, "sem_comprovante": [0.0] * 20, "generico": [0.0] * 20, "sem_fornecedor": [0.0] * 20}
        a, _ = bp.regra_documental(G, {"nf_sq": {str(i): "https://x" for i in range(2, 102)}, "nf_chave": {}, "tem_nf": True}, refs)
        self.assertEqual(a["status"], "warn")
        self.assertIn("1 de 101 lançamentos", " ".join(a["dados"][0]["linhas"]))

    def test_falta_de_comprovante_publico_nao_e_prova_de_inexistencia(self):
        a, _ = bp.regra_documental([lanc(1, 5000)], {"nf_sq": {}, "nf_chave": {}, "tem_nf": True}, {})
        self.assertIn("não significa que ele não existe", a["conclusao"])


class Temporal(unittest.TestCase):
    def test_ano_parcial_nao_compara_com_ano_completo(self):
        cats = lambda v: [{"nome": "Propaganda e publicidade", "valor": v, "itens": []}]  # noqa: E731
        hist = {2024: {"gastos": {"categorias": cats(100_000), "mensal_recorrente": [1] * 12}, "parcial": False}}
        rs = {"gastos": {"categorias": cats(5_000_000), "mensal_recorrente": [100_000] * 12}}
        self.assertEqual(bp.regra_temporal(2026, rs, hist, 1, {}, parcial=True)["status"], "good")
        self.assertEqual(bp.regra_temporal(2026, rs, hist, 1, {}, parcial=False)["status"], "warn")

    def test_devolucoes_nao_contam_como_aumento(self):
        hist = {2023: {"gastos": {"categorias": [{"nome": "Devoluções ao Tesouro e multas", "valor": 10_000}], "mensal_recorrente": [1] * 12}, "parcial": False}}
        rs = {"gastos": {"categorias": [{"nome": "Devoluções ao Tesouro e multas", "valor": 4_000_000}], "mensal_recorrente": [100_000] * 12}}
        self.assertEqual(bp.regra_temporal(2025, rs, hist, 1, {})["status"], "good")


if __name__ == "__main__":
    unittest.main()
