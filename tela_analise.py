# tela_analise.py — Tela 5: gráficos para entender o resultado (faixa de estoque, risco por mês, custo × serviço,
# distribuição do serviço, sensibilidade, curva de incerteza, backtest com o histórico real e confirmação no Stockpyl).
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import motor

LAYOUT = dict(height=360, separators=",.", margin=dict(t=50, b=10, l=10, r=10), legend=dict(orientation="h", y=-0.22),
              hovermode="x unified")


def _rgba(hex_, a):
    h = hex_.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def _nome(p):
    return motor.NOME_POLITICA.get(p, p).split(" · ")[0]


def faixa_estoque(res, cen, pols):
    prod = res["produto"]
    fig = go.Figure()
    fig.add_scatter(x=prod["meses"], y=prod["previsao"], name="Previsão de vendas", mode="lines", line=dict(color="#52514e", width=2, dash="dash"))
    tab = []
    for p in pols:
        m = res["mensal"].get((cen, p))
        if m is None:
            continue
        cor = motor.COR_POLITICA[p]
        fig.add_scatter(x=prod["meses"] + prod["meses"][::-1], y=list(m["estoque_p95"]) + list(m["estoque_p5"])[::-1], fill="toself",
                        fillcolor=_rgba(cor, 0.15), line=dict(width=0), name=f"{_nome(p)} · faixa P5–P95", hoverinfo="skip",
                        showlegend=True)
        fig.add_scatter(x=prod["meses"], y=m["estoque_p50"], name=f"{_nome(p)} · mediana", mode="lines+markers",
                        line=dict(color=cor, width=2), marker=dict(size=8))
        tab.append(m[["estoque_p5", "estoque_p50", "estoque_p95"]].assign(politica=_nome(p), mes=prod["meses"]))
    fig.update_layout(title="Estoque no fim do mês: mediana e faixa de 90% dos futuros", yaxis_title="unidades", **LAYOUT)
    return fig, pd.concat(tab) if tab else pd.DataFrame()


def risco_mensal(res, cen, pols):
    prod = res["produto"]
    fig = go.Figure()
    for p in pols:
        m = res["mensal"].get((cen, p))
        if m is None:
            continue
        cor = motor.COR_POLITICA[p]
        fig.add_scatter(x=prod["meses"], y=m["prob_falta"], name=f"{_nome(p)} · risco de falta", mode="lines+markers",
                        line=dict(color=cor, width=2), marker=dict(size=8))
        fig.add_scatter(x=prod["meses"], y=m["prob_excesso"], name=f"{_nome(p)} · risco de excesso", mode="lines+markers",
                        line=dict(color=cor, width=2, dash="dot"), marker=dict(size=8, symbol="diamond"))
    for y, txt in [(motor.GATILHO["risco_critico"], "crítico"), (motor.GATILHO["risco_atencao"], "atenção")]:
        fig.add_hline(y=y, line_dash="dash", line_color="#8a8f98", line_width=1, annotation_text=txt, annotation_position="top left")
    fig.update_layout(title="Probabilidade de faltar e de passar do limite de excesso, mês a mês", yaxis=dict(tickformat=".0%", range=[0, 1.02]),
                      **LAYOUT)
    return fig


def custo_servico(res, cen_atual):
    r = res["resumo"]
    fig = go.Figure()
    simbolos = ["circle", "square", "diamond", "triangle-up", "x", "star", "hexagon", "cross"]
    cens = list(res["cenarios"])
    for p in r["politica"].unique():
        g = r[r["politica"] == p]
        fig.add_scatter(x=g["custo_total"] / 1e6, y=g["nivel_garantido"], mode="markers", name=_nome(p),
                        marker=dict(color=motor.COR_POLITICA[p], size=[16 if c == cen_atual else 10 for c in g["cenario"]],
                                    symbol=[simbolos[cens.index(c) % len(simbolos)] for c in g["cenario"]],
                                    line=dict(color="white", width=2)),
                        text=g["cenario"], hovertemplate="%{text}<br>custo R$ %{x:,.2f} mi<br>garantido %{y:.1%}<extra>" + _nome(p) + "</extra>")
    meta = res["parametros"]["meta_garantido"]
    fig.add_hline(y=meta, line_dash="dash", line_color="#8a8f98", annotation_text=f"meta garantida {motor.pct(meta, 0)}")
    fig.update_layout(title="Custo total esperado × nível garantido (P5) — todos os cenários", xaxis_title="custo total (R$ mi)",
                      yaxis=dict(tickformat=".0%"), **dict(LAYOUT, hovermode="closest"))
    return fig


