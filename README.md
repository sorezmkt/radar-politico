# Radar Político

Site independente de transparência sobre os deputados federais. Para cada deputado em exercício mostra:

- **Índice de eficiência** (0 a 100): presença, uso da cota parlamentar, produção legislativa e efetividade
- **Gastos da cota** mês a mês, por categoria e por fornecedor, comparados à média da Câmara e ao teto do estado
- **Sinais de risco de irregularidade**: concentração em um fornecedor, empresa recém-aberta, CNPJ inativo e notas de valor redondo repetido
- **Presença** e **proposições** de autoria

Os sinais de risco são cruzamentos automáticos de dados públicos. Não são prova nem acusação de crime.

## Como funciona

- `scripts/build_data.py` baixa os dados abertos oficiais da Câmara e a situação dos CNPJs na Receita e gera `data/index.json` e `data/dep/<id>.json`.
- `.github/workflows/atualizar-dados.yml` roda o robô todo dia às 06:17 (Brasília) e publica o site no GitHub Pages.
- `index.html` + `assets/` é o site estático que lê esses arquivos.
- `data/status.json` mostra o diagnóstico da última execução (avisos, colunas lidas, contagens).

Para rodar à mão: aba **Actions → Atualizar dados e publicar → Run workflow**.

## Fontes

- [Dados Abertos da Câmara dos Deputados](https://dadosabertos.camara.leg.br/)
- [Cota parlamentar (CEAP)](https://www.camara.leg.br/transparencia/gastos-parlamentares)
- Situação cadastral de CNPJ: [BrasilAPI](https://brasilapi.com.br/) e [Minha Receita](https://minhareceita.org/)
