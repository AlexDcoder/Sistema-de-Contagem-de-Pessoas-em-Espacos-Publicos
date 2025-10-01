import streamlit as st
import uuid
import pathlib

def load_css(file_path):
    with open(file_path) as f:
        st.html(f"<style>{f.read()}</style>")
css_path = pathlib.Path("style.css")
load_css(css_path)

import streamlit as st


if 'linhas_menu' not in st.session_state:
    st.session_state.linhas_menu = ["teste imagem1","imagem2"]


st.sidebar.title("Meu perfil")


col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("Nova imagem", use_container_width=True):
        pass

st.sidebar.markdown("---")






st.container(height=400, border=True).markdown(
        """
        <div style="text-align: center; padding-top: 50px; opacity: 0.6;">
            <p style="font-size: 80px; margin-bottom: 10px;">☁️</p>
            <p style="font-size: 1.5rem;">Selecionar imagem</p>
        </div>
        """,
        unsafe_allow_html=True
    )
teste = False
if st.button("Contar pessoas"):
    teste = True
if teste:
    st.title("Total de pessoas: 23")

nome = st.text_input("Nome da imagem")
descricao = st.text_area(
    "Descrição da imagem",
    height=150  
)
        
if st.button("Salvar imagem"):
    with col1:        
        nova_linha = f"{nome}"
        st.session_state.linhas_menu.append(nova_linha)
    st.success("Salvo com sucesso!")


for i, linha in enumerate(st.session_state.linhas_menu):
    with st.sidebar.container():
        st.subheader(linha)