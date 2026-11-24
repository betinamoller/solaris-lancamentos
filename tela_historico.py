# tela_historico.py — Tela 6: todas as rodadas salvas no Drive: consultar, reabrir nas telas, baixar e apagar.
import pandas as pd
import streamlit as st

import motor

ss = st.session_state


def mostrar(dados, f):
    st.subheader("Histórico de rodadas")
    st.caption(f"Pasta: {motor.PASTA_HIST} · cada rodada gera um .json (para reabrir) e um .xlsx (para analisar).")
    h = motor.listar_historico()
    if h.empty:
        st.info("Nenhuma rodada salva ainda. Cada vez que você roda a simulação, o resultado é salvo aqui automaticamente.")
        return

    produtos = sorted(h["produto"].unique())
    filtro = st.multiselect("Filtrar por produto", produtos, key="hist_filtro", placeholder="Todos os produtos")
    if filtro:
        h = h[h["produto"].isin(filtro)]
    st.dataframe(pd.DataFrame({
        "Data": h["data"], "Produto": h["produto"], "Cenário": h["cenario"], "Política": h["como_executar"].map(motor.NOME_POLITICA),
        "Cumpre metas": h["cumpre_metas"].map({True: "✅", False: "❌"}), "Nível de serviço": h["nivel_servico"].map(motor.pct),
        "Garantido (P5)": h["nivel_garantido"].map(motor.pct), "Custo total": h["custo_total"].map(motor.mi),
        "Simulações": h["simulacoes"], "Proteção": h["protecao"], "Stockpyl": h["stockpyl"].map({True: "sim", False: ""}),
        "Arquivo": h["arquivo"]}), hide_index=True, width="stretch")

    rodadas = list(dict.fromkeys(h["arquivo"]))
    rot = {a: f"{h.loc[h['arquivo'] == a, 'data'].iloc[0]} · {h.loc[h['arquivo'] == a, 'produto'].iloc[0]}" for a in rodadas}
    st.markdown("**Consultar uma rodada**")
    nome = st.selectbox("Rodada", rodadas, format_func=rot.get, key="hist_sel", label_visibility="collapsed")
    c = st.columns(4)
    if c[0].button("📂 Abrir nas telas", type="primary", key="hist_abrir", width="stretch"):
        ss["resultado"] = motor.carregar_resultado(nome)
        st.rerun()
    xlsx, js = motor.bytes_historico(nome, ".xlsx"), motor.bytes_historico(nome, ".json")
    if xlsx:
        c[1].download_button("⬇ Excel", xlsx, file_name=f"{nome}.xlsx", key="hist_xlsx", width="stretch")
    if js:
        c[2].download_button("⬇ JSON", js, file_name=f"{nome}.json", key="hist_json", width="stretch")
    with c[3].popover("🗑 Apagar", width="stretch"):
        st.write(f"Apagar a rodada **{rot[nome]}**? Não dá para desfazer.")
        if st.button("Sim, apagar", key="hist_apagar"):
            motor.apagar_resultado(nome)
            if ss.get("resultado") is not None and ss["resultado"].get("_arquivo") == nome:
                ss["resultado"] = None
            st.rerun()

    st.download_button("⬇ Baixar todo o histórico (.zip)", motor.zip_historico(), file_name="SOLARIS_historico.zip", key="hist_zip")

    st.divider()
    st.markdown("**Reabrir uma rodada a partir de um JSON baixado**")
    arq = st.file_uploader("Arquivo .json de uma rodada", type=["json"], key="hist_up")
    if arq and st.button("Importar para o histórico", key="hist_imp"):
        motor.PASTA_HIST.mkdir(parents=True, exist_ok=True)
        nome_novo = arq.name.rsplit(".", 1)[0].removeprefix("SOLARIS_")
        (motor.PASTA_HIST / f"{nome_novo}.json").write_bytes(arq.getvalue())
        r = motor.carregar_resultado(nome_novo)
        (motor.PASTA_HIST / f"{nome_novo}.xlsx").write_bytes(motor.excel_resultado(r))
        ss["resultado"] = motor.carregar_resultado(nome_novo)
        st.rerun()
