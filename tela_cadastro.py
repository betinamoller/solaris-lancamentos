# tela_cadastro.py — Tela 2: ver os produtos da base, criar/editar produto novo (à mão) e subir planilha.
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import motor

ss = st.session_state


def _gravar(produtos):
    """Inclui ou atualiza (mesmo nome) produtos na lista de cadastrados e salva no Drive."""
    lista = [p for p in ss["cadastrados"] if p["nome"] not in {q["nome"] for q in produtos}]
    for q in produtos:
        q = dict(q, id=f"novo::{q['nome']}", fonte="novo")
        q.pop("sku_base", None), q.pop("versao", None)
        lista.append(q)
    ss["cadastrados"] = lista
    try:
        motor.salvar_cadastrados(lista)
        return True
    except Exception as e:
        st.warning(f"Produto guardado nesta sessão, mas não consegui salvar no Drive: {e}")
        return False


def _tabela_mensal(p):
    return pd.DataFrame({"Mês": p["meses"], "Previsão de vendas (un.)": p["previsao"],
                         "Produção programada (un.)": p["programada"]})


def ver_base(dados, f):
    series = dados["series"]
    padrao = f["produto"].get("sku_base") or list(series)[0]
    sku = st.selectbox("Série da base", list(series), index=list(series).index(padrao), key="cad_ver_sku")
    s = series[sku]
    c = st.columns(3) + st.columns(3)
    c[0].metric("Tipo", "Produto" if s["tipo"] == "produto" else "Benchmark", border=True)
    c[1].metric("Origem", s["origem"], border=True)
    c[2].metric("Cobertura-alvo", f"{motor.num(s['cobertura_dias'])} dias", border=True)
    c[3].metric("HB", f"{motor.num(s['hb_dias'])} dias", border=True)
    c[4].metric("Maior LT de insumo", f"{motor.num(s['lt_insumo_semanas'])} sem.", border=True)
    c[5].metric("Lote (inferido)", motor.num(s["lote"]) if s["lote"] else "sem lote", border=True,
                help="Maior quantidade q tal que ≥ 80% das produções planejadas são múltiplos de q (tolerância 2%).")
    st.caption(f"Preço (R$ PF): {motor.num(s['preco'], 2)} · {len(s['versoes'])} versões da previsão "
               f"({s['versoes'][0]} a {s['versoes'][-1]}) · {s['T_real']} meses com realizado.")

    # previsão da primeira versão × realizado
    fig = go.Figure()
    fig.add_bar(x=s["meses"][:s["T_real"]], y=s["realizado"], name="Realizado (sell-in)", marker_color="#8a8f98")
    for r, nome, cor in [(0, "1ª versão da previsão", "#2a78d6"), (min(3, len(s["versoes"]) - 1), "4ª versão", "#eb6834")]:
        fig.add_scatter(x=s["meses"][r:], y=np.nan_to_num(s["V"][r, r:]), name=f"{nome} ({s['versoes'][r]})", mode="lines+markers",
                        line=dict(color=cor))
    fig.update_layout(title=f"{sku}: previsão × realizado", height=340, separators=",.",
                      margin=dict(t=50, b=10, l=10, r=10), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")

    with st.expander("Triângulos da base (linha = versão do plano; coluna = mês)"):
        for nome, M in [("Previsão de vendas", s["V"]), ("Plano de produção", s["PP"])]:
            st.markdown(f"**{nome}**")
            st.dataframe(pd.DataFrame(M, index=s["versoes"], columns=s["meses"]).style.format("{:,.0f}", na_rep=""), width="stretch")
        st.markdown("**Realizado (última versão)**")
        st.dataframe(pd.DataFrame([s["realizado"], s["producao_real"], s["estoque_real"]], index=["Venda", "Produção", "Estoque"],
                                  columns=s["meses"][:s["T_real"]]).style.format("{:,.0f}", na_rep=""), width="stretch")
    if st.button("Copiar esta série como produto novo (para editar)", key="cad_copiar"):
        ss["_cad_origem"] = f"Copiar de {sku}"
        st.info("Abra **Criar ou editar** para ajustar e salvar a cópia.")


def criar_editar(dados, f):
    series = dados["series"]
    opcoes = ["Produto em branco"] + [f"Copiar de {k}" for k in series] + [f"Editar ✚ {p['nome']}" for p in ss["cadastrados"]]
    if "_cad_origem" in ss:
        ss["cad_origem"] = ss.pop("_cad_origem")
    if ss.get("cad_origem") not in opcoes:
        ss["cad_origem"] = opcoes[0]
    origem = st.selectbox("Começar de", opcoes, key="cad_origem")
    if origem == "Produto em branco":
        a, b = st.columns(2)
        inicio = a.text_input("Primeiro mês (mmm/aaaa)", "jan/2027", key="cad_inicio")
        n = b.number_input("Número de meses", 3, 36, 12, key="cad_n")
        if motor.mes_label(inicio) is None:
            st.error("Mês inválido. Use o formato mmm/aaaa, por exemplo jan/2027.")
            return
        p0 = motor.produto_novo("Novo produto", motor.mes_label(inicio), int(n))
        sig = f"branco_{motor.mes_label(inicio)}_{n}"
    elif origem.startswith("Copiar de "):
        sku = origem[len("Copiar de "):]
        p0 = motor.produto_da_base(series[sku], motor.versoes_validas(series[sku])[0])
        p0["nome"] = f"Cópia de {sku}"
        sig = f"copia_{sku}"
    else:
        nome = origem[len("Editar ✚ "):]
        p0 = next(p for p in ss["cadastrados"] if p["nome"] == nome)
        sig = f"edit_{nome}_{len(p0['meses'])}"

    st.markdown("**Atributos do produto**")
    c = st.columns(4)
    nome = c[0].text_input("Nome do produto", p0["nome"], key=f"nm_{sig}")
    origem_p = c[1].selectbox("Origem da produção", ["Interno", "Terceiro"], index=0 if p0["origem"] == "Interno" else 1, key=f"or_{sig}")
    cob = c[2].number_input("Cobertura-alvo (dias)", 0.0, 365.0, float(p0["cobertura_dias"]), 1.0, key=f"cb_{sig}")
    hb = c[3].number_input("HB (dias)", 0.0, 180.0, float(p0["hb_dias"]), 1.0, key=f"hb_{sig}")
    lt = c[0].number_input("Maior LT de insumo (semanas)", 0.0, 52.0, float(p0["lt_insumo_semanas"]), 1.0, key=f"lt_{sig}")
    preco = c[1].number_input("R$ PF (preço por unidade)", 0.0, 10_000.0, float(p0["preco"]), 0.1, key=f"pr_{sig}")
    lote = c[2].number_input("Lote mínimo (un.; 0 = sem lote)", 0, 10_000_000, int(p0["lote"]), 1, key=f"lo_{sig}")
    est = c[3].number_input("Estoque atual (un.)", 0.0, 1e9, float(p0["estoque_inicial"]), 1.0, key=f"es_{sig}")

    st.markdown("**Previsão de vendas e produção programada por mês** (edite as células; a produção programada é a que "
                "chega no mês)")
    tab = st.data_editor(_tabela_mensal(p0), key=f"ed_{sig}", num_rows="dynamic", width="stretch", hide_index=True,
                         column_config={"Previsão de vendas (un.)": st.column_config.NumberColumn(min_value=0, format="%.0f"),
                                        "Produção programada (un.)": st.column_config.NumberColumn(min_value=0, format="%.0f")})
    tab = tab.dropna(subset=["Mês"])
    meses = [motor.mes_label(m) for m in tab["Mês"]]
    p = dict(p0, nome=nome.strip(), origem=origem_p, cobertura_dias=cob, hb_dias=hb, lt_insumo_semanas=lt, preco=preco,
             lote=int(lote), estoque_inicial=est, meses=meses,
             previsao=[float(x) if pd.notna(x) else 0.0 for x in tab["Previsão de vendas (un.)"]],
             programada=[float(x) if pd.notna(x) else 0.0 for x in tab["Produção programada (un.)"]])
    erros = motor.validar_produto(p)
    if any(m is None for m in meses):
        erros.append("Há meses em formato inválido (use mmm/aaaa).")
    up, down = motor.janelas(p, f["par"])
    st.caption(f"Com estes dados: aumentar exige decidir {up} meses antes; reduzir, {down} meses antes. "
               f"Meses com previsão zero ficam fora das métricas e não acionam gatilho.")
    if p["nome"] in series:
        erros.append("Use um nome diferente dos produtos da base.")
    existe = any(q["nome"] == p["nome"] for q in ss["cadastrados"])
    if st.button("💾 Atualizar produto" if existe else "💾 Salvar produto", type="primary", disabled=bool(erros), key=f"sv_{sig}"):
        _gravar([p])
        ss["_selecionar"] = f"✚ {p['nome']}"
        ss["_cad_origem"] = f"Editar ✚ {p['nome']}"
        st.rerun()
    for e in erros:
        st.caption(f"⚠️ {e}")


def subir_planilha(dados, f):
    st.markdown("Use a **planilha modelo**: aba *Atributos* (uma linha por produto) e aba *Previsoes* (uma linha por produto e mês).")
    st.download_button("⬇ Baixar planilha modelo", motor.planilha_modelo([motor.produto_novo("Exemplo")]),
                       file_name="SOLARIS_modelo_importacao.xlsx", key="modelo_cad")
    arq = st.file_uploader("Planilha preenchida (.xlsx)", type=["xlsx"], key="cad_upload")
    if not arq:
        return
    produtos, avisos = motor.ler_planilha_produtos(arq)
    for a in avisos:
        st.warning(a)
    if not produtos:
        return
    resumo = pd.DataFrame([{"Produto": p["nome"], "Origem": p["origem"], "Cobertura (dias)": p["cobertura_dias"], "HB (dias)": p["hb_dias"],
                            "LT insumo (sem.)": p["lt_insumo_semanas"], "R$ PF": p["preco"], "Lote": p["lote"],
                            "Estoque": p["estoque_inicial"], "Meses": len(p["meses"]),
                            "De": p["meses"][0], "Até": p["meses"][-1], "Previsão total": sum(p["previsao"]),
                            "Problemas": " ".join(motor.validar_produto(p)) or "ok"} for p in produtos])
    st.dataframe(resumo, hide_index=True, width="stretch")
    validos = [p for p in produtos if not motor.validar_produto(p) and p["nome"] not in dados["series"]]
    if st.button(f"Cadastrar {len(validos)} produto(s)", type="primary", disabled=not validos, key="cad_imp"):
        _gravar(validos)
        ss["_selecionar"] = f"✚ {validos[0]['nome']}"
        st.success("Produtos cadastrados. Eles aparecem na barra lateral com o símbolo ✚.")
        st.rerun()


def lista_cadastrados(dados, f):
    lista = ss["cadastrados"]
    if not lista:
        st.info("Nenhum produto cadastrado ainda.")
        return
    st.dataframe(pd.DataFrame([{"Produto": p["nome"], "Origem": p["origem"], "Cobertura (dias)": p["cobertura_dias"],
                                "HB (dias)": p["hb_dias"], "LT insumo (sem.)": p["lt_insumo_semanas"], "R$ PF": p["preco"],
                                "Lote": p["lote"], "Estoque": p["estoque_inicial"], "Meses": f"{p['meses'][0]} a {p['meses'][-1]}",
                                "Previsão total": motor.num(sum(p["previsao"]))} for p in lista]), hide_index=True, width="stretch")
    st.caption(f"Arquivo: {motor.ARQUIVO_PRODUTOS}")
    a, b = st.columns(2)
    a.download_button("⬇ Baixar todos na planilha modelo", motor.planilha_modelo(lista), file_name="SOLARIS_produtos_cadastrados.xlsx",
                      key="cad_baixar")
    apagar = b.multiselect("Apagar produtos", [p["nome"] for p in lista], key="cad_apagar")
    if apagar and b.button(f"🗑 Apagar {len(apagar)} produto(s)", key="cad_apagar_btn"):
        ss["cadastrados"] = [p for p in lista if p["nome"] not in apagar]
        motor.salvar_cadastrados(ss["cadastrados"])
        st.rerun()


def mostrar(dados, f):
    st.subheader("Cadastro de produtos")
    secoes = {"Produtos da base": ver_base, "Criar ou editar": criar_editar, "Subir planilha": subir_planilha,
              "Produtos cadastrados": lista_cadastrados}
    escolha = st.segmented_control("Seção", list(secoes), default="Criar ou editar", key="cad_secao", label_visibility="collapsed")
    secoes[escolha or "Criar ou editar"](dados, f)
