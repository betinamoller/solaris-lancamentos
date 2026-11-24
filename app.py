# app.py — esqueleto do SOLARIS: barra lateral (produto, sensibilidade, custos), botão de rodar e 6 telas em abas.
# Cada tela mora em um arquivo próprio (tela_inicio.py, tela_cadastro.py, ...) com a mesma porta de entrada: mostrar(dados, f).
import importlib
import traceback

import streamlit as st

import motor  # toda a lógica: base, Monte Carlo, políticas, métricas, histórico (sem nenhum comando st.)

st.set_page_config(page_title="SOLARIS · Lançamentos", page_icon="☀️", layout="wide")
ss = st.session_state


@st.cache_data(show_spinner="Lendo a base da L'Oréal…")
def carregar(caminho, versao_arquivo):  # versao_arquivo = data de modificação: se a base mudar, lê de novo
    return motor.carregar_base(caminho)


# ---------- Base de dados ----------
if not motor.ARQUIVO_BASE.exists():
    st.title("SOLARIS")
    st.warning(f"Não encontrei a base **{motor.ARQUIVO_BASE.name}** na pasta do projeto ({motor.PASTA}). Envie o arquivo:")
    arq = st.file_uploader("Base da L'Oréal (Triangulo Produtos V2.xlsx)", type=["xlsx"])
    if arq:
        motor.PASTA.mkdir(parents=True, exist_ok=True)
        motor.ARQUIVO_BASE.write_bytes(arq.getvalue())
        st.rerun()
    st.stop()

dados = carregar(str(motor.ARQUIVO_BASE), motor.ARQUIVO_BASE.stat().st_mtime)
ss.setdefault("cadastrados", motor.carregar_cadastrados())
ss.setdefault("resultado", None)
if "_selecionar" in ss:  # outra tela pediu para trocar o produto (ex.: acabou de cadastrar)
    ss["escolha_produto"] = ss.pop("_selecionar")

# ---------- Barra lateral: produto ----------
st.sidebar.header("1 · Produto")
series = dados["series"]
nomes_base = list(series)
nomes_cad = [f"✚ {p['nome']}" for p in ss["cadastrados"]]
opcoes = nomes_base + nomes_cad
if ss.get("escolha_produto") not in opcoes:
    ss["escolha_produto"] = opcoes[0]
escolha = st.sidebar.selectbox("Produto em análise", opcoes, key="escolha_produto",
                               help="Produtos e benchmarks da base da L'Oréal, ou produtos cadastrados (✚) na aba Cadastro.")
if escolha in series:
    s = series[escolha]
    versoes = motor.versoes_validas(s)
    versao = st.sidebar.selectbox("Versão da previsão (mês “hoje”)", versoes, format_func=lambda i: s["versoes"][i],
                                  help="O mês em que a decisão é tomada: usa a previsão e o plano dessa versão e o estoque real "
                                       "do mês anterior. A primeira versão é o momento do lançamento.")
    produto = motor.produto_da_base(s, versao)
else:
    produto = dict(next(p for p in ss["cadastrados"] if f"✚ {p['nome']}" == escolha))
st.sidebar.caption(f"{produto['origem']} · cobertura-alvo {motor.num(produto['cobertura_dias'])} dias · HB "
                   f"{motor.num(produto['hb_dias'])} dias · LT insumo {motor.num(produto['lt_insumo_semanas'])} sem. · "
                   f"lote {motor.num(produto['lote']) if produto['lote'] else 'sem lote'}")

# ---------- Barra lateral: sensibilidade ----------
P = motor.PADRAO
st.sidebar.header("2 · Análises de sensibilidade")
distribuicoes = st.sidebar.multiselect(
    "Distribuição da demanda", motor.DISTRIBUICOES, default=P["distribuicoes"],
    help="Erros reais: a demanda é a previsão × (1 + um erro real dos benchmarks no mesmo horizonte). "
         "Normal e Poisson: variação em torno da previsão, para comparação.")
choques = st.sidebar.multiselect("Choque de fornecimento", motor.CHOQUES, default=P["choques"],
                                 help="Com choque: em cada mês há 10% de chance de começar uma interrupção (e 50% de terminar); "
                                      "durante o choque a produção não chega e fica retida.")
