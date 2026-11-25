# SOLARIS · Estoque de lançamentos


[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24517891.svg)](https://doi.org/10.5281/zenodo.24517891)

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/betinamoller/solaris-lancamentos/blob/main/SOLARIS_Streamlit_Colab.ipynb)

O SOLARIS é uma ferramenta de apoio à decisão para planejar a produção e o estoque de **lançamentos de produtos**. Ela foi desenvolvida no Projeto de Graduação em Engenharia de Produção da PUC-Rio, com apoio da L'Oréal Brasil.

Lançamentos não têm histórico de vendas, e a previsão erra muito nos primeiros meses. Produzir de menos gera ruptura na fase mais importante do produto; produzir demais gera excesso e risco de descarte. Para um produto escolhido, o SOLARIS:

1. simula centenas de futuros possíveis para a demanda (Monte Carlo), usando os erros reais de previsão de lançamentos anteriores;
2. aplica em cada futuro as políticas de estoque **P2** (repor o previsto), **P3** (previsto + reserva de segurança) e **P4** (reserva em lotes), respeitando os prazos da operação (horizonte congelado, lead time de insumo e de produção);
3. compara nível de serviço, cobertura e custo e **recomenda uma política**;
4. transforma a recomendação em um **plano mês a mês com prazos de decisão e gatilhos de S&OE**.

> *English summary.* SOLARIS is a decision-support tool for production and inventory planning of new product launches. It runs a Monte Carlo simulation driven by empirical forecast errors of past launches, compares base-stock policies under the real reaction lead times (frozen horizon, raw-material and production lead times), recommends a policy and turns it into a month-by-month S&OE action plan. Built with Python and Streamlit; runs on Google Colab.

---

## Telas

| Tela | Pergunta que responde |
|---|---|
| 🏠 Início | O que é a ferramenta, como usar, quem fez e onde estão os documentos |
| 📝 Cadastro | Quais produtos posso analisar? Como cadastro um produto novo (à mão ou por planilha)? |
| ✅ Recomendação | Qual política usar e por quê? A resposta muda com a sensibilidade? |
| 📅 Ação S&OE | O que fazer em cada mês, até quando decidir e quais meses acendem gatilho? |
| 📊 Análise avançada | Faixa de estoque, risco mês a mês, custo × serviço, backtest com o histórico real |
| 🗂️ Histórico | Rodadas salvas: reabrir, baixar em Excel/JSON e apagar |

Na barra lateral, o usuário escolhe as análises de sensibilidade: distribuição da demanda (erros reais, Normal ou Poisson), choque de fornecimento, HB de 30 ou 60 dias, fator de segurança (95%, 90% ou 85%), número de simulações e custos.

## Como rodar

### No Google Colab (sem instalar nada)

1. Clique no selo **Abrir no Colab** acima.
2. Rode as células na ordem. O passo 1 conecta o Google Drive e cria a pasta `MyDrive/SOLARIS`, onde ficam a base, o histórico de rodadas e os produtos cadastrados.
3. O passo 13 liga o Streamlit e abre um túnel temporário do `cloudflared`. O link público (`https://….trycloudflare.com`) aparece na tela.
4. Ao terminar, rode `parar_tudo()` para desligar o túnel.

> O túnel rápido do Cloudflare não tem senha: qualquer pessoa com o link acessa o app enquanto ele estiver ligado. Compartilhe só com quem precisa e desligue ao terminar.

### No computador

```bash
pip install -r requirements.txt
streamlit run app.py
```

Coloque a base de dados na mesma pasta do código, ou indique outra pasta pela variável de ambiente `SOLARIS_PASTA`.

## Dados

**Os dados da L'Oréal Brasil são confidenciais e não fazem parte deste repositório.** Para usar a ferramenta com outros dados, há dois caminhos:

