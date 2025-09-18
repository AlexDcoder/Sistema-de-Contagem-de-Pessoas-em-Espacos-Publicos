import io
import os
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="People Counter", page_icon="👥", layout="centered")
st.title("People Counter (YOLOv8)")
st.write("Faça upload de uma imagem. Ela será processada e a versão anotada será exibida. Resultados são persistidos no banco.")

uploaded = st.file_uploader("Arraste e solte uma imagem (JPG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded is not None:
    with st.spinner("Processando imagem..."):
        files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "image/jpeg")}
        try:
            resp = requests.post(f"{API_URL}/process", files=files, timeout=180)
            if resp.status_code != 200:
                st.error(f"Erro da API: {resp.status_code} - {resp.text}")
            else:
                duplicate = resp.headers.get("X-Duplicate", "false").lower() == "true"
                img_id = resp.headers.get("X-Image-Id", "")
                st.success("Imagem processada" + (" (duplicada, retornando do cache)" if duplicate else ""))
                st.image(io.BytesIO(resp.content), caption=f"ID: {img_id}")
                st.download_button(
                    label="Baixar imagem anotada",
                    data=resp.content,
                    file_name=f"annotated_{uploaded.name}",
                    mime="image/jpeg",
                )
        except Exception as e:
            st.error(f"Falha ao chamar API: {e}")

