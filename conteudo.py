# conteudo.py — textos da tela de Início. Edite à vontade: o app lê tudo daqui.
# Dica: texto entre ** fica em negrito; cada item de lista é uma string.

TITULO = "SOLARIS · Estoque de lançamentos"
SUBTITULO = "Ferramenta de apoio à decisão de produção e estoque para lançamentos de produtos · L'Oréal Brasil"

O_QUE_E = (
    "O SOLARIS recomenda **qual política de estoque usar** em um lançamento e **o que fazer mês a mês** no S&OE. "
    "Para isso, ele simula centenas de futuros possíveis (Monte Carlo) para a demanda do produto, aplica as políticas "
    "P2, P3 e P4 em cada futuro, com as mesmas regras de prazo da operação (horizonte congelado, lead time de insumo e de "
    "produção), e compara nível de serviço, cobertura e custo."
)

PROBLEMA = (
    "Lançamentos não têm histórico de vendas, e a previsão erra muito nos primeiros meses. Produzir de menos gera ruptura "
    "na fase mais importante do produto; produzir demais gera excesso e risco de descarte. A ferramenta mostra esse "
    "equilíbrio com números e transforma a recomendação em ações com prazo."
)

COMO_USAR = [
    "**Escolha o produto** na barra lateral: um produto da base da L'Oréal (e a versão da previsão) ou um produto cadastrado.",
    "**Cadastre produtos novos** na aba Cadastro: preencha à mão ou suba a planilha modelo.",
    "**Escolha as análises de sensibilidade**: distribuição da demanda, com ou sem choque de fornecimento, HB, fator de "
    "segurança e número de simulações. Os custos ficam visíveis e já vêm com os valores usados no projeto.",
    "**Clique em Rodar simulação.** A rodada é salva automaticamente no Histórico (Google Drive).",
    "**Leia a Recomendação**, depois a **Ação S&OE** (o que fazer em cada mês e até quando decidir) e, se quiser, a "
    "**Análise avançada** com os gráficos.",
]

POLITICAS = {
    "P2 · Repor o previsto": "Todo mês produz o previsto até a produção chegar mais a cobertura-alvo, descontando o estoque e "
                             "o que já está a caminho. Não tem reserva para o erro da previsão.",
    "P3 · Previsto + reserva": "Igual ao P2, com uma reserva de segurança (z × σ) dimensionada pelo erro histórico da previsão "
                               "em cada horizonte.",
    "P4 · Reserva em lotes": "Igual ao P3, com a produção arredondada para múltiplos do lote mínimo do produto.",
    "Plano programado": "O plano de produção que já está no sistema. Entra como referência para comparar e para calcular "
                        "os riscos da Ação S&OE.",
}

JANELA = (
    "**Janela de reação.** Para **aumentar** a produção de um mês, a decisão precisa ser tomada com "
    "max(HB, LT do insumo) + 1 mês de produção + 1 mês de decisão de antecedência. Para **reduzir**, basta "
    "HB + 1 mês de decisão (não depende do insumo nem da produção). Dentro do HB o plano está congelado."
)

METRICAS = {
    "Nível de serviço": "Parte da demanda atendida no próprio mês (a falta vira pendência).",
    "Nível garantido": "Nível de serviço em 95% dos futuros simulados (percentil 5). Mede o pior caso razoável.",
    "% meses com falta": "Meses em que faltou produto em relação aos meses com previsão de venda.",
    "Cobertura": "Dias que o estoque dura consumindo a previsão dos meses seguintes. Abaixo de 30 dias = cobertura baixa; "
                 "acima de 180 dias = excesso.",
    "Custo total": "Valores-padrão, editáveis na barra lateral: custo de manter estoque (25% a.a. sobre o preço) + falta (1 × preço por unidade pendente por mês) + sobra "
                   "no fim (0,3 × preço) + excesso acima de 6 meses de previsão (0,05 × preço por mês).",
    "Meses sem previsão": "Meses com previsão de venda igual a zero (pré-lançamento) ficam fora das métricas de avaliação e "
                          "não acionam gatilho.",
}

EQUIPE = {
    "Autoras": ["Betina Moller", "Julia Jallad"],
    "Orientador": ["Prof. Rodrigo Caiado"],
    "Apoio": ["L'Oréal Brasil", "PUC-Rio · Departamento de Engenharia Industrial"],
}

PROJETO = "Projeto de graduação (TCC) · Engenharia de Produção · PUC-Rio · 2026"

AGRADECIMENTOS = (
    "Agradecemos à equipe de Supply Chain da L'Oréal Brasil pelos dados e pelas discussões sobre o processo de S&OE, "
    "e ao Prof. Rodrigo Caiado pela orientação."
)

# Documentos para download na tela de Início: coloque os arquivos na pasta docs/ dentro da pasta do projeto.
# Chave = nome do arquivo; valor = descrição mostrada na tela. Arquivos da pasta que não estiverem aqui aparecem com o próprio nome.
DOCUMENTOS = {
    "SOLARIS_Manual_do_usuario.pdf": "Manual do usuário da ferramenta",
    "SOLARIS_Documentacao_Codigo_e_Resultados.pdf": "Documentação do código e dos resultados do experimento",
    "SOLARIS_Metodologia.docx": "Metodologia detalhada",
    "SOLARIS_Relatorio_Metodologia_Resultados.docx": "Capítulos de metodologia e resultados do relatório",
}

AVISO_DADOS = (
    "Os dados da base são da L'Oréal Brasil e foram cedidos para o projeto. Não compartilhe o link público do túnel fora da equipe."
)
