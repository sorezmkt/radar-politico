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

## Partidos (`partidos.html`)

Páginas sobre as contas dos **diretórios nacionais** dos partidos:

- **Quanto recebeu** cada partido e quanto disso é dinheiro público (Fundo Partidário e Fundo Eleitoral)
- **Como gastou**, por categoria, mês a mês e por fornecedor, com os repasses a candidatos e a outras direções separados
- **Uso obrigatório do Fundo Partidário** (fundação e participação das mulheres) e **devoluções ao Tesouro**
- **Seis alertas automáticos e auditáveis**: possíveis pagamentos duplicados, valores fora do padrão, concentração de pagamentos, padrões no tempo, inconsistências documentais e situação dos fornecedores na Receita. Cada alerta mostra o que foi encontrado, a regra, os lançamentos (com link para o comprovante no TSE), o que falta verificar e a conclusão atual. Nenhuma IA decide nada.

Como funciona:

- `scripts/build_partidos.py` baixa as prestações de contas anuais do TSE (de 2022 até o ano em curso, que aparece como parcial), o arquivo de comprovantes e o IPCA, e gera `data/partidos/index.json` e `data/partidos/<partido>.json`.
- `.github/workflows/atualizar-partidos.yml` roda todo dia às 07:41 (Brasília). Rodar à mão: **Actions → Atualizar dados dos partidos e publicar → Run workflow**.
- `data/partidos/status.json` mostra o diagnóstico da última execução.

Fontes: [Prestação de contas anual partidária](https://dadosabertos.tse.jus.br/dataset/?q=presta%C3%A7%C3%A3o+de+contas+partid%C3%A1rias) (Portal de Dados Abertos do TSE), [DivulgaSPCA](https://divulgaspca.tse.jus.br/), IPCA (IBGE, via [API do Banco Central](https://dadosabertos.bcb.gov.br/)) e situação de CNPJ via BrasilAPI e Minha Receita. Tudo gratuito, sem chave de API.

## Emendas parlamentares (`emendas.html`)

- **Visão nacional por ano**: valores reservados (empenhados), pagos até agora, ainda não pagos e cancelados, sempre separados; divisão por tipo de emenda, área, estado, cidade e tipo de favorecido; entidades e empresas que mais receberam.
- **Emendas Pix**: situação da prestação de contas de cada plano de ação no Transferegov (relatório final entregue, dentro do prazo, prazo vencido sem relatório, sem plano de trabalho).
- **Ficha de cada deputado** (`emendas-deputado.html?id=`): emendas individuais de 2020 até hoje, ano a ano, destinos, favorecidos, convênios e cinco sinais para verificar (prestação de contas das emendas Pix, repasses a entidades privadas, empresas que receberam direto, dinheiro enviado para fora do estado e valores que não fecham).
- **Busca por cidade**: total destinado à cidade e os deputados que mais mandaram recursos para ela.

Como funciona:

- `scripts/build_emendas.py` baixa o arquivo de emendas do Portal da Transparência e as tabelas das transferências especiais do Transferegov, e gera os arquivos em `data/emendas/`. Só emendas individuais são atribuídas a deputados; bancada, comissão e relator ficam nos totais nacionais.
- `.github/workflows/atualizar-emendas.yml` roda todo dia às 08:23 (Brasília). Se o Transferegov não responder, o robô usa a última cópia guardada em `cache/pix.json.gz` e avisa a data na página.
- `data/emendas/status.json` mostra o diagnóstico da última execução.

Fontes: [Portal da Transparência: emendas parlamentares](https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares) e [API das transferências especiais do Transferegov](https://api.transferegov.gestao.gov.br/transferenciasespeciais/). Tudo gratuito, sem chave de API.
