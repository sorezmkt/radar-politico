"""
Testes das regras das emendas parlamentares com dados de exemplo.
Rodar na raiz do projeto:  python -m unittest discover -s tests
"""
import datetime as dt
import io
import os
import sys
import unittest
import zipfile
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import build_emendas as be  # noqa: E402

CAB = ("Código da Emenda;Ano da Emenda;Tipo de Emenda;Código do Autor da Emenda;Nome do Autor da Emenda;Número da emenda;"
       "Localidade de aplicação do recurso;Código Município IBGE;Município;Código UF IBGE;UF;Região;Código Função;Nome Função;"
       "Código Subfunção;Nome Subfunção;Código Programa;Nome Programa;Código Ação;Nome Ação;Código Plano Orçamentário;"
       "Nome Plano Orçamentário;Valor Empenhado;Valor Liquidado;Valor Pago;Valor Restos A Pagar Inscritos;"
       "Valor Restos A Pagar Cancelados;Valor Restos A Pagar Pagos")


def linha(cod, ano, tipo, autor, emp, pago, rp_pago="0,00", rp_canc="0,00", uf="BAHIA", ibge="2927408", mun="SALVADOR"):
    return ";".join([cod, str(ano), tipo, "1234", autor, "0001", f"{mun} - BA", ibge, mun, "2900000", uf, "Nordeste", "10", "Saúde",
                     "302", "Assistência", "5018", "SUS", "2E90", "CUSTEIO", "EIND", "EMENDA INDIVIDUAL", emp, "0,00", pago, "0,00", rp_canc, rp_pago])


def zip_emendas(linhas):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("EmendasParlamentares.csv", (CAB + "\n" + "\n".join(linhas)).encode("latin-1"))
    return zipfile.ZipFile(io.BytesIO(buf.getvalue()))


IND = "Emenda Individual - Transferências com Finalidade Definida"
PIX = "Emenda Individual - Transferências Especiais"


class Valores(unittest.TestCase):
    def test_etapas_nao_sao_somadas_como_parcelas(self):
        z = zip_emendas([linha("202412340001", 2024, IND, "FULANO", "1000000,00", "300000,00", rp_pago="200000,00", rp_canc="100000,00")])
        e = be.carregar_emendas(z)["202412340001"]
        self.assertEqual(be.pago_total(e), 500_000)        # pago no ano + restos a pagar pagos
        self.assertEqual(be.pendente(e), 400_000)          # empenhado - pago - cancelado
        t = be.soma([e])
        self.assertEqual((t["emp"], t["pago"], t["n"]), (1_000_000, 500_000, 1))

    def test_linhas_do_mesmo_codigo_viram_uma_emenda(self):
        z = zip_emendas([linha("202412340001", 2024, IND, "FULANO", "600000,00", "0,00"),
                         linha("202412340001", 2024, IND, "FULANO", "400000,00", "100000,00", ibge="2910800", mun="FEIRA DE SANTANA")])
        ems = be.carregar_emendas(z)
        self.assertEqual(len(ems), 1)
        self.assertEqual(be.soma(ems.values())["emp"], 1_000_000)
        self.assertEqual(len(ems["202412340001"]["munis"]), 2)

    def test_pendente_nunca_negativo(self):
        self.assertEqual(be.pendente({"emp": 100, "pago": 150, "rp_pago": 0, "rp_canc": 0}), 0)

    def test_anos_antigos_e_sem_codigo_ficam_fora(self):
        z = zip_emendas([linha("Sem informação", 2024, IND, "FULANO", "1,00", "0,00"), linha("201912340001", 2019, IND, "FULANO", "1,00", "0,00")])
        self.assertEqual(be.carregar_emendas(z), {})


class Autoria(unittest.TestCase):
    def test_so_individuais_e_nome_unico(self):
        ems = {"1": {"cod": "1", "tipo": "individual", "autor": "JOSÉ DA SILVA"}, "2": {"cod": "2", "tipo": "bancada", "autor": "JOSÉ DA SILVA"},
               "3": {"cod": "3", "tipo": "pix", "autor": "MARIA"}}
        por_nome = {"JOSE DA SILVA": [{"id": 10}], "MARIA": [{"id": 11}, {"id": 12}]}
        self.assertEqual(be.autor_do_deputado(ems, por_nome), {"1": 10})


