# motor.py — lógica do SOLARIS (sem nenhum comando de tela).
# Leitura da base L'Oréal, cadastro de produtos, simulação de Monte Carlo, políticas de estoque,
# métricas, regra de escolha, plano mês a mês, gatilhos de S&OE, confirmação no Stockpyl e histórico.
# Separar "conta" de "tela" deixa o app fácil de testar no notebook e garante que todas as telas usam as mesmas regras.
from __future__ import annotations

import io
import json
import math
import os
import re
import unicodedata
import zlib
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# =====================================================================================================
# 0. Constantes e valores-padrão (os valores-padrão aparecem pré-preenchidos na barra lateral)
# =====================================================================================================
PASTA = Path(os.environ.get("SOLARIS_PASTA", "."))          # pasta do projeto (no Colab: Google Drive)
ARQUIVO_BASE = PASTA / "Triangulo Produtos V2.xlsx"           # base da L'Oréal
PASTA_HIST = PASTA / "historico"                               # rodadas salvas
ARQUIVO_PRODUTOS = PASTA / "produtos_cadastrados.json"        # produtos novos cadastrados
PASTA_DOCS = PASTA / "docs"                                    # PDFs para download na tela de início
ARQUIVOS_REFERENCIA = [PASTA / "solaris_resultados.json", PASTA / "resultados" / "solaris_resultados.json"]

DIAS_MES = 30
POLITICAS = ["P2", "P3", "P4", "P2L"]
NOME_POLITICA = {
    "P2": "P2 · Repor o previsto",
    "P3": "P3 · Previsto + reserva de segurança",
    "P4": "P4 · Reserva de segurança em lotes",
    "P2L": "P2 + lote · Repor o previsto em lotes",
    "PROG": "Plano programado (referência)",
    "P0": "P0 · O que aconteceu (estoque real)",
}
DESC_POLITICA = {
    "P2": "Todo mês produz a previsão até a produção chegar + a cobertura-alvo, descontando o estoque e o que já está a caminho. Sem reserva.",
    "P3": "Igual ao P2, mais uma reserva de segurança para o erro da previsão (z × σ).",
    "P4": "Igual ao P3, com a produção arredondada para múltiplos do lote mínimo.",
    "P2L": "Igual ao P2, com a produção arredondada para múltiplos do lote mínimo (sem reserva).",
}
DISTRIBUICOES = ["Erros reais (histórico)", "Normal", "Poisson"]
CHOQUES = ["Sem choque", "Com choque"]
PROTECAO_Z = {"95%": 1.645, "90%": 1.282, "85%": 1.036}

PADRAO = {
    "n_rep": 500, "protecao": "95%", "politicas": ["P2", "P3", "P4"],
    "distribuicoes": ["Erros reais (histórico)"], "choques": ["Sem choque"],
    # custos (visíveis na barra lateral)
    "custo_estoque_aa": 0.25, "custo_falta": 1.00, "custo_sobra": 0.30, "custo_excesso": 0.05,
    # avançado
    "regra_janela": "Assimétrica (validada)", "mes_decisao": True, "lt_producao": 1,
    "mult_incerteza": 1.0, "choque_inicio": 0.10, "choque_fim": 0.50,
    "meta_servico": 0.95, "meta_garantido": 0.90, "cob_min": 30, "cob_max": 180,
    "semente": 2026, "stockpyl": False, "n_rep_stockpyl": 50, "hbs": None,
}
# Gatilhos da Ação S&OE (edite aqui se a regra mudar)
GATILHO = {"risco_critico": 0.50, "risco_atencao": 0.25, "risco_excesso_atencao": 0.50, "desvio_atencao": 0.15,
           "tolerancia_manter": 0.05}

# Cores do semáforo e das políticas (mesmas em todas as telas)
CORES = {"Crítico": "#C0392B", "Atenção": "#D68910", "OK": "#1E8449", "—": "#7F8C8D"}
COR_POLITICA = {"P2": "#2a78d6", "P3": "#eb6834", "P4": "#1baf7a", "P2L": "#eda100", "PROG": "#8a8f98", "P0": "#8a8f98"}

_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
_MESES_PT = {m: i + 1 for i, m in enumerate(_MESES)}
_MES_RE = re.compile(r"^([a-zç]{3})/(\d{4})$")


# =====================================================================================================
# 1. Utilidades de formatação
# =====================================================================================================
def pct(v, casas=1):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{100 * v:.{casas}f}%".replace(".", ",")


def num(v, casas=0):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mi(v, casas=2):
    return "—" if v is None or not np.isfinite(v) else "R$ " + num(v / 1e6, casas) + " mi"