def composicao_custo(res, cen):
    r = res["resumo"][res["resumo"]["cenario"] == cen]
    fig = go.Figure()
    partes = [("custo_estoque", "Manter estoque", "#2a78d6"), ("custo_falta", "Falta (pendência)", "#e34948"),
              ("custo_sobra", "Sobra no fim", "#eda100"), ("custo_excesso", "Excesso > 6 meses", "#6250d6")]
    for col, nome, cor in partes:
        fig.add_bar(x=[_nome(p) for p in r["politica"]], y=r[col] / 1e6, name=nome, marker=dict(color=cor, line=dict(color="white", width=2)),
                    hovertemplate="%{x}: R$ %{y:,.2f} mi<extra>" + nome + "</extra>")
    fig.update_layout(barmode="stack", title="De onde vem o custo (média dos futuros)", yaxis_title="R$ mi", **dict(LAYOUT, hovermode="closest"))
    return fig


def distribuicao_servico(res, cen):
    rep = res["repeticoes"]
    rep = rep[rep["cenario"] == cen]
    fig = go.Figure()
    for p in rep["politica"].unique():
        fig.add_box(y=rep.loc[rep["politica"] == p, "nivel_servico"], name=_nome(p), marker_color=motor.COR_POLITICA[p], boxpoints=False)
    fig.add_hline(y=res["parametros"]["meta_servico"], line_dash="dash", line_color="#8a8f98", annotation_text="meta")
    fig.update_layout(title="Nível de serviço em cada futuro simulado", yaxis=dict(tickformat=".0%"), showlegend=False,
                      **dict(LAYOUT, hovermode="closest"))
    return fig


def mapa_melhor(res):
    m = res["melhor"].copy()
    m["linha"] = m["distribuicao"] + " · " + m["choque"]
    m["coluna"] = "HB " + m["hb_dias"].astype(int).astype(str) + " dias"
    z = m.pivot(index="linha", columns="coluna", values="nivel_garantido")
    txt = m.assign(t=m["como_executar"].map(_nome) + "<br>" + m["nivel_garantido"].map(motor.pct) + m["cumpre_metas"].map(
        {True: " ✓", False: " ✗"})).pivot(index="linha", columns="coluna", values="t")
    fig = go.Figure(go.Heatmap(z=z.values, x=list(z.columns), y=list(z.index), text=txt.values, texttemplate="%{text}",
                               colorscale=[[0, "#f3f1ee"], [1, "#2a78d6"]], zmin=0.5, zmax=1, xgap=2, ygap=2,
                               colorbar=dict(title="garantido", tickformat=".0%"),
                               hovertemplate="%{y} · %{x}<br>%{text}<extra></extra>"))
    fig.update_layout(title="Política recomendada e nível garantido em cada cenário", height=120 + 60 * len(z), separators=",.",
                      margin=dict(t=50, b=10, l=10, r=10))
    return fig


def curva(res):
    c = pd.DataFrame(res["curva"])
    fig = go.Figure(go.Bar(x=c["h"], y=c["cv"] * res["parametros"]["mult_incerteza"], marker=dict(color="#2a78d6", cornerradius=4),
                           text=[motor.pct(v, 0) for v in c["cv"] * res["parametros"]["mult_incerteza"]], textposition="outside",
                           hovertemplate="horizonte %{x} meses<br>erro %{y:.0%}<extra></extra>"))
    fig.update_layout(title="Erro da previsão por horizonte (benchmarks)", xaxis_title="meses entre a previsão e o mês-alvo",
                      yaxis=dict(tickformat=".0%", title="desvio do erro ÷ previsão média"), **dict(LAYOUT, hovermode="closest"))
    return fig


