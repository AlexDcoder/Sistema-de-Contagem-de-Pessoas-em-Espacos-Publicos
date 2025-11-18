import io
import os
import pathlib
import requests
import streamlit as st
from datetime import datetime


def _load_css(file_path: pathlib.Path) -> None:
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Crowd Counting System",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Carregar CSS customizado
_load_css(pathlib.Path(__file__).parent / "style.css")

# Estado
if "analises_realizadas" not in st.session_state:
    st.session_state.analises_realizadas = []
if "imagem_atual" not in st.session_state:
    st.session_state.imagem_atual = None
if "resultado_contagem" not in st.session_state:
    st.session_state.resultado_contagem = None
if "imagens_salvas" not in st.session_state:
    st.session_state.imagens_salvas = {}

# Header
st.markdown(
    """
<div style="text-align: center; padding: 2rem 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; margin-bottom: 2rem;">
  <h1 style="color: white; margin: 0; font-size: 2.5rem; font-weight: 700;">👥 Sistema de Contagem de Pessoas</h1>
  <p style="color: #e8e8e8; margin: 0.5rem 0 0 0; font-size: 1.2rem;">Análise inteligente de multidões em espaços públicos</p>
</div>
""",
    unsafe_allow_html=True,
)

col_main, col_sidebar = st.columns([3, 1])

