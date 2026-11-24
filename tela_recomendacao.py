# tela_recomendacao.py — Tela 3: qual política usar, por quê, e se a resposta muda com a sensibilidade.
import pandas as pd
import streamlit as st

import motor

ss = st.session_state


def tabela_politicas(resumo, par):
    t = resumo.copy()
    t["Política"] = t["politica"].map(motor.NOME_POLITICA)
    t["Cumpre metas"] = t.apply(lambda r: "—" if r["politica"] == "PROG" else ("✅" if r["cumpre_metas"] else "❌"), axis=1)
    out = pd.DataFrame({
        "Política": t["Política"], "Cumpre metas": t["Cumpre metas"],
        "Nível de serviço": t["nivel_servico"].map(motor.pct), "Nível garantido (P5)": t["nivel_garantido"].map(motor.pct),
        "% meses com falta": t["meses_falta"].map(lambda v: motor.pct(v, 0)),
        f"% meses cobertura < {par['cob_min']}d": t["meses_cob_baixa"].map(lambda v: motor.pct(v, 0)),
        f"% meses cobertura > {par['cob_max']}d": t["meses_excesso"].map(lambda v: motor.pct(v, 0)),
        "Estoque médio (un.)": t["estoque_medio"].map(motor.num), "Reserva média (un.)": t["reserva_media"].map(motor.num),
        "Estoque final (un.)": t["estoque_final"].map(motor.num), "Unidades reduzidas": t["unidades_cortadas"].map(motor.num),
        "Custo total esperado": t["custo_total"].map(motor.mi), "Custo P95": t["custo_p95"].map(motor.mi)})
    return out