def mostrar(dados, f):
    res = f["resultado"]
    if res is None:
        st.info("Rode a simulação (barra lateral) ou abra uma rodada do Histórico para ver os gráficos.")
        return
    cen = f["cenario"]
    disponiveis = [p for p in ["P2", "P3", "P4", "P2L", "PROG"] if (cen, p) in res["mensal"]]
    melhor = res["melhor"].set_index("cenario").loc[cen, "como_executar"]
    pols = st.multiselect("Políticas nos gráficos", disponiveis, default=[p for p in dict.fromkeys([melhor, "PROG"]) if p in disponiveis],
                          format_func=lambda p: motor.NOME_POLITICA[p], key="an_pols")
    if not pols:
        st.warning("Escolha pelo menos uma política.")
        return

    fig, tab = faixa_estoque(res, cen, pols)
    st.plotly_chart(fig, width="stretch")
    with st.expander("Ver dados da faixa de estoque"):
        st.dataframe(tab.round(0), hide_index=True, width="stretch")
    st.plotly_chart(risco_mensal(res, cen, pols), width="stretch")

    a, b = st.columns(2)
    a.plotly_chart(custo_servico(res, cen), width="stretch")
    b.plotly_chart(composicao_custo(res, cen), width="stretch")

    a, b = st.columns(2)
    if res.get("repeticoes") is not None:
        a.plotly_chart(distribuicao_servico(res, cen), width="stretch")
    else:
        a.info("A distribuição por futuro simulado só aparece em rodadas feitas nesta sessão (o histórico guarda os resumos; "
               "as repetições ficam no Excel da rodada).")
    b.plotly_chart(curva(res), width="stretch")

    if len(res["cenarios"]) > 1:
        st.plotly_chart(mapa_melhor(res), width="stretch")

    # ---------- Backtest com o histórico real ----------
    prod = res["produto"]
    serie = dados["series"].get(prod.get("sku_base")) if prod.get("fonte") == "base" else None
    st.subheader("Backtest com o histórico real")
    bt = motor.backtest_historico(serie, res["parametros"], res["z"], pd.DataFrame(res["curva"]), prod.get("versao", 0)) if serie else None
    if bt is None:
        st.caption("Disponível para séries da base com pelo menos 3 meses de venda realizada a partir da versão escolhida: "
                   "aplica cada política às previsões que a L'Oréal de fato tinha em cada mês e à venda real. "
                   "P0 = o que aconteceu (estoque real da base).")
    else:
        t = bt["tabela"]
        fig = go.Figure()
        fig.add_bar(x=bt["meses"], y=bt["realizado"], name="Venda realizada", marker=dict(color="#c3c7cc", cornerradius=4))
        for _, r in t.iterrows():
            fig.add_scatter(x=bt["meses"], y=r["_estoque"], name=f"Estoque · {r['politica']}", mode="lines+markers",
                            line=dict(color=motor.COR_POLITICA.get(r["politica"], "#8a8f98"), width=2,
                                      dash="dash" if r["politica"] == "P0" else "solid"), marker=dict(size=8))
        fig.update_layout(title=f"{prod['sku_base']}: estoque de cada política com a venda real (P0 = estoque real; negativo = pendência)",
                          yaxis_title="unidades", **LAYOUT)
        st.plotly_chart(fig, width="stretch")
        st.dataframe(pd.DataFrame({"Política": t["politica"].map(lambda p: motor.NOME_POLITICA.get(p, p)),
                                   "Nível de serviço": t["nivel_servico"].map(motor.pct), "% meses com falta": t["meses_falta"].map(lambda v: motor.pct(v, 0)),
                                   "% meses > limite": t["meses_excesso"].map(lambda v: motor.pct(v, 0)),
                                   "Estoque médio": t["estoque_medio"].map(motor.num), "Estoque final": t["estoque_final"].map(motor.num),
                                   "Custo total": t["custo_total"].map(motor.mi)}), hide_index=True, width="stretch")
        st.caption(f"Começa na versão {bt['versao']}. Um único futuro (o que aconteceu): serve para checar se a política faria sentido "
                   "na prática, não substitui o Monte Carlo. A venda realizada é tratada como demanda (a demanda perdida não é observada), "
                   "por isso o P0 tem nível de serviço de 100% por construção.")

    # ---------- Stockpyl ----------
    v = res.get("stockpyl")
    if v is not None and len(v):
        st.subheader("SOLARIS × Stockpyl")
        v = v[v["cenario"] == cen]
        fig = go.Figure()
        for p in v["politica"].unique():
            g = v[v["politica"] == p]
            fig.add_scatter(x=g["estoque_medio_solaris"], y=g["estoque_medio_stockpyl"], mode="markers", name=_nome(p),
                            marker=dict(color=motor.COR_POLITICA[p], size=9, line=dict(color="white", width=2)))
        lim = [0, float(max(v["estoque_medio_solaris"].max(), v["estoque_medio_stockpyl"].max()) * 1.05 or 1)]
        fig.add_scatter(x=lim, y=lim, mode="lines", line=dict(color="#8a8f98", dash="dash", width=1), name="iguais", hoverinfo="skip")
        fig.update_layout(title="Estoque médio por futuro: SOLARIS (x) × Stockpyl (y)", xaxis_title="SOLARIS (un.)",
                          yaxis_title="Stockpyl (un.)", **dict(LAYOUT, hovermode="closest"))
        st.plotly_chart(fig, width="stretch")