with col_sidebar:
    st.markdown("### 📊 Histórico de Análises")

    if st.button("🔄 Nova Análise", type="primary"):
        st.session_state.imagem_atual = None
        st.session_state.resultado_contagem = None
        st.rerun()

    st.markdown("---")

    if st.session_state.analises_realizadas:
        for i, analise in enumerate(reversed(st.session_state.analises_realizadas[-5:])):
            with st.container():
                col_content, col_delete = st.columns([4, 1])
                with col_content:
                    st.markdown(
                        f"""
                        <div style=\"background-color: #3a3a3a; padding: 1rem; border-radius: 8px; margin: 0.5rem 0; border-left: 4px solid #667eea;\">
                          <strong style=\"color: #e0e0e0;\">{analise['nome']}</strong><br>
                          <small style=\"color: #b0b0b0;\">{analise['data']}</small><br>
                          <span style=\"color: #28a745; font-weight: bold;\">👥 {analise['pessoas']} pessoas</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_delete:
                    if analise["nome"] in st.session_state.imagens_salvas:
                        imagem_data = st.session_state.imagens_salvas[analise["nome"]]
                        st.download_button(
                            label="📥",
                            data=imagem_data,
                            file_name=f"{analise['nome']}.jpg",
                            mime="image/jpeg",
                            key=f"download_btn_{i}",
                            help="Baixar imagem",
                        )
                    else:
                        st.button("📥", key=f"download_disabled_{i}", disabled=True, help="Imagem não disponível")

                    if st.button("❌", key=f"delete_{i}", help="Excluir análise"):
                        index_to_remove = len(st.session_state.analises_realizadas) - 1 - i
                        analise_removida = st.session_state.analises_realizadas.pop(index_to_remove)
                        if analise_removida["nome"] in st.session_state.imagens_salvas:
                            del st.session_state.imagens_salvas[analise_removida["nome"]]
                        st.rerun()
    else:
        st.info("Nenhuma análise realizada ainda")

with col_main:
    st.markdown("### 📸 Upload da Imagem")
    uploaded_file = st.file_uploader(
        "Escolha uma imagem para análise",
        type=["png", "jpg", "jpeg"],
        help="Formatos suportados: PNG, JPG, JPEG",
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        st.session_state.imagem_atual = uploaded_file
        col_img, col_info = st.columns([2, 1])
        with col_img:
            st.image(uploaded_file, caption="Imagem carregada", width='stretch')
        with col_info:
            st.markdown("### 📋 Informações")
            st.write(f"**Nome:** {uploaded_file.name}")
            st.write(f"**Tamanho:** {uploaded_file.size / 1024:.1f} KB")
            st.write(f"**Tipo:** {uploaded_file.type}")
            nome_analise = st.text_input(
                "Nome da análise", value=uploaded_file.name.split(".")[0], key="nome_analise_upload"
            )
            descricao = st.text_area(
                "Descrição (opcional)", placeholder="Descreva o local ou contexto da imagem...", key="descricao_upload"
            )
            st.markdown("---")
            mode = st.selectbox(
                "Modo de anotação",
                options=["seg", "bbox"],
                index=0 if st.session_state.get("mode", "seg") == "seg" else 1,
                help="'seg' usa máscaras; 'bbox' usa apenas caixas.",
                key="mode_selectbox"
            )
            st.session_state["mode"] = mode
            # Confiança fixa em 0.25 (padrão do YOLO)
            conf = 0.25
    else:
        st.markdown(
            """
            <div style=\"text-align: center; padding: 4rem 2rem; border: 2px dashed #667eea; border-radius: 10px; background-color: #3a3a3a;\">
              <div style=\"font-size: 4rem; margin-bottom: 1rem;\">📷</div>
              <h3 style=\"color: #e0e0e0; margin-bottom: 0.5rem;\">Nenhuma imagem carregada</h3>
              <p style=\"color: #b0b0b0;\">Faça upload de uma imagem para começar a análise</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.session_state.imagem_atual is not None:
        st.markdown("### 🔍 Análise")
        # Valores padrão para processamento
        mode = st.session_state.get("mode", "seg")
        conf = 0.25  # Valor fixo de confiança
        col_btn, col_status = st.columns([1, 2])
        with col_btn:
            if st.button("🚀 Contar Pessoas", type="primary", key="contar_pessoas_btn"):
                with st.spinner("Processando imagem na API..."):
                    try:
                        # Usa sempre a imagem do session_state para evitar perda após reruns
                        img_obj = st.session_state.imagem_atual
                        img_name = getattr(img_obj, "name", None) or "upload.jpg"
                        img_bytes = img_obj.getvalue()
                        img_mime = getattr(img_obj, "type", None) or "image/jpeg"
                        files = {"file": (img_name, img_bytes, img_mime)}
                        params = {"mode": mode, "conf": conf}
                        resp = requests.post(f"{API_URL}/process", files=files, params=params, timeout=180)
                        if resp.status_code != 200:
                            st.session_state.resultado_contagem = None
                            st.error(f"Erro da API: {resp.status_code} - {resp.text}")
                        else:
                            duplicate = resp.headers.get("X-Duplicate", "false").lower() == "true"
                            img_id = resp.headers.get("X-Image-Id", "")
                            count_hdr = resp.headers.get("X-Count", "")
                            try:
                                count_val = int(count_hdr) if count_hdr != "" else None
                            except Exception:
                                count_val = None
                            st.session_state.resultado_contagem = count_val
                            annotated_bytes = resp.content
                            st.image(
                                io.BytesIO(annotated_bytes),
                                caption=f"Resultado (ID: {img_id}{' • duplicado' if duplicate else ''})",
                                width='stretch',
                            )
                            st.download_button(
                                label="📥 Baixar imagem anotada",
                                data=annotated_bytes,
                                file_name=f"annotated_{img_name}",
                                mime="image/jpeg",
                                key="download_result_btn",
                            )
                            st.session_state.imagens_salvas[nome_analise] = annotated_bytes
                            if count_val is None:
                                st.warning("Processado com sucesso, mas a contagem não foi recebida da API.")
                            else:
                                st.success("✅ Análise concluída com sucesso!")
                    except Exception as e:
                        st.session_state.resultado_contagem = None
                        st.error(f"Falha ao chamar API: {e}")

        with col_status:
            if st.session_state.resultado_contagem is not None:
                st.markdown(
                    f"""
                    <div style=\"background: linear-gradient(135deg, #28a745, #20c997); padding: 1.5rem; border-radius: 10px; text-align: center; color: white;\">
                      <h2 style=\"margin: 0; font-size: 3rem;\">👥 {st.session_state.resultado_contagem}</h2>
                      <p style=\"margin: 0.5rem 0 0 0; font-size: 1.2rem;\">pessoas detectadas</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if st.session_state.resultado_contagem is not None:
            st.markdown("### 💾 Salvar Análise")
            col_save, col_actions = st.columns([2, 1])
            with col_save:
                nome_final = st.text_input(
                    "Nome da análise",
                    value=nome_analise if "nome_analise" in locals() else "Nova análise",
                    key="nome_final_save",
                )
            with col_actions:
                if st.button("💾 Salvar", key="salvar_analise_btn"):
                    nova_analise = {
                        "nome": nome_final,
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "pessoas": st.session_state.resultado_contagem,
                        "descricao": descricao if "descricao" in locals() else "",
                    }
                    if nome_analise in st.session_state.imagens_salvas:
                        st.session_state.imagens_salvas[nome_final] = st.session_state.imagens_salvas[nome_analise]
                    elif st.session_state.imagem_atual is not None:
                        st.session_state.imagens_salvas[nome_final] = st.session_state.imagem_atual.getvalue()
                    st.session_state.analises_realizadas.append(nova_analise)
                    st.success("Análise salva com sucesso!")
                    st.rerun()

st.markdown("---")
st.markdown(
    """
<div style="text-align: center; color: #666; padding: 1rem;">
  <p>Sistema de Contagem de Pessoas em Espaços Públicos | Desenvolvido com Streamlit</p>
</div>
""",
    unsafe_allow_html=True,
)