def mostrar(dados, f):
    res = f["resultado"]
    if res is None:
        st.info("Ainda não há resultado. Escolha o produto e as análises na barra lateral e clique em **▶ Rodar simulação** "
                "(ou abra uma rodada salva na aba Histórico).")
        return
    prod, par = res["produto"], res["parametros"]
    if prod["nome"] != f["produto"]["nome"]:
        st.warning(f"Este resultado é de **{prod['nome']}**. O produto escolhido na barra lateral agora é "
                   f"**{f['produto']['nome']}**: clique em Rodar simulação para atualizar.")
    cen = f["cenario"]
    cd = res["cenarios"][cen]
    b = res["melhor"].set_index("cenario").loc[cen]
    resumo = res["resumo"][res["resumo"]["cenario"] == cen]

    # ---------- Cartão principal ----------
    with st.container(border=True):
        st.markdown(f"### Política recomendada: **{motor.NOME_POLITICA[b['como_executar']]}**")
        if b["como_executar"] != b["politica"]:
            st.caption(f"A melhor no Monte Carlo foi {motor.NOME_POLITICA[b['politica']]}; como o produto tem lote mínimo de "
                       f"{motor.num(prod['lote'])} un., a execução usa a versão em lotes.")
        if b["cumpre_metas"]:
            st.success(f"Cumpre as metas (serviço ≥ {motor.pct(par['meta_servico'], 0)} e garantido ≥ "
                       f"{motor.pct(par['meta_garantido'], 0)}) com o **menor custo** entre as que cumprem.")
        else:
            st.error(f"Nenhuma política cumpre as metas neste cenário. A indicada é a de **maior nível garantido**: "
                     f"levar ao S&OP a discussão de meta, cobertura-alvo ou janela.")
        c = st.columns(5)
        c[0].metric("Nível de serviço", motor.pct(b["nivel_servico"]), border=True, help="Média dos futuros simulados.")
        c[1].metric("Nível garantido (P5)", motor.pct(b["nivel_garantido"]), border=True,
                    help="Em 95% dos futuros o nível de serviço fica acima deste valor.")
        c[2].metric("% meses com falta", motor.pct(b["meses_falta"], 0), border=True)
        c[3].metric(f"% meses > {par['cob_max']} dias", motor.pct(b["meses_excesso"], 0), border=True)
        c[4].metric("Custo esperado (R$)", motor.num(b["custo_total"] / 1e6, 1) + " mi", border=True,
                    delta=None if pd.isna(b.get("custo_vs_programado")) else f"{motor.pct(b['custo_vs_programado'], 0)} vs programado",
                    delta_color="inverse")
        st.caption(f"Janela de reação neste cenário: para **aumentar**, decidir com **{cd['janela_aumento']} meses** de antecedência; "
                   f"para **reduzir**, com **{cd['janela_reducao']} meses** ({par['regra_janela'].lower()}"
                   f"{', com mês de decisão' if par['mes_decisao'] else ''}). Proteção {par['protecao']} (z = {res['z']}).")

    # ---------- Comparação das políticas ----------
    st.subheader("Comparação das políticas neste cenário")
    st.dataframe(tabela_politicas(resumo, par), hide_index=True, width="stretch")
    st.caption("Métricas de avaliação consideram só os meses com previsão de venda. Custos somam todo o horizonte. "
               "O plano programado segue o plano do sistema até o último mês programado e depois repõe o previsto.")

    # ---------- Sensibilidade ----------
    if len(res["cenarios"]) > 1:
        st.subheader("A recomendação muda com a sensibilidade?")
        m = res["melhor"]
        st.dataframe(pd.DataFrame({
            "Cenário": m["cenario"], "Política": m["como_executar"].map(motor.NOME_POLITICA),
            "Cumpre metas": m["cumpre_metas"].map({True: "✅", False: "❌"}), "Nível de serviço": m["nivel_servico"].map(motor.pct),
            "Garantido (P5)": m["nivel_garantido"].map(motor.pct), "Custo total": m["custo_total"].map(motor.mi)}),
            hide_index=True, width="stretch")
        n_pol = m["como_executar"].nunique()
        st.caption("A mesma política em todos os cenários: recomendação robusta." if n_pol == 1 else
                   f"A política muda entre os cenários ({n_pol} diferentes): a escolha depende da premissa de demanda/choque/HB.")

    # ---------- Segunda opinião ----------
    st.subheader("Segunda opinião: séries parecidas no experimento anterior")
    so = motor.segunda_opiniao(prod, motor.carregar_referencia(), cd["distribuicao"], cd["choque"], cd["hb_dias"])
    if so is None:
        st.caption("Coloque o arquivo solaris_resultados.json na pasta do projeto para ver a segunda opinião.")
    else:
        cols = st.columns(3)
        for col, t in zip(cols, so["top"]):
            col.metric(t["serie"], motor.NOME_POLITICA.get(t["politica"], t["politica"]).split(" · ")[0],
                       f"semelhança {motor.num(t['semelhanca'])}/100", delta_color="off", border=True)
        txt = (f"Confiança **{so['confianca']}** (concordância entre as 3 mais parecidas). Referência: experimento anterior, "
               f"janela simples, distribuição {so['dist_ref']}, HB {so['hb']} dias.")
        if so.get("proprio"):
            txt += f" No experimento anterior, a própria série {prod.get('sku_base')} ficou com **{so['proprio'][0]}**."
        st.caption(txt)
        sim_pol = {t["politica"] for t in so["top"]}
        if b["politica"] not in sim_pol:
            st.info("A simulação deste produto e as séries parecidas apontam políticas diferentes. Vale a simulação "
                    "(é feita com os dados do próprio produto); a segunda opinião serve de alerta para revisar as premissas.")
        with st.expander("Ranking completo de semelhança"):
            r = so["ranking"].rename(columns={"sku": "Série", "kind": "Tipo", "origin": "Origem", "target_days": "Cobertura (dias)",
                                              "max_material_lt_weeks": "LT insumo (sem.)", "forecast_cv": "Variação da previsão (CV)",
                                              "forecast_peak_ratio": "Pico ÷ média", "semelhanca": "Semelhança"})
            st.dataframe(r.round(2), hide_index=True, width="stretch")

    # ---------- Stockpyl ----------
    if res.get("stockpyl") is not None and len(res["stockpyl"]):
        st.subheader("Confirmação no Stockpyl")
        v = res["stockpyl"]
        v = v[v["cenario"] == cen] if "cenario" in v else v
        ok = v["identico"].mean() if len(v) else float("nan")
        c = st.columns(3)
        c[0].metric("Trajetórias idênticas", motor.pct(ok, 0), border=True)
        c[1].metric("Maior diferença de estoque", f"{motor.num(v['maior_diferenca_un'].max(), 2)} un.", border=True)
        c[2].metric("Simulações comparadas", motor.num(len(v)), border=True)
        st.caption("O Stockpyl recebeu as mesmas demandas, choques e decisões de produção do SOLARIS. Trajetórias idênticas "
                   "confirmam que o simulador do SOLARIS reproduz a dinâmica de estoque, pendência e choque do Stockpyl.")
        st.dataframe(v.groupby("politica")[["estoque_medio_solaris", "estoque_medio_stockpyl", "maior_diferenca_un"]].mean()
                     .rename(index=motor.NOME_POLITICA).style.format("{:,.2f}"), width="stretch")

    # ---------- Downloads ----------
    st.subheader("Baixar esta rodada")
    a, b2 = st.columns(2)
    a.download_button("⬇ Excel completo", motor.bytes_excel(res), file_name=f"SOLARIS_{res['id']}.xlsx", key="rec_xlsx",
                      width="stretch")
    b2.download_button("⬇ JSON (para reabrir)", motor.json_resultado(res), file_name=f"SOLARIS_{res['id']}.json", key="rec_json",
                       width="stretch")