hb_prod = int(round(produto["hb_dias"]))
hbs = st.sidebar.multiselect("HB (dias)", sorted({30, 60, hb_prod}), default=[hb_prod],
                             help="Horizonte congelado. Escolha os dois para ver o efeito de mudar o HB.")
politicas = st.sidebar.multiselect("Políticas", motor.POLITICAS, default=P["politicas"], format_func=lambda p: motor.NOME_POLITICA[p],
                                   help="P2 + lote só roda quando o produto tem lote mínimo.")
protecao = st.sidebar.radio("Fator de segurança (proteção)", list(motor.PROTECAO_Z), horizontal=True,
                            help="Probabilidade de não faltar que a reserva de segurança mira: 95% (z = 1,645), 90% (z = 1,282) "
                                 "ou 85% (z = 1,036). Vale para P3 e P4.")
n_rep = st.sidebar.slider("Número de simulações (futuros por cenário)", 100, 2000, P["n_rep"], 100)

# ---------- Barra lateral: custos (visíveis, com os valores do projeto) ----------
st.sidebar.header("3 · Custos")
c1, c2 = st.sidebar.columns(2)
custo_estoque = c1.number_input("Estoque (% a.a.)", 0.0, 100.0, 100 * P["custo_estoque_aa"], 1.0,
                                help="Custo de manter estoque por ano, em % do preço (R$ PF).") / 100
custo_falta = c2.number_input("Falta (× PF)", 0.0, 10.0, P["custo_falta"], 0.1, help="Por unidade pendente por mês.")
custo_sobra = c1.number_input("Sobra final (× PF)", 0.0, 5.0, P["custo_sobra"], 0.05, help="Por unidade em estoque no fim do horizonte.")
custo_excesso = c2.number_input("Excesso (× PF/mês)", 0.0, 5.0, P["custo_excesso"], 0.01,
                                help="Por unidade acima de 6 meses de previsão, por mês.")

# ---------- Barra lateral: avançado ----------
with st.sidebar.expander("Avançado"):
    regra = st.radio("Regra da janela de reação", ["Assimétrica (validada)", "Simples (experimento anterior)"],
                     help="Assimétrica: aumentar = max(HB, LT insumo) + produção + decisão; reduzir = HB + decisão. "
                          "Simples: max(HB, 1 mês) nos dois sentidos.")
    mes_decisao = st.toggle("Somar 1 mês de decisão", value=P["mes_decisao"])
    lt_prod = st.number_input("LT de produção (meses)", 0, 6, P["lt_producao"])
    mult = st.slider("Multiplicador da incerteza", 0.5, 2.0, P["mult_incerteza"], 0.1,
                     help="1,0 = erro histórico. 1,5 = erros 50% maiores que os históricos.")
    a1, a2 = st.columns(2)
    p_ini = a1.number_input("Choque: início (%)", 0.0, 100.0, 100 * P["choque_inicio"], 1.0) / 100
    p_fim = a2.number_input("Choque: fim (%)", 1.0, 100.0, 100 * P["choque_fim"], 1.0) / 100
    meta_s = a1.number_input("Meta de serviço (%)", 50.0, 100.0, 100 * P["meta_servico"], 0.5) / 100
    meta_g = a2.number_input("Meta garantida P5 (%)", 50.0, 100.0, 100 * P["meta_garantido"], 0.5) / 100
    cob_min = a1.number_input("Cobertura baixa (< dias)", 0, 120, P["cob_min"], 5)
    cob_max = a2.number_input("Excesso (> dias)", 60, 720, P["cob_max"], 10)
    semente = st.number_input("Semente aleatória", 0, 10_000_000, P["semente"], 1,
                              help="Mesma semente = mesmos futuros: os resultados se repetem.")
    usar_spl = st.checkbox("Confirmar no Stockpyl (mais lento)", value=P["stockpyl"],
                           help="Executa as mesmas decisões no simulador Stockpyl e compara estoque e pendência.")
    n_spl = st.slider("Simulações no Stockpyl", 10, 200, P["n_rep_stockpyl"], 10, disabled=not usar_spl)

par = dict(P, n_rep=n_rep, protecao=protecao, politicas=politicas, distribuicoes=distribuicoes, choques=choques, hbs=hbs,
           custo_estoque_aa=custo_estoque, custo_falta=custo_falta, custo_sobra=custo_sobra, custo_excesso=custo_excesso,
           regra_janela=regra, mes_decisao=mes_decisao, lt_producao=lt_prod, mult_incerteza=mult, choque_inicio=p_ini,
           choque_fim=p_fim, meta_servico=meta_s, meta_garantido=meta_g, cob_min=cob_min, cob_max=cob_max, semente=semente,
           stockpyl=usar_spl, n_rep_stockpyl=n_spl)
