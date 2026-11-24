# tela_inicio.py — Tela 1: o que é a ferramenta, como usar, quem fez e documentos para baixar.
# Os textos ficam em conteudo.py (fácil de editar sem mexer na tela).
import importlib

import streamlit as st

import conteudo
import motor


def mostrar(dados, f):
    importlib.reload(conteudo)  # edições no conteudo.py aparecem ao recarregar a página
    st.header(conteudo.TITULO)
    st.markdown(f"*{conteudo.SUBTITULO}*")

    esq, dir_ = st.columns([3, 2], gap="large")
    with esq:
        st.subheader("O que é")
        st.markdown(conteudo.O_QUE_E)
        st.subheader("Que problema resolve")
        st.markdown(conteudo.PROBLEMA)
        st.subheader("Como usar")
        st.markdown("\n".join(f"{i}. {passo}" for i, passo in enumerate(conteudo.COMO_USAR, 1)))
        st.info(conteudo.JANELA)
    with dir_:
        st.subheader("Quem fez")
        for papel, nomes in conteudo.EQUIPE.items():
            st.markdown(f"**{papel}:** " + " · ".join(nomes))
        st.caption(conteudo.PROJETO)
        st.caption(conteudo.AGRADECIMENTOS)

        st.subheader("Documentos")
        docs = sorted(motor.PASTA_DOCS.glob("*")) if motor.PASTA_DOCS.exists() else []
        docs = [d for d in docs if d.is_file()]
        if not docs:
            st.caption(f"Coloque os PDFs e documentos na pasta **{motor.PASTA_DOCS}** para que apareçam aqui.")
        for d in docs:
            st.download_button(f"⬇ {conteudo.DOCUMENTOS.get(d.name, d.name)}", d.read_bytes(), file_name=d.name,
                               key=f"doc_{d.name}", width="stretch")
        st.download_button("⬇ Planilha modelo para cadastrar produtos", motor.planilha_modelo([motor.produto_novo("Exemplo")]),
                           file_name="SOLARIS_modelo_importacao.xlsx", key="modelo_inicio", width="stretch")

        st.subheader("A base em uso")
        s = dados["series"]
        n_prod = sum(1 for v in s.values() if v["tipo"] == "produto")
        c1, c2, c3 = st.columns(3)
        c1.metric("Produtos", n_prod, border=True)
        c2.metric("Benchmarks", len(s) - n_prod, border=True)
        c3.metric("Novos", len(st.session_state.get("cadastrados", [])), border=True)
        st.caption(f"Erros de previsão de {len(dados['arquivo'])} pares versão × mês dos benchmarks calibram a incerteza.")

    st.divider()
    a, b = st.columns(2, gap="large")
    with a:
        st.subheader("Políticas comparadas")
        for nome, desc in conteudo.POLITICAS.items():
            st.markdown(f"**{nome}.** {desc}")
    with b:
        st.subheader("Como ler as métricas")
        for nome, desc in conteudo.METRICAS.items():
            st.markdown(f"**{nome}.** {desc}")
    st.caption(conteudo.AVISO_DADOS)