def norm_txt(s):
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def mes_label(v):
    """Converte 'ago/2025', datas do Excel, '2025-08' ou '08/2025' em 'ago/2025'."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return f"{_MESES[v.month - 1]}/{v.year}"
    s = str(v).strip().lower()
    m = _MES_RE.match(s)
    if m and m.group(1) in _MESES_PT:
        return s
    m = re.match(r"^(\d{4})[-/](\d{1,2})", s)
    if m:
        return f"{_MESES[int(m.group(2)) - 1]}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})[-/](\d{4})$", s)
    if m:
        return f"{_MESES[int(m.group(1)) - 1]}/{m.group(2)}"
    return None


def seq_meses(inicio, n):
    m = _MES_RE.match(mes_label(inicio) or "jan/2026")
    i0, ano = _MESES_PT[m.group(1)] - 1, int(m.group(2))
    return [f"{_MESES[(i0 + k) % 12]}/{ano + (i0 + k) // 12}" for k in range(n)]


def meses_para(semanas_ou_dias, unidade="dias"):
    """HB e LT em meses, sempre arredondando para cima (16 semanas → 4 meses; 60 dias → 2 meses)."""
    dias = float(semanas_ou_dias) * (7 if unidade == "semanas" else 1)
    return int(math.ceil(dias / DIAS_MES - 1e-9)) if dias > 0 else 0


# =====================================================================================================
# 2. Leitura da base L'Oréal (formato em triângulo) e curva de incerteza
# =====================================================================================================
def _eh_mes(x):
    return isinstance(x, str) and _MES_RE.match(x.strip().lower()) is not None


def _periodo(label):
    m = _MES_RE.match(label.strip().lower())
    return pd.Period(year=int(m.group(2)), month=_MESES_PT[m.group(1)], freq="M")


def _ler_aba_base(caminho):
    raw = pd.read_excel(caminho, sheet_name="Base", header=None)
    lin = next(i for i, r in raw.iterrows() if any(str(v).strip().upper() == "PRODUTO" for v in r.values))
    cab = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[lin].values]
    df = raw.iloc[lin + 1:].copy()
    df.columns = cab
    df = df.loc[:, [c for c in df.columns if c]].dropna(subset=["PRODUTO"])
    df = df.rename(columns={"PRODUTO": "product_id", "Origem Produção": "origem", "Cobertura Target (dias)": "cobertura_dias",
                            "HB (dias)": "hb_dias", "Maior LT de Insumo (in weeks)": "lt_insumo_semanas", "R$ PF": "preco",
                            "BENCHS": "benchmarks"})
    df["product_id"] = df["product_id"].apply(lambda v: str(int(v)) if isinstance(v, (int, float)) else str(v).strip())
    for c in ["cobertura_dias", "hb_dias", "lt_insumo_semanas", "preco"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["origem"] = df["origem"].astype(str).str.strip()
    return df.reset_index(drop=True)


def _ler_triangulo(caminho, aba):
    """Lê os três blocos (PV, plano de produção, estoque). Linha = versão do plano; coluna = mês-alvo."""
    raw = pd.read_excel(caminho, sheet_name=aba, header=None)
    blocos, cab, atual = {}, {}, None
    for _, r in raw.iterrows():
        a = r.iloc[0]
        if not isinstance(a, str):
            continue
        s = a.strip(); su = s.upper()
        if su.startswith("PV"):
            atual = "previsao"; blocos[atual] = []
        elif su.startswith("PLANO"):
            atual = "producao"; blocos[atual] = []
        elif su.startswith("ESTOQUE"):
            atual = "estoque"; blocos[atual] = []
        elif s == "Mes/Ano" and atual and _eh_mes(r.iloc[1]):
            cab[atual] = [str(x).strip().lower() for x in r.iloc[1:] if _eh_mes(x)]
        elif _eh_mes(s) and atual in cab:
            n = len(cab[atual])
            blocos[atual].append((s.lower(), pd.to_numeric(r.iloc[1:1 + n], errors="coerce").to_numpy(dtype=float)))
    return {k: pd.DataFrame([v for _, v in blocos[k]], index=[i for i, _ in blocos[k]], columns=cab[k])
            for k in ("previsao", "producao", "estoque")}


def inferir_lote(producao: pd.DataFrame, tol=0.02, fracao_min=0.80):
    """Lote = maior q tal que ≥ 80% das quantidades PLANEJADAS são múltiplos de q (tolerância 2%; mínimo 5 quantidades)."""
    cols, plan = list(producao.columns), []
    for v in producao.index:
        if v in cols:
            plan += [x for x in producao.loc[v].iloc[cols.index(v):].to_numpy() if np.isfinite(x) and x > 0]
    plan = np.array(plan, dtype=float)
    if len(plan) < 5:
        return 0
    melhor = 0
    for c in np.unique(np.round(plan))[:10]:
        r = plan / c
        if np.mean(np.abs(r - np.round(r)) <= tol * np.maximum(1, np.round(r))) >= fracao_min:
            melhor = max(melhor, int(round(c)))
    return melhor


def _matrizes(tri):
    """Matrizes alinhadas no tempo; células realizadas (à esquerda da diagonal) ficam vazias (sem vazamento)."""
    F, PP, INV = tri["previsao"], tri["producao"], tri["estoque"]
    alvos, versoes = list(F.columns), list(F.index)
    off = [_periodo(c) for c in alvos].index(_periodo(versoes[0]))
    alvos = alvos[off:]
    T = alvos.index(versoes[-1])
    nC = len(alvos)

    def mat(df):
        M = np.full((len(versoes), nC), np.nan)
        for r, v in enumerate(versoes):
            M[r, r:] = df.loc[v, alvos].to_numpy(dtype=float)[r:]
        return M

    return {"meses": alvos, "versoes": versoes, "T_real": T, "V": mat(F), "PP": mat(PP),
            "realizado": F.loc[versoes[-1], alvos[:T]].to_numpy(dtype=float),
            "producao_real": PP.loc[versoes[-1], alvos[:T]].to_numpy(dtype=float),
            "estoque_real": INV.loc[versoes[-1], alvos[:T]].to_numpy(dtype=float)}


def carregar_base(caminho=ARQUIVO_BASE):
    """Lê a base inteira: atributos, BOM e as abas PRODUTO n / BENCH X_n. Devolve séries, arquivo de erros e curva."""
    caminho = str(caminho)
    base = _ler_aba_base(caminho)
    bom = pd.read_excel(caminho, sheet_name="BOM")
    bom.columns = ["product_id", "material_id", "material_desc", "lt_semanas"]
    bom["product_id"] = bom["product_id"].apply(lambda v: str(int(v)) if isinstance(v, (int, float)) else str(v).strip())
    series = {}
    for aba in pd.ExcelFile(caminho).sheet_names:
        s = aba.strip().upper()
        mp, mb = re.match(r"^PRODUTO\s*(\d+)$", s), re.match(r"^BENCH\s*([A-Z]+)\s*_\s*(\d+)$", s)
        if not (mp or mb):
            continue
        sku, tipo, pid = (f"PRODUTO {mp.group(1)}", "produto", mp.group(1)) if mp else (f"BENCH {mb.group(1)}", "benchmark", mb.group(2))
        b = base.loc[base["product_id"] == pid].iloc[0]
        tri = _ler_triangulo(caminho, aba)
        m = _matrizes(tri)
        lt_bom = bom.loc[bom["product_id"] == pid, "lt_semanas"].max()
        series[sku] = {"sku": sku, "tipo": tipo, "product_id": pid, "origem": b["origem"],
                       "cobertura_dias": float(b["cobertura_dias"]), "hb_dias": float(b["hb_dias"]),
                       "lt_insumo_semanas": float(np.nanmax([b["lt_insumo_semanas"], lt_bom])),
                       "preco": float(b["preco"]), "lote": inferir_lote(tri["producao"]), **m}
    arquivo = arquivo_erros(series)
    return {"series": series, "arquivo": arquivo, "curva": curva_incerteza(arquivo)}


def arquivo_erros(series, excluir=None, max_h=12):
    """Erros de previsão dos benchmarks (lançamentos com realizado conhecido): um registro por versão × mês-alvo."""
    linhas = []
    for sku, s in series.items():
        if s["tipo"] != "benchmark" or sku == excluir:
            continue
        V, A = s["V"], s["realizado"]
        for r in range(min(V.shape[0], len(A))):
            for c in range(r, len(A)):
                f, a = V[r, c], A[c]
                if not np.isfinite(f) or (f == 0 and a == 0) or c - r > max_h:
                    continue
                linhas.append({"sku": sku, "versao": r, "alvo": c, "h": c - r, "previsao": f, "realizado": a,
                               "erro": a - f, "erro_rel": (a - f) / f if f > 0 else np.nan})
    return pd.DataFrame(linhas)


def curva_incerteza(arq):
    """CV do erro por horizonte = desvio-padrão do erro ÷ previsão média (interpolado, limitado a [0,01; 1])."""
    g = arq.groupby("h").agg(prev_media=("previsao", "mean"), erro_dp=("erro", "std"), n=("erro", "size"))
    g["cv"] = (g["erro_dp"] / g["prev_media"].replace(0, np.nan)).interpolate().bfill().ffill().clip(0.01, 1.0)
    return g.reset_index()[["h", "cv", "n"]]


def cv_por_horizonte(curva, n):
    tab = dict(zip(curva["h"].astype(int), curva["cv"]))
    ult = float(curva.sort_values("h")["cv"].iloc[-1])
    return np.array([tab.get(h, ult) for h in range(n + 1)])


def pools_erros(arq):
    """Erros relativos reais: por horizonte (sorteio independente) e trajetórias inteiras (mantém a persistência do erro)."""
    a = arq.dropna(subset=["erro_rel"])
    por_h = {int(h): g["erro_rel"].clip(-0.95, 3.0).to_numpy() for h, g in a.groupby("h")}
    traj = []
    for (_, _), g in a.groupby(["sku", "versao"]):
        v = np.full(13, np.nan)
        for h, e in zip(g["h"], g["erro_rel"].clip(-0.95, 3.0)):
            if h <= 12:
                v[int(h)] = e
        if np.isfinite(v).sum() >= 3:
            traj.append(v)
    return por_h, traj


# =====================================================================================================
# 3. Produtos: da base (escolhendo a versão da previsão) ou cadastrados pelo usuário
# =====================================================================================================
CAMPOS = ["nome", "origem", "cobertura_dias", "hb_dias", "lt_insumo_semanas", "preco", "lote", "estoque_inicial"]


def produto_da_base(serie, versao_idx=0):
    """Monta o produto a partir de uma versão do triângulo: previsão e plano dessa versão, estoque real anterior."""
    r = int(versao_idx)
    V, PP = serie["V"], serie["PP"]
    prev, prog = np.nan_to_num(V[r, r:]), np.nan_to_num(PP[r, r:])
    meses = serie["meses"][r:]
    k = len(prev)
    while k > 1 and prev[k - 1] == 0 and prog[k - 1] == 0:
        k -= 1
    est = float(serie["estoque_real"][r - 1]) if 0 < r <= len(serie["estoque_real"]) else 0.0
    return {"id": f"base::{serie['sku']}::{r}", "nome": f"{serie['sku']} (versão {serie['versoes'][r]})", "fonte": "base",
            "sku_base": serie["sku"], "versao": r, "origem": serie["origem"], "cobertura_dias": serie["cobertura_dias"],
            "hb_dias": serie["hb_dias"], "lt_insumo_semanas": serie["lt_insumo_semanas"], "preco": serie["preco"],
            "lote": int(serie["lote"]), "estoque_inicial": max(est, 0.0), "meses": meses[:k],
            "previsao": [float(x) for x in prev[:k]], "programada": [float(x) for x in prog[:k]]}


def versoes_validas(serie):
    """Versões com pelo menos 2 meses de previsão positiva (antes disso o lançamento ainda não tinha previsão)."""
    return [i for i in range(len(serie["versoes"])) if np.sum(np.nan_to_num(serie["V"][i, i:]) > 0) >= 2]


def produto_novo(nome="Novo produto", inicio="jan/2027", n=12):
    return {"id": f"novo::{nome}", "nome": nome, "fonte": "novo", "origem": "Interno", "cobertura_dias": 60, "hb_dias": 30,
            "lt_insumo_semanas": 8, "preco": 20.0, "lote": 0, "estoque_inicial": 0.0, "meses": seq_meses(inicio, n),
            "previsao": [0.0] * n, "programada": [0.0] * n}


def validar_produto(p):
    erros = []
    if not str(p.get("nome", "")).strip():
        erros.append("Informe o nome do produto.")
    if sum(1 for x in p["previsao"] if x > 0) < 2:
        erros.append("Informe pelo menos 2 meses com previsão de vendas positiva.")
    if float(p["preco"]) <= 0:
        erros.append("Informe o preço (R$ PF) maior que zero.")
    if len(p["meses"]) != len(p["previsao"]) or len(p["previsao"]) != len(p["programada"]):
        erros.append("Meses, previsão e produção programada precisam ter o mesmo tamanho.")
    return erros


def carregar_cadastrados():
    try:
        return json.loads(ARQUIVO_PRODUTOS.read_text(encoding="utf-8"))
    except Exception:
        return []


def salvar_cadastrados(lista):
    ARQUIVO_PRODUTOS.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_PRODUTOS.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")


COLS_ATR = ["Produto", "Origem (Interno/Terceiro)", "Cobertura-alvo (dias)", "HB (dias)", "Maior LT de insumo (semanas)",
            "R$ PF (preço por unidade)", "Lote (un.; 0 = sem lote)", "Estoque atual (un.)"]
COLS_PREV = ["Produto", "Mês (mmm/aaaa)", "Previsão (un.)", "Produção programada (un.)"]


def planilha_modelo(produtos=None):
    """Planilha modelo de importação (abas Instrucoes, Atributos, Previsoes), em bytes para download."""
    produtos = produtos or []
    instr = pd.DataFrame({"Como preencher": [
        "1. Aba Atributos: uma linha por produto. Não mude os títulos das colunas.",
        "2. Aba Previsoes: uma linha por produto e por mês: previsão de vendas e produção programada para chegar no mês.",
        "3. O nome do produto deve ser igual nas duas abas. Meses no formato mmm/aaaa (ex.: ago/2025) ou data do Excel.",
        "4. Comece pelo mês atual e informe meses suficientes para cobrir a janela de reação + a cobertura-alvo.",
        "5. Origem: Interno ou Terceiro. HB em dias (30 ou 60). LT de insumo em semanas.",
        "6. Na ferramenta: Cadastro → Subir planilha. Produtos com o mesmo nome são atualizados."]})
    atr = pd.DataFrame([[p["nome"], p["origem"], p["cobertura_dias"], p["hb_dias"], p["lt_insumo_semanas"], p["preco"],
                         p["lote"], p["estoque_inicial"]] for p in produtos], columns=COLS_ATR)
    prev = pd.DataFrame([[p["nome"], m, f, g] for p in produtos for m, f, g in zip(p["meses"], p["previsao"], p["programada"])],
                        columns=COLS_PREV)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        instr.to_excel(w, sheet_name="Instrucoes", index=False)
        atr.to_excel(w, sheet_name="Atributos", index=False)
        prev.to_excel(w, sheet_name="Previsoes", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 26 if ws.title != "Instrucoes" else 110
    return buf.getvalue()


def ler_planilha_produtos(arquivo):
    """Lê a planilha modelo (ou uma parecida). Devolve (lista de produtos, avisos)."""
    abas = pd.read_excel(arquivo, sheet_name=None)
    nome_aba = lambda chaves: next((n for n in abas if any(k in norm_txt(n) for k in chaves)), None)
    a_atr, a_prev = nome_aba(["atribut", "attr"]), nome_aba(["previs", "forecast", "demanda"])
    if not a_atr or not a_prev:
        return [], ["Não encontrei as abas 'Atributos' e 'Previsoes'. Use a planilha modelo."]
    A, P = abas[a_atr], abas[a_prev]
    col = lambda df, testes: next((c for c in df.columns if any(t(norm_txt(c)) for t in testes)), None)
    ca = {"nome": col(A, [lambda h: h.startswith("produto"), lambda h: h in ("nome", "sku")]),
          "origem": col(A, [lambda h: h.startswith("origem")]), "cob": col(A, [lambda h: "cobertura" in h]),
          "hb": col(A, [lambda h: h.startswith("hb")]), "lt": col(A, [lambda h: "insumo" in h or h.startswith("lt")]),
          "preco": col(A, [lambda h: "pf" in h or "preco" in h]), "lote": col(A, [lambda h: h.startswith("lote")]),
          "est": col(A, [lambda h: "estoque" in h])}
    cp = {"nome": col(P, [lambda h: h.startswith("produto"), lambda h: h in ("nome", "sku")]),
          "mes": col(P, [lambda h: h.startswith("mes") or h.startswith("data")]),
          "prev": col(P, [lambda h: h.startswith("previs") or "demanda" in h]),
          "prog": col(P, [lambda h: "program" in h or h.startswith("producao")])}
    if not ca["nome"] or not cp["nome"] or not cp["mes"] or not cp["prev"]:
        return [], ["Colunas obrigatórias não encontradas (Produto, Mês, Previsão)."]
    avisos, produtos = [], []
    numf = lambda v, d=0.0: float(pd.to_numeric(v, errors="coerce")) if pd.notna(pd.to_numeric(v, errors="coerce")) else d
    for _, r in A.iterrows():
        nome = str(r[ca["nome"]]).strip()
        if not nome or nome.lower() == "nan":
            continue
        sub = P[P[cp["nome"]].astype(str).str.strip() == nome].copy()
        sub["_m"] = sub[cp["mes"]].apply(mes_label)
        if sub["_m"].isna().any():
            avisos.append(f"{nome}: há meses em formato inválido (ignorados).")
        sub = sub.dropna(subset=["_m"])
        sub["_p"] = sub["_m"].apply(_periodo)
        sub = sub.sort_values("_p")
        if sub.empty:
            avisos.append(f"{nome}: sem linhas na aba Previsoes.")
            continue
        orig = norm_txt(r[ca["origem"]]) if ca["origem"] else "interno"
        produtos.append({"id": f"novo::{nome}", "nome": nome, "fonte": "novo",
                         "origem": "Terceiro" if orig.startswith("terc") else "Interno",
                         "cobertura_dias": numf(r[ca["cob"]], 60) if ca["cob"] else 60,
                         "hb_dias": numf(r[ca["hb"]], 30) if ca["hb"] else 30,
                         "lt_insumo_semanas": numf(r[ca["lt"]], 0) if ca["lt"] else 0,
                         "preco": numf(r[ca["preco"]], 0) if ca["preco"] else 0,
                         "lote": int(numf(r[ca["lote"]], 0)) if ca["lote"] else 0,
                         "estoque_inicial": numf(r[ca["est"]], 0) if ca["est"] else 0,
                         "meses": list(sub["_m"]), "previsao": [numf(x) for x in sub[cp["prev"]]],
                         "programada": [numf(x) for x in sub[cp["prog"]]] if cp["prog"] else [0.0] * len(sub)})
    return produtos, avisos


# =====================================================================================================
# 4. Janela de reação
# =====================================================================================================
def janelas(prod, par):
    """Devolve (janela para AUMENTAR, janela para REDUZIR), em meses.
    Assimétrica (validada): aumentar = max(HB, LT de insumo) + LT de produção + mês de decisão;
                            reduzir  = HB + mês de decisão (não depende de insumo nem de produção).
    Simples (experimento anterior): max(HB, LT de produção) nos dois sentidos."""
    hb = meses_para(prod["hb_dias"], "dias")
    lt = meses_para(prod["lt_insumo_semanas"], "semanas")
    d = 1 if par["mes_decisao"] else 0
    if par["regra_janela"].startswith("Assim"):
        up, down = max(hb, lt) + int(par["lt_producao"]) + d, hb + d
    else:
        up = down = max(hb, int(par["lt_producao"]), 1)
    down = max(1, down)
    return max(up, down), down


# =====================================================================================================
# 5. Cenários de Monte Carlo: demanda, previsão revisada mês a mês e choque de fornecimento
# =====================================================================================================
def gerar_cenarios(prev, dist, R, rng, cv, por_h, traj, mult, choque, p_ini, p_fim):
    """Gera R futuros possíveis. Cada futuro tem:
       D[r, j]     demanda que acontece no mês j;
       Vr[r, t, j] previsão que o planejador tem no mês t para o mês j (revisada a cada mês; Vr[:,0,:] = previsão cadastrada);
       S[r, j]     True se o mês j está em choque (recebimento retido)."""
    F = np.asarray(prev, float)
    n = len(F)
    hmax = lambda h: min(int(h), 12)
    if dist.startswith("Erros"):
        E = np.empty((R, n))
        for r in range(R):
            tr = traj[rng.integers(len(traj))] if traj else np.full(13, np.nan)
            for j in range(n):
                e = tr[hmax(j)]
                if not np.isfinite(e):
                    pool = por_h.get(hmax(j)) if por_h.get(hmax(j)) is not None else np.concatenate(list(por_h.values()))
                    e = pool[rng.integers(len(pool))]
                E[r, j] = e
        D = np.clip(F * (1 + mult * E), 0, None)
    elif dist == "Normal":
        D = np.clip(F * (1 + rng.normal(0, 1, (R, n)) * mult * cv[:n]), 0, None)
    else:  # Poisson
        D = rng.poisson(np.clip(F, 0, None), (R, n)).astype(float)
    Vr = np.zeros((R, n, n))
    Vr[:, 0, :] = F
    for t in range(1, n):
        for j in range(t + 1, n):
            h = j - t
            if dist.startswith("Erros"):
                pool = por_h.get(hmax(h)) if por_h.get(hmax(h)) is not None else np.concatenate(list(por_h.values()))
                e = pool[rng.integers(len(pool), size=R)] * mult
                Vr[:, t, j] = D[:, j] / np.clip(1 + e, 0.2, None)
            elif dist == "Normal":
                Vr[:, t, j] = np.clip(D[:, j] * (1 + rng.normal(0, 1, R) * mult * cv[h]), 0, None)
            else:
                Vr[:, t, j] = np.clip(D[:, j] + rng.normal(0, 1, R) * np.sqrt(np.maximum(D[:, j], 1)), 0, None)
        Vr[:, t, F == 0] = 0.0          # meses sem previsão continuam sem previsão
    S = np.zeros((R, n), bool)
    if choque == "Com choque":
        estado = np.zeros(R, bool)
        for j in range(n):
            u = rng.random(R)
            estado = np.where(estado, u >= p_fim, u < p_ini)
            S[:, j] = estado
    return D, Vr, S


# =====================================================================================================
# 6. Simulador do SOLARIS (vetorizado nas R repetições) — política, falta como pendência, métricas
# =====================================================================================================
def _cobertura(estoque, Vt, t, n, cob_max):
    """Cobertura para frente (dias): quantos dias o estoque dura consumindo a previsão dos meses seguintes.
    Se a previsão acabar antes do estoque: > cob_max quando o horizonte restante já passa de cob_max; senão indefinida."""
    R = len(estoque)
    cov = np.full(R, np.nan)
    resto = estoque.copy()
    dias = np.zeros(R)
    aberto = np.ones(R, bool)
    for k in range(t + 1, n):
        f = Vt[:, k]
        consome = np.minimum(resto, f)
        acaba = aberto & (resto < f) & (f > 0)
        cov[acaba] = dias[acaba] + DIAS_MES * (resto[acaba] / f[acaba])
        aberto &= ~acaba
        resto = resto - consome
        dias = dias + DIAS_MES
    sobra = aberto & (dias >= cob_max)
    cov[sobra] = dias[sobra] + 1          # dura mais que o horizonte e que o limite de excesso
    return cov


def _excesso_unidades(estoque, Vt, t, n, cob_max):
    k = int(round(cob_max / DIAS_MES))
    if t + k >= n:
        return np.zeros(len(estoque))
    return np.maximum(0.0, estoque - Vt[:, t + 1:t + 1 + k].sum(axis=1))


def simular(prod, pol, D, Vr, S, par, cv, z):
    """Executa a política em todos os futuros de uma vez. Devolve métricas por repetição e por mês."""
    R, n = D.shape
    F = np.asarray(prod["previsao"], float)
    prog = np.asarray(prod["programada"], float)
    up, down = janelas(prod, par)
    lote = int(prod.get("lote") or 0)
    usa_lote = pol in ("P4", "P2L") and lote > 0
    zz = z if pol in ("P3", "P4") else 0.0
    c = float(prod["cobertura_dias"]) / DIAS_MES
    inteiro, frac = int(math.floor(c)), c - math.floor(c)
    n_prot = max(up + int(math.ceil(c)), up + 1)
    preco = float(prod["preco"])
    h_un, b_un = par["custo_estoque_aa"] / 12 * preco, par["custo_falta"] * preco
    L = n + up + 2
    arr = np.zeros((R, L))
    kp = int(np.nonzero(prog > 0)[0].max()) if (prog > 0).any() else -1      # último mês com produção programada
    if pol == "PROG":
        # Plano programado: segue exatamente o programado até o último mês com plano; depois disso continua repondo
        # o previsto (P2), porque o plano ainda não foi feito para esses meses.
        arr[:, :kp + 1] = prog[:kp + 1]
    else:
        arr[:, :min(up, n)] = prog[:min(up, n)]          # o que já está programado dentro da janela de aumento
    IL = np.full(R, float(prod["estoque_inicial"]))
    retido = np.zeros(R)
    out = {k: np.zeros((R, n)) for k in ["atendido", "estoque", "pendente", "cob", "ss", "excesso", "pedido", "corte", "recebido"]}
    cvw = cv[1:n_prot + 1] * par["mult_incerteza"] if len(cv) > n_prot else np.resize(cv[1:], n_prot) * par["mult_incerteza"]
    for t in range(n):
        # 1) recebimento (com choque, o que chega fica retido até o choque terminar)
        chega = arr[:, t]
        retido = retido + np.where(S[:, t], chega, 0.0)
        receb = np.where(S[:, t], 0.0, chega + retido)
        retido = np.where(S[:, t], retido, 0.0)
        # 2) demanda: atende com o estoque disponível; o resto vira pendência
        disp = IL + receb
        atend = np.minimum(D[:, t], np.maximum(disp, 0.0))
        IL = disp - D[:, t]
        Vt = Vr[:, t, :] if t > 0 else np.broadcast_to(F, (R, n))
        ss = np.zeros(R)
        if pol != "PROG" or t + up > kp:
            # 3) nível-alvo com a previsão vigente: até a produção chegar + cobertura-alvo (+ reserva)
            def janela(a, k):
                b = min(n, a + k)
                return Vt[:, a:b].sum(axis=1) if b > a else np.zeros(R)
            pre = janela(t + 1, up)
            cob = janela(t + 1 + up, inteiro)
            j_f = t + 1 + up + inteiro
            if frac > 1e-9 and j_f < n:
                cob = cob + frac * Vt[:, j_f]
            if zz > 0:
                b = min(n, t + 1 + n_prot)
                fut = Vt[:, t + 1:b]
                sig = np.sqrt(fut.sum(axis=1)) if par["_dist"] == "Poisson" else np.sqrt(((fut * cvw[:fut.shape[1]]) ** 2).sum(axis=1))
                ss = zz * sig
            alvo = pre + cob + ss
            pos = IL + retido + arr[:, t + 1:].sum(axis=1)          # posição de estoque
            q = np.maximum(0.0, alvo - pos)
            if usa_lote:
                q = np.ceil(q / lote - 1e-9) * lote
            if t + up < L:
                arr[:, t + up] += q
            out["pedido"][:, t] = q
        if pol != "PROG":
            # 4) redução: o que está planejado fora da janela de redução pode ser cortado (em lotes inteiros, se houver lote)
            exc = np.maximum(0.0, pos - alvo)
            cortado = np.zeros(R)
            for m in range(min(t + up - 1, L - 1), t + down - 1, -1):
                corte = np.minimum(arr[:, m], exc)
                if usa_lote:
                    corte = np.floor(corte / lote + 1e-9) * lote
                arr[:, m] -= corte
                exc -= corte
                cortado += corte
            out["corte"][:, t] = cortado
        est = np.maximum(IL, 0.0)
        out["atendido"][:, t] = atend
        out["estoque"][:, t] = est
        out["pendente"][:, t] = np.maximum(-IL, 0.0)
        out["ss"][:, t] = ss
        out["recebido"][:, t] = receb
        out["cob"][:, t] = _cobertura(est, Vt, t, n, par["cob_max"])
        out["excesso"][:, t] = _excesso_unidades(est, Vt, t, n, par["cob_max"])
    out["chegada_final"] = arr[:, :n].copy()
    return metricas(out, D, F, prod, par, h_un, b_un, preco)


def metricas(out, D, F, prod, par, h_un, b_un, preco):
    """Métricas por repetição. Meses sem previsão de venda ficam fora das métricas de avaliação."""
    aval = np.asarray(par["_aval"], bool) if par.get("_aval") is not None else F > 0
    Da, Aa = D[:, aval], out["atendido"][:, aval]
    tot = Da.sum(axis=1)
    falta_mes = (Aa < Da - 1e-6) & (Da > 0)
    cov = out["cob"][:, aval]
    defin = np.isfinite(cov)
    with np.errstate(invalid="ignore", divide="ignore"):
        sub = np.where(defin.sum(axis=1) > 0, ((cov < par["cob_min"]) & defin).sum(axis=1) / np.maximum(defin.sum(axis=1), 1), 0.0)
        sobre = np.where(defin.sum(axis=1) > 0, ((cov > par["cob_max"]) & defin).sum(axis=1) / np.maximum(defin.sum(axis=1), 1), 0.0)
    custo_est = (out["estoque"] * h_un).sum(axis=1)
    custo_falta = (out["pendente"] * b_un).sum(axis=1)
    custo_sobra = out["estoque"][:, -1] * par["custo_sobra"] * preco
    custo_exc = (out["excesso"] * par["custo_excesso"] * preco).sum(axis=1)
    rep = pd.DataFrame({
        "nivel_servico": np.where(tot > 0, Aa.sum(axis=1) / np.maximum(tot, 1e-9), 1.0),
        "meses_falta": falta_mes.mean(axis=1) if aval.any() else 0.0,
        "meses_cob_baixa": sub, "meses_excesso": sobre,
        "estoque_medio": out["estoque"][:, aval].mean(axis=1) if aval.any() else 0.0,
        "estoque_final": out["estoque"][:, -1], "reserva_media": out["ss"][:, aval].mean(axis=1) if aval.any() else 0.0,
        "custo_estoque": custo_est, "custo_falta": custo_falta, "custo_sobra": custo_sobra, "custo_excesso": custo_exc,
        "custo_total": custo_est + custo_falta + custo_sobra + custo_exc,
        "pedidos": (out["pedido"] > 0).sum(axis=1), "unidades_cortadas": out["corte"].sum(axis=1)})
    mensal = pd.DataFrame({
        "estoque_p5": np.percentile(out["estoque"], 5, axis=0), "estoque_p50": np.percentile(out["estoque"], 50, axis=0),
        "estoque_p95": np.percentile(out["estoque"], 95, axis=0),
        "prob_falta": ((out["atendido"] < D - 1e-6) & (D > 0)).mean(axis=0),
        # cobertura indefinida (a previsão acaba antes do estoque e o horizonte restante é curto) em mais da metade dos
        # futuros → probabilidade não calculada (NaN), para não mostrar "0% de excesso" no fim do horizonte
        "prob_excesso": np.where(np.isfinite(out["cob"]).mean(axis=0) >= 0.5,
                                 (np.nan_to_num(out["cob"], nan=0) > par["cob_max"]).sum(axis=0) / np.maximum(np.isfinite(out["cob"]).sum(axis=0), 1), np.nan),
        "prob_cob_baixa": np.where(np.isfinite(out["cob"]).mean(axis=0) >= 0.5,
                                   ((out["cob"] < par["cob_min"]) & np.isfinite(out["cob"])).sum(axis=0) / np.maximum(np.isfinite(out["cob"]).sum(axis=0), 1), np.nan),
        "chegada_media": out["chegada_final"].mean(axis=0), "demanda_media": D.mean(axis=0)})
    return {"rep": rep, "mensal": mensal, "_bruto": out}


# =====================================================================================================
# 7. Rodada completa: cenários de sensibilidade (distribuição × choque × HB) × políticas × repetições
# =====================================================================================================
def _semente(base, *partes):
    return int(base) + zlib.crc32("|".join(map(str, partes)).encode()) % 1_000_000 * 10


def nome_cenario(dist, choque, hb):
    return f"{dist} · {choque} · HB {int(hb)} dias"


def rodar(prod, par, base_dados, progresso=None):
    """Roda o Monte Carlo para o produto em todos os cenários escolhidos. Devolve um dicionário com tudo."""
    n = len(prod["previsao"])
    excluir = prod.get("sku_base") if prod.get("fonte") == "base" else None
    # deixa-um-fora: um benchmark não calibra o próprio erro
    arq = arquivo_erros(base_dados["series"], excluir=excluir) if excluir and excluir.startswith("BENCH") else base_dados["arquivo"]
    curva = curva_incerteza(arq)
    cv = cv_por_horizonte(curva, n + 40)
    por_h, traj = pools_erros(arq)
    z = PROTECAO_Z[par["protecao"]]
    pols = [p for p in par["politicas"] if p != "P2L" or int(prod.get("lote") or 0) > 0]
    tem_prog = sum(prod["programada"]) > 0
    hbs = par.get("hbs") or [prod["hb_dias"]]
    cen_def = {}
    for d in par["distribuicoes"]:
        for c in par["choques"]:
            for hb in hbs:
                p_hb = dict(prod, hb_dias=float(hb))
                up, down = janelas(p_hb, par)
                cen_def[nome_cenario(d, c, hb)] = {"distribuicao": d, "choque": c, "hb_dias": float(hb),
                                                    "janela_aumento": up, "janela_reducao": down}
    resumo, reps, mensal, brutos = [], [], {}, {}
    total, feito = len(cen_def) * (len(pols) + tem_prog), 0
    for cen, cd in cen_def.items():
        d, c = cd["distribuicao"], cd["choque"]
        # mesmos futuros (números aleatórios comuns) para todas as políticas e para os dois HB
        rng = np.random.default_rng(_semente(par["semente"], prod["nome"], d, c))
        D, Vr, S = gerar_cenarios(prod["previsao"], d, int(par["n_rep"]), rng, cv, por_h, traj, par["mult_incerteza"],
                                  c, par["choque_inicio"], par["choque_fim"])
        p_hb = dict(prod, hb_dias=cd["hb_dias"])
        p2 = dict(par, _dist=d)
        for pol in pols + (["PROG"] if tem_prog else []):
            res = simular(p_hb, pol, D, Vr, S, p2, cv, z)
            r = res["rep"]
            reps.append(r.assign(cenario=cen, politica=pol, repeticao=np.arange(len(r))))
            mensal[(cen, pol)] = res["mensal"]
            brutos[(cen, pol)] = res["_bruto"]
            resumo.append({"cenario": cen, "distribuicao": d, "choque": c, "hb_dias": cd["hb_dias"], "politica": pol,
                           "nivel_servico": r["nivel_servico"].mean(), "nivel_garantido": r["nivel_servico"].quantile(0.05),
                           "meses_falta": r["meses_falta"].mean(), "meses_cob_baixa": r["meses_cob_baixa"].mean(),
                           "meses_excesso": r["meses_excesso"].mean(), "estoque_medio": r["estoque_medio"].mean(),
                           "estoque_final": r["estoque_final"].mean(), "reserva_media": r["reserva_media"].mean(),
                           "custo_estoque": r["custo_estoque"].mean(), "custo_falta": r["custo_falta"].mean(),
                           "custo_sobra": r["custo_sobra"].mean(), "custo_excesso": r["custo_excesso"].mean(),
                           "custo_total": r["custo_total"].mean(), "custo_p95": r["custo_total"].quantile(0.95),
                           "unidades_cortadas": r["unidades_cortadas"].mean()})
            feito += 1
            if progresso:
                progresso(feito / total, f"{cen} · {NOME_POLITICA[pol]}")
        brutos[(cen, "_cen")] = {"D": D, "S": S}
    resumo = pd.DataFrame(resumo)
    resumo["cumpre_metas"] = (resumo["nivel_servico"] >= par["meta_servico"]) & (resumo["nivel_garantido"] >= par["meta_garantido"])
    agora = datetime.now()
    return {"id": agora.strftime("%Y%m%d_%H%M%S"), "data": agora.strftime("%d/%m/%Y %H:%M"),
            "produto": prod, "parametros": {k: v for k, v in par.items() if not k.startswith("_")},
            "cenarios": cen_def, "z": z, "curva": curva.to_dict("list"), "resumo": resumo,
            "melhor": escolher(resumo, prod), "repeticoes": pd.concat(reps, ignore_index=True),
            "mensal": mensal, "_brutos": brutos, "stockpyl": None}


def escolher(resumo, prod):
    """Regra de escolha: entre as políticas que cumprem as metas, a de menor custo; se nenhuma cumpre, a de maior nível garantido.
    Com lote mínimo, a execução usa a versão em lotes (P2 → P2 + lote; P3 → P4)."""
    linhas = []
    for cen, g in resumo[resumo["politica"] != "PROG"].groupby("cenario", sort=False):
        ok = g[g["cumpre_metas"]]
        b = ok.sort_values("custo_total").iloc[0] if len(ok) else g.sort_values(["nivel_garantido", "custo_total"], ascending=[False, True]).iloc[0]
        impl = b["politica"]
        if int(prod.get("lote") or 0) > 0:
            impl = {"P2": "P2L", "P3": "P4"}.get(impl, impl)
        if impl not in set(g["politica"]):
            impl = b["politica"]
        p2 = g[g["politica"] == "P2"]
        prog = resumo[(resumo["cenario"] == cen) & (resumo["politica"] == "PROG")]
        linhas.append({"cenario": cen, "distribuicao": b["distribuicao"], "choque": b["choque"], "hb_dias": b["hb_dias"],
                       "politica": b["politica"], "como_executar": impl,
                       "cumpre_metas": bool(len(ok)), "nivel_servico": b["nivel_servico"], "nivel_garantido": b["nivel_garantido"],
                       "meses_falta": b["meses_falta"], "meses_excesso": b["meses_excesso"], "custo_total": b["custo_total"],
                       "custo_vs_P2": (b["custo_total"] / p2["custo_total"].iloc[0] - 1) if len(p2) else np.nan,
                       "custo_vs_programado": (b["custo_total"] / prog["custo_total"].iloc[0] - 1) if len(prog) else np.nan,
                       "motivo": "menor custo entre as que cumprem as metas" if len(ok) else
                                 "nenhuma cumpre as metas: maior nível garantido (levar ao S&OP)"})
    return pd.DataFrame(linhas)


# =====================================================================================================
# 8. Plano mês a mês e gatilhos de S&OE
# =====================================================================================================
def plano_deterministico(prod, pol, par, z, curva_cv):
    """Plano usando a previsão cadastrada como se fosse se confirmar (1 futuro, sem revisão, sem choque)."""
    F = np.asarray(prod["previsao"], float)
    n = len(F)
    D, S = F[None, :].copy(), np.zeros((1, n), bool)
    Vr = np.broadcast_to(F, (1, n, n)).copy()
    res = simular(prod, pol, D, Vr, S, dict(par, _dist="Normal"), curva_cv, z)
    return res["_bruto"]


TEXTO_ACAO = {
    "congelado_crit": "Dentro do horizonte congelado: não alterar a produção; acelerar entregas, realocar estoque e priorizar canais.",
    "congelado": "Dentro do horizonte congelado: acompanhar a execução; não mudar o plano sem exceção confirmada.",
    "aumento_tarde": "Só dá para reduzir neste mês (aumento fora do prazo de insumo/produção): buscar alternativas — antecipar "
                     "produção de outro mês, compra urgente de insumo, realocação entre canais.",
    "curto_up": "Curto prazo: aumentar ou antecipar produção, confirmar lote, garantir insumos críticos e capacidade.",
    "curto_down": "Curto prazo: adiar ou reduzir produção, suspender compras de insumo evitáveis e checar risco de E&O.",
    "curto_ok": "Curto prazo: manter o plano e revisar o próximo slot de produção e os compromissos de insumo.",
    "tatico_up": "Tático: rebalancear capacidade, antecipar componentes críticos e atualizar o cenário de alta no S&OP.",
    "tatico_down": "Tático: cancelar ou adiar insumos reversíveis, reduzir lotes futuros e atualizar o cenário de baixa / E&O.",
    "tatico_ok": "Tático: preservar flexibilidade; atualizar premissas do cenário e compromissos com fornecedores.",
    "medio": "Médio prazo: revisar premissas do lançamento, metas de S&OP e parâmetros da política; sem intervenção emergencial.",
}


def plano_e_acoes(resultado, cen, pol):
    """Tabela mês a mês: plano recomendado × programado, prazos, riscos (dos futuros simulados) e gatilho."""
    cd = resultado["cenarios"][cen]
    prod = dict(resultado["produto"], hb_dias=cd["hb_dias"])
    par, z = resultado["parametros"], resultado["z"]
    up, down = cd["janela_aumento"], cd["janela_reducao"]
    cv = cv_por_horizonte(pd.DataFrame(resultado["curva"]), len(prod["previsao"]) + 40)
    F = np.asarray(prod["previsao"], float)
    prog = np.asarray(prod["programada"], float)
    n, meses, lote = len(F), prod["meses"], int(prod.get("lote") or 0)
    rec = plano_deterministico(prod, pol, par, z, cv)
    proj = plano_deterministico(prod, "PROG", par, z, cv)
    risco = resultado["mensal"].get((cen, "PROG"))
    if risco is None:
        risco = resultado["mensal"].get((cen, pol))
    media = F[F > 0].mean() if (F > 0).any() else 0
    linhas = []
    for m in range(n):
        r_ch, p = rec["chegada_final"][0, m], prog[m]
        est_prog, pend_prog = proj["estoque"][0, m], proj["pendente"][0, m]
        cob_prog = proj["cob"][0, m]
        rf = float(risco["prob_falta"].iloc[m]) if risco is not None else np.nan
        rx = float(risco["prob_excesso"].iloc[m]) if risco is not None else np.nan
        dif = r_ch - p
        tol = max(GATILHO["tolerancia_manter"] * max(p, r_ch), lote * 0.5, 0.02 * media)
        if m < down:
            acao, dirc = "Congelado", "0"
        elif dif > tol:
            acao, dirc = ("Produzir mais", "up") if m >= up else ("Aumento fora do prazo", "up_late")
        elif dif < -tol:
            acao, dirc = "Reduzir", "down"
        else:
            acao, dirc = "Manter", "0"
        # gatilho (previsão de vendas = 0 → nenhum gatilho)
        motivos, sev = [], "OK"
        if F[m] <= 0:
            sev = "—"
        else:
            if pend_prog > 0:
                motivos.append("falta projetada com o plano programado")
            if np.isfinite(cob_prog) and cob_prog < par["cob_min"]:
                motivos.append(f"cobertura abaixo de {par['cob_min']} dias")
            if np.isfinite(rf) and rf >= GATILHO["risco_critico"]:
                motivos.append(f"risco de falta ≥ {int(100 * GATILHO['risco_critico'])}%")
            if motivos:
                sev = "Crítico"
            else:
                if np.isfinite(rf) and rf >= GATILHO["risco_atencao"]:
                    motivos.append(f"risco de falta entre {int(100 * GATILHO['risco_atencao'])}% e {int(100 * GATILHO['risco_critico'])}%")
                if (np.isfinite(cob_prog) and cob_prog > par["cob_max"]) or (np.isfinite(rx) and rx >= GATILHO["risco_excesso_atencao"]):
                    motivos.append(f"risco de excesso (cobertura > {par['cob_max']} dias)")
                if m >= down and acao != "Manter" and abs(dif) > GATILHO["desvio_atencao"] * max(p, 1):
                    motivos.append(f"programado difere {int(100 * GATILHO['desvio_atencao'])}% ou mais do recomendado")
                if motivos:
                    sev = "Atenção"
        if m < down:
            txt = TEXTO_ACAO["congelado_crit" if sev == "Crítico" else "congelado"]
        elif dirc == "up_late" or (m < up and sev == "Crítico"):
            txt = TEXTO_ACAO["aumento_tarde"]
        elif m <= 3:
            txt = TEXTO_ACAO["curto_up" if dirc == "up" else "curto_down" if dirc == "down" else "curto_ok"]
        elif m <= 6 or dirc in ("up", "down"):
            txt = TEXTO_ACAO["tatico_up" if dirc == "up" else "tatico_down" if dirc == "down" else "tatico_ok"]
        else:
            txt = TEXTO_ACAO["medio"]
        linhas.append({"mes": meses[m], "previsao": F[m], "programada": p, "recomendada": r_ch, "acao": acao, "diferenca": dif,
                       "decidir_aumento_ate": meses[m - up] if m - up >= 0 else "prazo vencido",
                       "decidir_reducao_ate": meses[m - down] if m - down >= 0 else "congelado",
                       "estoque_proj_programado": est_prog - pend_prog, "cobertura_programado": cob_prog if F[m] > 0 else np.nan,
                       "estoque_proj_recomendado": rec["estoque"][0, m] - rec["pendente"][0, m],
                       "reserva": rec["ss"][0, m], "risco_falta": rf, "risco_excesso": rx, "gatilho": sev,
                       "motivo": "; ".join(motivos), "o_que_fazer": txt if (F[m] > 0 or p > 0 or r_ch > 0) else "",
                       "_congelado": m < down})
    df = pd.DataFrame(linhas)
    visivel = ~((df["previsao"] <= 0) & df["_congelado"])          # previsão zero dentro do HB não aparece
    return df[visivel].drop(columns="_congelado").reset_index(drop=True)


# =====================================================================================================
# 9. Segunda opinião: série parecida no experimento anterior
# =====================================================================================================
def carregar_referencia():
    for p in ARQUIVOS_REFERENCIA:
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def perfil(prev):
    v = np.array([x for x in prev if x > 0], float)
    if len(v) < 2:
        return {"media": float(v.mean()) if len(v) else 0.0, "cv": 0.0, "pico": 0.0, "n": len(v)}
    return {"media": float(v.mean()), "cv": float(v.std(ddof=1) / v.mean()), "pico": float(v.max() / v.mean()), "n": len(v)}


def segunda_opiniao(prod, ref, dist, choque, hb):
    """Série mais parecida entre as 8 testadas no experimento anterior (origem, cobertura, LT, volume, variação, pico).
    Semelhança = 100·e^(−distância/3). A política vem do experimento anterior (janela simples, distribuição Normal/Poisson)."""
    if not ref:
        return None
    prof = pd.DataFrame(ref["profiles"])
    sku = prod.get("sku_base")
    if sku in set(prof["sku"]):          # série da base: usa o mesmo perfil do experimento e não compara com ela mesma
        row = prof[prof["sku"] == sku].iloc[0]
        pf = {"media": row["forecast_mean"], "cv": row["forecast_cv"], "pico": row["forecast_peak_ratio"]}
        prof = prof[prof["sku"] != sku]
    else:
        pf = perfil(prod["previsao"])
    feats = {"cobertura": ("target_days", float(prod["cobertura_dias"]), 1.0),
             "lt": ("max_material_lt_weeks", float(prod["lt_insumo_semanas"]), 1.0),
             "volume": ("forecast_mean", math.log10(max(pf["media"], 1)), 1.0),
             "cv": ("forecast_cv", pf["cv"], 1.5), "pico": ("forecast_peak_ratio", pf["pico"], 1.0)}
    X = prof.copy()
    X["forecast_mean"] = np.log10(X["forecast_mean"].clip(lower=1))
    d2 = (X["origin"] != prod["origem"]).astype(float) ** 2
    todos = pd.DataFrame(ref["profiles"]).assign(forecast_mean=lambda d: np.log10(d["forecast_mean"].clip(lower=1)))
    for colname, val, w in feats.values():
        sd = todos[colname].std(ddof=1) or 1.0
        d2 = d2 + w * ((val - X[colname]) / sd) ** 2
    X["distancia"] = np.sqrt(d2)
    X["semelhanca"] = 100 * np.exp(-X["distancia"] / 3)
    X = X.sort_values("distancia")
    hb_ref = 60 if float(hb) > 45 else 30
    dref = "Normal" if dist.startswith("Erros") else dist
    best = pd.DataFrame(ref["best"])

    def pol_de(sku):
        b = best[(best["sku"] == sku) & (best["hb_days"] == hb_ref) & (best["distribution"] == dref) & (best["shock"] == choque)]
        return (b["best_policy"].iloc[0], bool(b["best_meets_floors"].iloc[0])) if len(b) else ("—", False)

    top = [{"serie": s, "semelhanca": sim, "politica": pol_de(s)[0], "cumpre": pol_de(s)[1]}
           for s, sim in zip(X["sku"].head(3), X["semelhanca"].head(3))]
    votos = pd.Series([t["politica"] for t in top]).value_counts()
    ranking = X[["sku", "kind", "origin", "target_days", "max_material_lt_weeks", "forecast_cv", "forecast_peak_ratio", "semelhanca"]]
    proprio = pol_de(sku) if sku in set(pd.DataFrame(ref["profiles"])["sku"]) else None
    return {"top": top, "ranking": ranking, "hb": hb_ref, "dist_ref": dref, "proprio": proprio,
            "confianca": "alta" if votos.iloc[0] == 3 else "média" if votos.iloc[0] == 2 else "baixa"}


# =====================================================================================================
# 10. Confirmação no Stockpyl: executa no Stockpyl as mesmas decisões do SOLARIS e compara
# =====================================================================================================
def confirmar_stockpyl(resultado, n_rep, progresso=None):
    """Para as primeiras n_rep repetições de cada cenário e política, roda o Stockpyl com as chegadas decididas pelo SOLARIS.
    O Stockpyl usa prazo de entrega = janela de redução (o pedido vira firme nesse momento); os meses iniciais entram como
    um aquecimento sem demanda, para incluir a produção já programada. O choque usa o DisruptionProcess (retém o recebimento)."""
    from stockpyl.supply_chain_network import single_stage_system
    from stockpyl.sim import initialize, step, close
    from stockpyl.disruption_process import DisruptionProcess
    prod, par = resultado["produto"], resultado["parametros"]
    preco = float(prod["preco"])
    chaves = [k for k in resultado["_brutos"] if k[1] not in ("_cen", "PROG")]
    linhas, total, feito = [], len(chaves) * n_rep, 0
    for (cen, pol) in chaves:
        bru, sc = resultado["_brutos"][(cen, pol)], resultado["_brutos"][(cen, "_cen")]
        W = int(resultado["cenarios"][cen]["janela_reducao"])
        for r in range(min(n_rep, sc["D"].shape[0])):
            Dr, Sr, ch = sc["D"][r], sc["S"][r], bru["chegada_final"][r]
            n = len(Dr)
            dem = [0.0] * W + [float(x) for x in Dr]
            net = single_stage_system(holding_cost=par["custo_estoque_aa"] / 12 * preco, stockout_cost=par["custo_falta"] * preco,
                                      demand_type="D", demand_list=dem, policy_type="BS", base_stock_level=0.0,
                                      shipment_lead_time=W, initial_inventory_level=float(prod["estoque_inicial"]))
            node = net.nodes[0]
            estados = [False] * W + [bool(x) for x in Sr]
            if any(estados):
                node.disruption_process = DisruptionProcess(random_process_type="E", disruption_type="RP",
                                                            disruption_state_list=estados)
            initialize(network=net, num_periods=W + n, rand_seed=0)
            ip = float(prod["estoque_inicial"])
            for k in range(W + n):
                q = float(ch[k]) if k < n else 0.0           # pedido no período k chega em k + W (= mês k da simulação)
                ip_dep = ip - dem[k]
                node.inventory_policy.base_stock_level = ip_dep + q
                step(network=net)
                ip = ip_dep + q
            close(network=net)
            il = np.array([float(list(node.state_vars[W + t].inventory_level.values())[0]) for t in range(n)])
            est_spl = np.maximum(il, 0.0)
            dif = float(np.max(np.abs(est_spl - bru["estoque"][r])))
            aval = np.asarray(prod["previsao"]) > 0
            atend = np.minimum(Dr, np.maximum(il + Dr, 0.0))          # atendido = demanda − aumento da pendência
            linhas.append({"cenario": cen, "politica": pol, "repeticao": r,
                           "estoque_medio_solaris": float(bru["estoque"][r][aval].mean()) if aval.any() else 0.0,
                           "estoque_medio_stockpyl": float(est_spl[aval].mean()) if aval.any() else 0.0,
                           "pendencia_final_solaris": float(bru["pendente"][r][-1]), "pendencia_final_stockpyl": float(max(-il[-1], 0.0)),
                           "maior_diferenca_un": dif, "identico": dif < 1e-3 * max(1.0, float(np.max(Dr)))})
            feito += 1
            if progresso:
                progresso(feito / max(total, 1), f"Stockpyl · {cen} · {pol}")
    return pd.DataFrame(linhas)


# =====================================================================================================
# 11. Histórico: salvar, listar, carregar e exportar para Excel
# =====================================================================================================
def _serializavel(resultado):
    r = {k: v for k, v in resultado.items() if not k.startswith("_") and k not in ("repeticoes", "mensal", "resumo", "melhor", "stockpyl")}
    r["resumo"] = resultado["resumo"].to_dict("records")
    r["melhor"] = resultado["melhor"].to_dict("records")
    r["mensal"] = [{"cenario": cen, "politica": p, **{k: [float(x) for x in v] for k, v in df.to_dict("list").items()}}
                   for (cen, p), df in resultado["mensal"].items()]
    r["stockpyl"] = resultado["stockpyl"].to_dict("records") if resultado.get("stockpyl") is not None else None
    return r


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def excel_resultado(resultado):
    """Excel da rodada: parâmetros, produto, melhor política, resumo, plano e ações, risco mensal, Stockpyl e repetições."""
    prod = resultado["produto"]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame([{"parâmetro": k, "valor": str(v)} for k, v in resultado["parametros"].items()] +
                     [{"parâmetro": "z", "valor": resultado["z"]}, {"parâmetro": "data", "valor": resultado["data"]}]
                     ).to_excel(w, sheet_name="Parametros", index=False)
        pd.DataFrame([{"cenario": k, **v} for k, v in resultado["cenarios"].items()]).to_excel(w, sheet_name="Cenarios", index=False)
        pd.DataFrame([{c: prod.get(c) for c in CAMPOS}]).to_excel(w, sheet_name="Produto", index=False)
        pd.DataFrame({"mes": prod["meses"], "previsao": prod["previsao"], "programada": prod["programada"]}).to_excel(
            w, sheet_name="Produto", index=False, startrow=3)
        resultado["melhor"].to_excel(w, sheet_name="Melhor_politica", index=False)
        resultado["resumo"].to_excel(w, sheet_name="Resumo", index=False)
        for i, b in resultado["melhor"].reset_index(drop=True).iterrows():
            try:
                plano_e_acoes(resultado, b["cenario"], b["como_executar"]).assign(cenario=b["cenario"], politica=b["como_executar"]
                                                                                    ).to_excel(w, sheet_name=f"Acao_{i + 1}", index=False)
            except Exception:
                pass
        pd.concat([df.assign(mes=prod["meses"], cenario=cen, politica=p) for (cen, p), df in resultado["mensal"].items()]
                  ).to_excel(w, sheet_name="Risco_mensal", index=False)
        if resultado.get("stockpyl") is not None:
            resultado["stockpyl"].to_excel(w, sheet_name="Validacao_Stockpyl", index=False)
        rep = resultado.get("repeticoes")
        if rep is not None and len(rep) <= 20_000:
            rep.to_excel(w, sheet_name="Repeticoes", index=False)
        elif rep is not None:
            pd.DataFrame({"aviso": [f"{len(rep)} linhas: as repetições estão no arquivo _repeticoes.csv da mesma rodada."]}
                         ).to_excel(w, sheet_name="Repeticoes", index=False)
    return buf.getvalue()


def bytes_excel(resultado):
    """Excel da rodada, gerado uma vez e guardado no próprio resultado (evita refazer a cada clique)."""
    if resultado.get("_xlsx") is None:
        resultado["_xlsx"] = excel_resultado(resultado)
    return resultado["_xlsx"]


def json_resultado(resultado):
    return json.dumps(_serializavel(resultado), ensure_ascii=False, default=_json_default).encode("utf-8")


def salvar_resultado(resultado):
    PASTA_HIST.mkdir(parents=True, exist_ok=True)
    nome = f"{resultado['id']}_{norm_txt(resultado['produto']['nome'])[:30]}"
    (PASTA_HIST / f"{nome}.json").write_bytes(json_resultado(resultado))
    (PASTA_HIST / f"{nome}.xlsx").write_bytes(bytes_excel(resultado))
    if resultado.get("repeticoes") is not None:
        resultado["repeticoes"].to_csv(PASTA_HIST / f"{nome}_repeticoes.csv", index=False, sep=";", decimal=",")
    return nome


def listar_historico():
    if not PASTA_HIST.exists():
        return pd.DataFrame()
    linhas = []
    for f in sorted(PASTA_HIST.glob("*.json"), reverse=True):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            for b in r["melhor"]:
                linhas.append({"arquivo": f.stem, "data": r["data"], "produto": r["produto"]["nome"],
                               "simulacoes": r["parametros"]["n_rep"], "protecao": r["parametros"]["protecao"],
                               "cenario": b["cenario"], "politica": b["politica"], "como_executar": b["como_executar"],
                               "cumpre_metas": b["cumpre_metas"], "nivel_servico": b["nivel_servico"],
                               "nivel_garantido": b["nivel_garantido"], "custo_total": b["custo_total"],
                               "stockpyl": r.get("stockpyl") is not None})
        except Exception:
            continue
    return pd.DataFrame(linhas)


def carregar_resultado(nome):
    """Recarrega uma rodada salva (sem as repetições brutas) para consultar nas telas."""
    r = json.loads((PASTA_HIST / f"{nome}.json").read_text(encoding="utf-8"))
    r["resumo"] = pd.DataFrame(r["resumo"])
    r["melhor"] = pd.DataFrame(r["melhor"])
    r["mensal"] = {(m["cenario"], m["politica"]): pd.DataFrame({k: v for k, v in m.items() if k not in ("cenario", "politica")})
                   for m in r["mensal"]}
    r["stockpyl"] = pd.DataFrame(r["stockpyl"]) if r.get("stockpyl") else None
    r["repeticoes"] = None
    r["_brutos"] = {}
    r["_arquivo"] = nome
    r["_xlsx"] = bytes_historico(nome)
    return r


def apagar_resultado(nome):
    for ext in (".json", ".xlsx", "_repeticoes.csv"):
        p = PASTA_HIST / f"{nome}{ext}"
        if p.exists():
            p.unlink()


def bytes_historico(nome, ext=".xlsx"):
    p = PASTA_HIST / f"{nome}{ext}"
    return p.read_bytes() if p.exists() else None


def zip_historico():
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PASTA_HIST.glob("*")) if PASTA_HIST.exists() else []:
            z.write(f, f.name)
    return buf.getvalue()


# =====================================================================================================
# 12. Backtest com o histórico real (só produtos da base): o que cada política teria feito com as versões reais
# =====================================================================================================
def backtest_historico(serie, par, z, curva, versao_idx=0):
    """Backtest com o histórico real: a demanda é a venda realizada (sell-in) e a previsão revisada é a de cada versão real
    do triângulo. P0 = o que aconteceu de fato (estoque real da base). Começa na primeira versão com previsão.
    Premissa: a venda realizada é tratada como demanda (não se observa a demanda perdida)."""
    validas = versoes_validas(serie)
    r0 = max(int(versao_idx), validas[0] if validas else 0)
    T = serie["T_real"]
    if T - r0 < 3 or (np.nan_to_num(serie["realizado"][r0:T]) > 0).sum() < 3:
        return None
    A = np.nan_to_num(serie["realizado"][r0:T])
    n = len(A)
    V = np.nan_to_num(serie["V"][r0:T, r0:T])
    prod = produto_da_base(serie, r0)
    prod = dict(prod, previsao=[float(x) for x in np.nan_to_num(serie["V"][r0, r0:T])],
                programada=[float(x) for x in np.nan_to_num(serie["producao_real"][r0:T])], meses=serie["meses"][r0:T])
    Vr = np.zeros((1, n, n))
    for t in range(n):
        Vr[0, t, t:] = V[t, t:]
    Vr[0, 0, :] = prod["previsao"]
    D, S = A[None, :].astype(float), np.zeros((1, n), bool)
    cv = cv_por_horizonte(curva, n + 40)
    aval = (A > 0) | (np.asarray(prod["previsao"]) > 0)
    p2 = dict(par, _dist="Normal", _aval=aval)
    preco = float(prod["preco"])
    linhas = []
    # P0: o que aconteceu (estoque real informado na base)
    est = np.maximum(np.nan_to_num(serie["estoque_real"][r0:T]), 0.0)[None, :]
    out = {"atendido": D.copy(), "estoque": est, "pendente": np.zeros((1, n)), "ss": np.zeros((1, n)),
           "pedido": np.zeros((1, n)), "corte": np.zeros((1, n)), "chegada_final": np.zeros((1, n)),
           "cob": np.array([[_cobertura(est[:, t], Vr[:, t, :], t, n, par["cob_max"])[0] for t in range(n)]]),
           "excesso": np.array([[_excesso_unidades(est[:, t], Vr[:, t, :], t, n, par["cob_max"])[0] for t in range(n)]])}
    reais = {"P0": (metricas(out, D, np.asarray(prod["previsao"]), prod, p2, par["custo_estoque_aa"] / 12 * preco,
                             par["custo_falta"] * preco, preco), est[0])}
    for pol in [p for p in par["politicas"] if p != "P2L" or int(prod.get("lote") or 0) > 0]:
        res = simular(prod, pol, D, Vr, S, p2, cv, z)
        reais[pol] = (res, res["_bruto"]["estoque"][0] - res["_bruto"]["pendente"][0])
    for pol, (res, traj) in reais.items():
        rr = res["rep"].iloc[0]
        linhas.append({"politica": pol, "nivel_servico": rr["nivel_servico"], "meses_falta": rr["meses_falta"],
                       "meses_excesso": rr["meses_excesso"], "estoque_medio": rr["estoque_medio"], "estoque_final": rr["estoque_final"],
                       "custo_total": rr["custo_total"], "_estoque": traj})
    return {"tabela": pd.DataFrame(linhas), "meses": prod["meses"], "realizado": A, "previsao_inicial": prod["previsao"],
            "versao": serie["versoes"][r0]}