up, down = motor.janelas(produto, par)
st.sidebar.info(f"Janela de reação: **aumentar** com {up} meses de antecedência · **reduzir** com {down}.")

faltando = [n for n, v in [("distribuição", distribuicoes), ("choque", choques), ("HB", hbs), ("política", politicas)] if not v]
erros = motor.validar_produto(produto)
rodar = st.sidebar.button("▶ Rodar simulação", type="primary", width="stretch", disabled=bool(faltando or erros))
if faltando:
    st.sidebar.error("Escolha pelo menos uma opção de: " + ", ".join(faltando) + ".")
if erros:
    st.sidebar.error(" ".join(erros))

st.title("☀️ SOLARIS · Estoque de lançamentos")

# ---------- Rodar ----------
if rodar:
    barra = st.progress(0.0, text="Simulando…")
    try:
        r = motor.rodar(produto, par, dados, progresso=lambda x, t: barra.progress(min(x, 1.0), text=t))
        if usar_spl:
            try:
                barra.progress(0.0, text="Confirmando no Stockpyl…")
                r["stockpyl"] = motor.confirmar_stockpyl(r, n_spl, progresso=lambda x, t: barra.progress(min(x, 1.0), text=t))
            except ImportError:
                st.warning("O Stockpyl não está instalado (pip install stockpyl). A rodada segue só com o simulador do SOLARIS.")
        ss["resultado"] = r
        barra.progress(1.0, text="Salvando no Histórico…")
        try:
            r["_arquivo_salvo"] = motor.salvar_resultado(r)
            st.success(f"Rodada concluída e salva no Histórico ({motor.PASTA_HIST}). Veja a aba **Recomendação**.")
        except Exception as e:
            st.warning(f"Rodada concluída, mas não consegui salvar no Histórico: {e}")
    except Exception:
        st.error("Erro ao rodar a simulação:")
        st.code(traceback.format_exc())
    finally:
        barra.empty()

# ---------- Cabeçalho ----------
res = ss["resultado"]
if res is not None:
    st.caption(f"Resultado em tela: **{res['produto']['nome']}** · rodado em {res['data']} · {res['parametros']['n_rep']} "
               f"simulações por cenário · proteção {res['parametros']['protecao']}"
               + (" · aberto do histórico" if res.get("_arquivo") else ""))
else:
    st.caption("Escolha o produto e as análises na barra lateral e clique em **Rodar simulação**.")

# ---------- Cenário em tela (vale para Recomendação, Ação e Análise) ----------
cenario = None
if ss["resultado"] is not None:
    cens = list(ss["resultado"]["cenarios"])
    if ss.get("cenario_ativo") not in cens:
        ss["cenario_ativo"] = cens[0]
    if len(cens) > 1:
        cenario = st.selectbox("Cenário em tela", cens, key="cenario_ativo",
                               help="Combinação de distribuição da demanda, choque e HB que as telas de resultado mostram.")
    else:
        cenario = cens[0]

f = {"produto": produto, "par": par, "resultado": ss["resultado"], "janelas": (up, down), "cenario": cenario}

# ---------- As 6 telas ----------
telas = {"🏠 Início": "tela_inicio", "📝 Cadastro": "tela_cadastro", "✅ Recomendação": "tela_recomendacao",
         "📅 Ação S&OE": "tela_acao", "📊 Análise avançada": "tela_analise", "🗂️ Histórico": "tela_historico"}
abas = st.tabs(list(telas))
importlib.invalidate_caches()  # enxerga arquivos de tela gravados depois que o app começou
for aba, modulo in zip(abas, telas.values()):
    with aba:
        try:
            tela = importlib.import_module(modulo)
        except ModuleNotFoundError as erro:
            if erro.name != modulo:
                raise
            st.info(f"🚧 Tela em construção: grave **{modulo}.py** no notebook e recarregue a página (F5).")
            continue
        try:
            tela.mostrar(dados, f)
        except Exception:
            st.error(f"Erro na tela {modulo}:")
            st.code(traceback.format_exc())