- **Cadastrar produtos na própria ferramenta** (aba Cadastro), à mão ou pela planilha modelo, que a ferramenta gera para download. Ela tem uma aba `Atributos` (origem, cobertura-alvo, HB, maior LT de insumo, preço, lote e estoque atual) e uma aba `Previsoes` (previsão de vendas e produção programada por mês).
- **Fornecer uma base no mesmo formato da base original** (`Triangulo Produtos V2.xlsx`):
  - aba `Base`: atributos de cada produto;
  - aba `BOM`: insumos e lead times;
  - uma aba por série (`PRODUTO n` ou `BENCH X_n`), cada uma com três triângulos (previsão de vendas, plano de produção e estoque), em que a linha é a versão do plano e a coluna é o mês-alvo.

A incerteza da previsão é calibrada com os erros dos benchmarks (lançamentos anteriores com venda realizada). Sem uma base com benchmarks, a ferramenta não tem como estimar a curva de erro.

## Estrutura do repositório

| Arquivo | O que faz |
|---|---|
| `SOLARIS_Streamlit_Colab.ipynb` | Notebook que grava os arquivos do app, testa o motor e publica a ferramenta pelo túnel do `cloudflared` |
| `motor.py` | Toda a lógica, sem nenhum comando de tela: leitura da base, curva de incerteza, geração dos futuros, simulador das políticas, métricas, regra de escolha, plano e gatilhos de S&OE, confirmação no Stockpyl e histórico |
| `app.py` | Barra lateral, botão de rodar e as seis telas em abas |
| `conteudo.py` | Textos da tela de Início (fácil de editar) |
| `tela_*.py` | Uma tela por arquivo, todas com a entrada `mostrar(dados, f)` |
| `requirements.txt` | Bibliotecas necessárias |

## O modelo em resumo

- **Janela de reação assimétrica:**
  - aumentar exige decidir com antecedência de max(HB, LT do insumo) + 1 mês de produção + 1 mês de decisão;
  - reduzir exige HB + 1 mês de decisão;
  - HB e LT são convertidos em meses arredondando para cima.
- **Demanda:** previsão × (1 + erro relativo real), com o erro sorteado das trajetórias de erro dos benchmarks no mesmo horizonte. Normal e Poisson estão disponíveis para comparação. A previsão é revisada mês a mês dentro de cada futuro.
- **Choque de fornecimento:** cadeia de Markov (10% de chance de começar e 50% de terminar a cada mês); durante o choque, a produção fica retida.
- **Políticas:** estoque-alvo = previsão até a produção chegar + cobertura-alvo + z × σ (só em P3 e P4). P4 e P2 + lote trabalham em múltiplos do lote mínimo.
- **Métricas:**
  - nível de serviço;
  - nível garantido (percentil 5);
  - % de meses com falta, com cobertura abaixo de 30 dias e acima de 180 dias;
  - estoque médio e custo total (manter estoque, falta, sobra final e excesso).

  Meses sem previsão de venda ficam fora das métricas de avaliação.
- **Regra de escolha:** entre as políticas com nível de serviço ≥ 95% e nível garantido ≥ 90%, a de menor custo. Se nenhuma cumpre, a de maior nível garantido.
- **Verificação:** as decisões do simulador do SOLARIS podem ser reexecutadas no [Stockpyl](https://github.com/LarrySnyder/stockpyl). Nos testes, as trajetórias de estoque foram idênticas.

Todos os parâmetros-padrão ficam no início do `motor.py` (`PADRAO` e `GATILHO`) e a maioria pode ser alterada na barra lateral.

## Como citar

Se usar este código, cite a versão arquivada no Zenodo (veja também o arquivo `CITATION.cff`):

> MOLLER, B.; JALLAD, J. **SOLARIS: ferramenta de apoio à decisão de estoque para lançamentos de produtos**. Versão 1.0.0. [S. l.]: Zenodo, 2026. Software. DOI: 10.5281/zenodo.24517891.

## Autoria

- **Autoras:** Betina Moller e Julia Jallad
- **Orientador:** Prof. Rodrigo Caiado
- **Apoio:** L'Oréal Brasil e PUC-Rio (Departamento de Engenharia Industrial)

Projeto de Graduação em Engenharia de Produção, PUC-Rio, 2026.

## Licença

Distribuído sob a licença MIT. Veja o arquivo [`LICENSE`](LICENSE).