class Favorecidos(unittest.TestCase):
    def test_grupos(self):
        self.assertEqual(be.grupo_favorecido("00360305000104", "Sociedade Anônima Fechada", "Pessoa Jurídica"), "banco")
        self.assertEqual(be.grupo_favorecido("1", "Associação Privada", "Pessoa Jurídica"), "entidade")
        self.assertEqual(be.grupo_favorecido("1", "Sociedade Empresária Limitada", "Pessoa Jurídica"), "empresa")
        self.assertEqual(be.grupo_favorecido("1", "Fundo Público da Administração Direta Municipal", "Pessoa Jurídica"), "publico")
        self.assertEqual(be.grupo_favorecido("1", "Sem informação", "Pessoa Fisica"), "pf")

    def test_entidades_acima_do_limite_ficam_amarelas(self):
        favs = {"a": {"doc": "a", "nome": "Prefeitura", "natureza": "Município", "grupo": "publico", "municipio": "", "uf": "", "valor": 3_000_000},
                "b": {"doc": "b", "nome": "Instituto X", "natureza": "Associação Privada", "grupo": "entidade", "municipio": "", "uf": "", "valor": 10_500_000}}
        self.assertEqual(be.regra_entidades(favs)["status"], "warn")
        favs["b"]["valor"] = 100_000
        self.assertEqual(be.regra_entidades(favs)["status"], "good")


class Pix(unittest.TestCase):
    HOJE = dt.date(2026, 10, 14)

    def plano(self, fim=None, rel=None, ano=2024, trabalho=True):
        return {"ano_plano_acao": ano, "trabalho": [{"data_fim_execucao_plano_trabalho": fim}] if trabalho else [], "relatorios": rel or []}

    def test_relatorio_final_entregue(self):
        p = self.plano("2025-01-01", [{"tipo": "Final", "situacao": "DISPONIBILIZADO"}])
        self.assertEqual(be.situacao_plano_pix(p, self.HOJE)[0], "ok")

    def test_prazo_vencido_sem_relatorio(self):
        p = self.plano("2025-01-01", [{"tipo": "Parcial", "situacao": "DISPONIBILIZADO"}, {"tipo": "Final", "situacao": "EM_ELABORACAO"}])
        self.assertEqual(be.situacao_plano_pix(p, self.HOJE)[0], "atrasado")

    def test_dentro_da_margem_nao_e_atraso(self):
        self.assertEqual(be.situacao_plano_pix(self.plano("2026-06-01"), self.HOJE)[0], "andamento")

    def test_plano_recente_sem_plano_de_trabalho(self):
        self.assertEqual(be.situacao_plano_pix(self.plano(trabalho=False), self.HOJE)[0], "sem_plano")
        self.assertEqual(be.situacao_plano_pix(self.plano(trabalho=False, ano=2021), self.HOJE)[0], "andamento")

    def test_regra_pix(self):
        e = {"cod": "202412340001", "ano": 2024, "tipo": "pix", "emp": 1_000_000, "pago": 1_000_000, "rp_pago": 0}
        e = {**e, "emp": 10_000_000, "pago": 10_000_000}
        plano = {**self.plano("2024-06-01"), "valor_custeio_plano_acao": 0, "valor_investimento_plano_acao": 5_200_000,
                 "nome_beneficiario_plano_acao": "MUNICIPIO X", "codigo_plano_acao": "0903-1"}
        a = be.regra_pix([e], {"202412340001": [plano]})
        self.assertEqual(a["status"], "bad")
        self.assertEqual(a["registros"][0]["valor"], 5_200_000)
        plano["valor_investimento_plano_acao"] = 3_000_000
        self.assertEqual(be.regra_pix([e], {"202412340001": [plano]})["status"], "warn")  # 30% e R$ 3 milhões
        plano["valor_investimento_plano_acao"] = 1_900_000
        self.assertEqual(be.regra_pix([e], {"202412340001": [plano]})["status"], "good")  # 19%: perto da média nacional
        self.assertEqual(be.regra_pix([e], None)["status"], "nd")
        self.assertEqual(be.regra_pix([{**e, "tipo": "individual"}], {})["status"], "nd")


class ForaDoEstado(unittest.TestCase):
    def test_fora_do_estado(self):
        ems = [{"cod": "1", "ano": 2024, "emp": 3_000_000, "ufs": Counter({"BA": 1}), "local": "SALVADOR - BA"},
               {"cod": "2", "ano": 2024, "emp": 2_000_000, "ufs": Counter({"SP": 1}), "local": "SÃO PAULO - SP"}]
        a = be.regra_fora_estado(ems, "BA")
        self.assertEqual(a["status"], "warn")
        self.assertIn("40%", a["texto"])
        self.assertEqual(be.regra_fora_estado(ems[:1], "BA")["status"], "good")


if __name__ == "__main__":
    unittest.main()
