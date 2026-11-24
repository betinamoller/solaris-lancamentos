# tela_acao.py — Tela 4: o que fazer em cada mês, até quando decidir e quais meses acendem gatilho no S&OE.
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import motor


def _cor_gatilho(v):
    if v in ("Crítico", "Atenção"):
        return f"background-color: {motor.CORES[v]}; color: white; font-weight: 600"
    return f"color: {motor.CORES['OK']}" if v == "OK" else ""


def _cor_acao(v):
    return {"Produzir mais": "color: #1A5276; font-weight: 600", "Reduzir": "color: #7D3C98; font-weight: 600",
            "Aumento fora do prazo": "color: #C0392B; font-weight: 600", "Congelado": "color: #7F8C8D"}.get(v, "")


def mostrar(dados, f):
    res = f["resultado"]
    if res is None:
        st.info("Rode a simulação (barra lateral) ou abra uma rodada do Histórico para ver o plano de ação.")
        return
    cen = f["cenario"]
    cd = res["cenarios"][cen]
    melhor = res["melhor"].set_index("cenario").loc[cen]
    pols = [p for p in res["resumo"].loc[res["resumo"]["cenario"] == cen, "politica"].unique() if p != "PROG"]
    a, b = st.columns([2, 3])
    pol = a.selectbox("Política do plano", pols, index=pols.index(melhor["como_executar"]) if melhor["como_executar"] in pols else 0,
                      format_func=lambda p: motor.NOME_POLITICA[p] + (" (recomendada)" if p == melhor["como_executar"] else ""),
                      key="acao_pol")
    b.markdown(f"**Janela:** aumentar exige decidir **{cd['janela_aumento']} meses** antes do mês; reduzir, "
               f"**{cd['janela_reducao']} meses** antes. Meses dentro do HB estão congelados.")

    tab = motor.plano_e_acoes(res, cen, pol)
    n_crit, n_at = int((tab["gatilho"] == "Crítico").sum()), int((tab["gatilho"] == "Atenção").sum())
    c = st.columns(4)
    c[0].metric("Meses críticos", n_crit, border=True)
    c[1].metric("Meses em atenção", n_at, border=True)
    c[2].metric("Produção recomendada", motor.num(tab["recomendada"].sum()), border=True,
                delta=f"{motor.num(tab['recomendada'].sum() - tab['programada'].sum())} vs programado", delta_color="off")
    prox = tab[(tab["acao"] != "Manter") & (tab["acao"] != "Congelado") & (tab["previsao"] > 0)]
    c[3].metric("Próxima decisão", prox["mes"].iloc[0] if len(prox) else "—", border=True,
                help="Primeiro mês com previsão em que o recomendado difere do programado.")

    # ---------- Gráfico: programado × recomendado e estoque projetado ----------
    fig = go.Figure()
    fig.add_bar(x=tab["mes"], y=tab["programada"], name="Produção programada", marker_color="#c3c7cc")
    fig.add_bar(x=tab["mes"], y=tab["recomendada"], name=f"Produção recomendada ({pol})", marker_color=motor.COR_POLITICA.get(pol))
    fig.add_scatter(x=tab["mes"], y=tab["previsao"], name="Previsão de vendas", mode="lines+markers", line=dict(color="#52514e", width=2))
    fig.add_scatter(x=tab["mes"], y=tab["estoque_proj_programado"], name="Estoque projetado (programado)", mode="lines",
                    line=dict(color="#8a8f98", dash="dot"))
    fig.add_scatter(x=tab["mes"], y=tab["estoque_proj_recomendado"], name="Estoque projetado (recomendado)", mode="lines",
                    line=dict(color=motor.COR_POLITICA.get(pol), dash="dot"))
    for _, r in tab[tab["gatilho"].isin(["Crítico", "Atenção"])].iterrows():
        fig.add_annotation(x=r["mes"], y=max(r["previsao"], r["recomendada"], r["programada"]), text="●", showarrow=False,
                           font=dict(color=motor.CORES[r["gatilho"]], size=16), yshift=10)
    fig.update_layout(barmode="group", height=380, separators=",.", margin=dict(t=30, b=10, l=10, r=10),
                      legend=dict(orientation="h", y=-0.2), yaxis_title="unidades")
    st.plotly_chart(fig, width="stretch")
    st.caption("Plano recomendado = a política aplicada à previsão atual (como se ela se confirmasse). Os riscos de falta e "
               "de excesso vêm dos futuros simulados com o plano programado.")

    # ---------- Tabela de ações ----------
    so_gat = st.toggle("Mostrar só meses com gatilho ou mudança", value=False, key="acao_filtro")
    t = tab.copy()
    if so_gat:
        t = t[(t["gatilho"].isin(["Crítico", "Atenção"])) | (~t["acao"].isin(["Manter", "Congelado"]))]
    vis = pd.DataFrame({
        "Mês": t["mes"], "Gatilho": t["gatilho"], "Ação": t["acao"], "Previsão": t["previsao"].map(motor.num),
        "Programado": t["programada"].map(motor.num), "Recomendado": t["recomendada"].map(motor.num),
        "Diferença": t["diferenca"].map(motor.num), "Decidir aumento até": t["decidir_aumento_ate"],
        "Decidir redução até": t["decidir_reducao_ate"], "Estoque proj. (programado)": t["estoque_proj_programado"].map(motor.num),
        "Cobertura (programado, dias)": t["cobertura_programado"].map(motor.num),
        "Risco de falta": t["risco_falta"].map(lambda v: motor.pct(v, 0)),
        "Risco de excesso": t["risco_excesso"].map(lambda v: motor.pct(v, 0)), "Motivo": t["motivo"], "O que fazer": t["o_que_fazer"]})
    st.dataframe(vis.style.map(_cor_gatilho, subset=["Gatilho"]).map(_cor_acao, subset=["Ação"]), hide_index=True, width="stretch",
                 height=min(38 * (len(vis) + 1) + 4, 600))
    with st.expander("Regras dos gatilhos"):
        g = motor.GATILHO
        st.markdown(
            f"- **Crítico:** falta projetada com o plano programado, cobertura abaixo de {res['parametros']['cob_min']} dias "
            f"ou risco de falta ≥ {motor.pct(g['risco_critico'], 0)} nos futuros simulados.\n"
            f"- **Atenção:** risco de falta ≥ {motor.pct(g['risco_atencao'], 0)}, cobertura acima de "
            f"{res['parametros']['cob_max']} dias ou risco de excesso ≥ {motor.pct(g['risco_excesso_atencao'], 0)}, ou "
            f"programado diferente do recomendado em {motor.pct(g['desvio_atencao'], 0)} ou mais (fora do HB).\n"
            f"- **Sem gatilho (—):** meses com previsão de vendas igual a zero. Meses com previsão zero dentro do HB nem aparecem.\n"
            f"- **Aumento fora do prazo:** o recomendado é maior que o programado, mas o mês já passou do prazo para aumentar "
            f"(insumo + produção); só é possível reduzir ou buscar alternativas.")

    # ---------- Ata para a reunião ----------
    st.subheader("Ata da reunião de S&OE")
    ata = t[t["gatilho"].isin(["Crítico", "Atenção"]) | (~t["acao"].isin(["Manter", "Congelado"]))][
        ["mes", "gatilho", "acao", "diferenca", "decidir_aumento_ate", "decidir_reducao_ate", "o_que_fazer"]].copy()
    ata = ata.rename(columns={"mes": "Mês", "gatilho": "Gatilho", "acao": "Ação", "diferenca": "Diferença (un.)",
                              "decidir_aumento_ate": "Aumento até", "decidir_reducao_ate": "Redução até", "o_que_fazer": "O que fazer"})
    ata["Responsável"], ata["Status"], ata["Observação"] = "", "Aberto", ""
    ed = st.data_editor(ata, hide_index=True, width="stretch", key=f"ata_{res['id']}_{cen}_{pol}",
                        disabled=["Mês", "Gatilho", "Ação", "Diferença (un.)", "Aumento até", "Redução até", "O que fazer"],
                        column_config={"Status": st.column_config.SelectboxColumn(options=["Aberto", "Em andamento", "Feito", "Não se aplica"]),
                                       "Diferença (un.)": st.column_config.NumberColumn(format="%.0f")})
    st.caption("O editor não salva sozinho: baixe a ata ao fim da reunião.")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        ed.to_excel(w, sheet_name="Ata", index=False)
        tab.to_excel(w, sheet_name="Plano_completo", index=False)
    a, b = st.columns(2)
    a.download_button("⬇ Ata + plano (Excel)", buf.getvalue(), file_name=f"SOLARIS_acao_{res['id']}_{pol}.xlsx", key="acao_xlsx",
                      width="stretch")
    b.download_button("⬇ Plano (CSV)", tab.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                      file_name=f"SOLARIS_plano_{res['id']}_{pol}.csv", key="acao_csv", width="stretch")
