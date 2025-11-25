import io
import os
import pathlib
import requests
import streamlit as st
from datetime import datetime
import uuid
import json
import base64
from pathlib import Path


def _load_css(file_path: pathlib.Path) -> None:
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("API_KEY")


def _auth_headers() -> dict:
    h = {}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h

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
if "imagem_atual_bytes" not in st.session_state:
    st.session_state.imagem_atual_bytes = None
if "imagem_atual_name" not in st.session_state:
    st.session_state.imagem_atual_name = None
if "imagem_atual_type" not in st.session_state:
    st.session_state.imagem_atual_type = None
if "resultado_contagem" not in st.session_state:
    st.session_state.resultado_contagem = None
if "imagens_salvas" not in st.session_state:
    st.session_state.imagens_salvas = {}

# --- Identificador do usuário/ sessão persistente via query param 'sid'
query_params = st.query_params
sid = None
if "sid" in query_params and query_params["sid"]:
    sid = query_params["sid"][0]
else:
    sid = str(uuid.uuid4())
    # atualiza query params (st.query_params espera mapeamento de listas)
    new_qp = dict(st.query_params)
    new_qp["sid"] = [sid]
    st.query_params = new_qp

# Diretório local para persistência leve por 'sid' (usa/ cria pasta ./data/<sid>)
base_data_dir = Path(__file__).parent / "data"
user_dir = base_data_dir / sid
user_dir.mkdir(parents=True, exist_ok=True)

# Carrega análises salvas localmente para este sid (se existirem)
meta_file = user_dir / "metadata.json"
if meta_file.exists():
    try:
        with open(meta_file, "r", encoding="utf-8") as mf:
            data = json.load(mf)
            # Coloca no session_state para uso pela UI
            st.session_state.analises_realizadas = data.get("analises", [])
            # Carrega imagens salvas (se houverem arquivos referenciados)
            st.session_state.imagens_salvas = {}
            for a in st.session_state.analises_realizadas:
                img_name = a.get("saved_image")
                if img_name:
                    img_path = user_dir / img_name
                    if img_path.exists():
                        st.session_state.imagens_salvas[a["nome"]] = img_path.read_bytes()
    except Exception:
        # falha ao ler — ignora e segue com estado em branco
        pass

# --- Tenta carregar histórico do servidor e mesclar (GET /images)
try:
    headers = _auth_headers()
    resp = requests.get(f"{API_URL}/images", params={"page": 1, "per_page": 50}, headers=headers, timeout=4)
    if resp.status_code == 200:
        payload = resp.json()
        server_items = payload.get("images", []) if isinstance(payload, dict) else []
        # Converte para o formato local e mescla (server items primeiro)
        merged = []
        for it in server_items:
            meta = it.get("metadata", {}) or {}
            nome = meta.get("title") or meta.get("input", it.get("input_filename") or f"img_{it.get('id')}")
            created = it.get("created_at")
            # formata data semelhante ao local
            try:
                dt = datetime.fromisoformat(created)
                data_str = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                data_str = created or ""
            pessoas = meta.get("count") if isinstance(meta.get("count"), int) else meta.get("count")
            descricao_srv = meta.get("description") or meta.get("descricao") or ""
            merged.append({
                "nome": nome,
                "data": data_str,
                "pessoas": pessoas if pessoas is not None else "",
                "descricao": descricao_srv,
                "saved_image": None,
                "_server_id": it.get("id"),
            })
        # evita duplicatas simples (mesma nome+data)
        existing_keys = {(a.get("nome"), a.get("data")) for a in st.session_state.analises_realizadas}
        for m in merged:
            key = (m.get("nome"), m.get("data"))
            if key not in existing_keys:
                st.session_state.analises_realizadas.insert(0, m)
                existing_keys.add(key)
except Exception:
    # falha ao contatar API — segue com histórico local
    pass

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
    
    # Processar exclusões pendentes ANTES de renderizar
    if "delete_analise_id" in st.session_state and st.session_state.delete_analise_id:
        analise_id_to_delete = st.session_state.delete_analise_id
        # Limpar o flag ANTES de processar para evitar loops
        del st.session_state.delete_analise_id
        
        # Remover a análise da lista
        if "analises_realizadas" in st.session_state and st.session_state.analises_realizadas:
            analises_originais = st.session_state.analises_realizadas.copy()
            analises_filtradas = []
            
            for a in analises_originais:
                # Verificar se é a análise a ser removida
                # Usar a mesma lógica de geração de ID que no render
                analise_id_atual = a.get("id") or f"{a.get('nome', '')}_{a.get('data', '')}"
                
                # Comparar IDs (normalizar para evitar problemas de espaços/caracteres)
                analise_id_atual_clean = str(analise_id_atual).strip()
                analise_id_to_delete_clean = str(analise_id_to_delete).strip()
                
                if analise_id_atual_clean != analise_id_to_delete_clean:
                    analises_filtradas.append(a)
                else:
                    # Encontrou a análise a remover - remover imagem salva também
                    nome_analise = a.get("nome")
                    if nome_analise and nome_analise in st.session_state.imagens_salvas:
                        del st.session_state.imagens_salvas[nome_analise]
            
            # Atualizar a lista
            st.session_state.analises_realizadas = analises_filtradas
        
        # Forçar rerun para atualizar a interface
        st.rerun()

    if st.session_state.analises_realizadas:
        # Mostrar últimas 5 análises em ordem reversa (mais recente primeiro)
        total_analises = len(st.session_state.analises_realizadas)
        inicio = max(0, total_analises - 5)  # Mostrar no máximo 5, começando das mais recentes
        
        # Criar lista de análises para renderizar
        analises_para_renderizar = []
        for idx in range(total_analises - 1, inicio - 1, -1):  # Iterar de trás para frente
            if idx < 0 or idx >= len(st.session_state.analises_realizadas):
                continue
            analise = st.session_state.analises_realizadas[idx]
            analise_id = analise.get("id") or f"{analise.get('nome', '')}_{analise.get('data', '')}"
            analises_para_renderizar.append((analise_id, analise, idx))
        
        # Container único envolvendo TODAS as análises
        with st.container():
            # Renderizar cada análise dentro do container único
            for analise_id, analise, idx in analises_para_renderizar:
                col_content, col_actions = st.columns([3, 1])
                with col_content:
                    st.markdown(
                        f"""
                        <div style="background-color: #3a3a3a; padding: 1rem; border-radius: 8px; margin: 0.5rem 0; border-left: 4px solid #667eea;">
                          <strong style="color: #e0e0e0;">{analise['nome']}</strong><br>
                          <small style="color: #b0b0b0;">{analise['data']}</small><br>
                          <span style="color: #28a745; font-weight: bold;">👥 {analise['pessoas']} pessoas</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_actions:
                    # Botões em coluna vertical
                    if analise["nome"] in st.session_state.imagens_salvas:
                        imagem_data = st.session_state.imagens_salvas[analise["nome"]]
                        st.download_button(
                            label="📥",
                            data=imagem_data,
                            file_name=f"{analise['nome']}.jpg",
                            mime="image/jpeg",
                            key=f"download_btn_{analise_id}",
                            help="Baixar imagem",
                            use_container_width=True,
                        )
                    else:
                        st.button("📥", key=f"download_disabled_{analise_id}", disabled=True, help="Imagem não disponível", use_container_width=True)
                    
                    delete_key = f"delete_{analise_id}"
                    if st.button("❌", key=delete_key, help="Excluir análise", use_container_width=True):
                        # Marcar para exclusão no próximo rerun
                        st.session_state.delete_analise_id = analise_id
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
        # Armazena bytes e metadados no session_state para estabilidade entre reruns
        st.session_state.imagem_atual = uploaded_file
        try:
            b = uploaded_file.getvalue()
        except Exception:
            b = None
        st.session_state.imagem_atual_bytes = b
        st.session_state.imagem_atual_name = getattr(uploaded_file, "name", "upload.jpg")
        st.session_state.imagem_atual_type = getattr(uploaded_file, "type", "image/jpeg")

        col_img, col_info = st.columns([2, 1])
        with col_img:
            if st.session_state.imagem_atual_bytes:
                st.image(io.BytesIO(st.session_state.imagem_atual_bytes), caption="Imagem carregada", width='stretch')
            else:
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
            # Removido controle de modo (bbox/seg) da interface — modo fixo no cliente
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

    if st.session_state.imagem_atual_bytes is not None:
        st.markdown("### 🔍 Análise")
        # Valores padrão para processamento
        mode = "seg"  # modo fixo (remoção da opção bbox/seg da UI)
        conf = 0.25  # Valor fixo de confiança
        col_btn, col_status = st.columns([1, 2])
        with col_btn:
            if st.button("🚀 Contar Pessoas", type="primary", key="contar_pessoas_btn"):
                with st.spinner("Processando imagem na API..."):
                    try:
                        # Usa os bytes armazenados em session_state
                        img_bytes = st.session_state.imagem_atual_bytes
                        img_name = st.session_state.imagem_atual_name or "upload.jpg"
                        img_mime = st.session_state.imagem_atual_type or "image/jpeg"
                        files = {"file": (img_name, img_bytes, img_mime)}
                        params = {"mode": mode, "conf": conf}
                        resp = requests.post(f"{API_URL}/process", files=files, params=params, timeout=180)
                        if resp.status_code != 200:
                            st.session_state.resultado_contagem = None
                            st.error(f"Erro da API: {resp.status_code} - {resp.text}")
                        else:
                            duplicate = resp.headers.get("X-Duplicate", "false").lower() == "true"
                            img_id = resp.headers.get("X-Image-Id", "")
                            # guarda último id processado para permitir salvar/atualizar metadados
                            st.session_state.last_image_id = img_id
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
                            # Persistência local leve: salva também no diretório do sid
                            try:
                                # gera nome seguro para arquivo
                                safe_img_name = f"{nome_analise.replace(' ', '_')}.jpg"
                                img_path = user_dir / safe_img_name
                                img_path.write_bytes(annotated_bytes)
                                # atualiza metadata no objeto de análise (se houver)
                            except Exception:
                                pass
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
                    # prepara objeto de análise e persiste localmente por sid
                    nova_analise = {
                        "id": str(uuid.uuid4()),  # ID único para cada análise
                        "nome": nome_final,
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "pessoas": st.session_state.resultado_contagem,
                        "descricao": descricao if "descricao" in locals() else "",
                        "saved_image": None,
                    }
                    # prefer annotated image se disponível, senão imagem original
                    try:
                        if nome_analise in st.session_state.imagens_salvas:
                            img_bytes = st.session_state.imagens_salvas[nome_analise]
                        elif st.session_state.imagem_atual_bytes is not None:
                            img_bytes = st.session_state.imagem_atual_bytes
                        else:
                            img_bytes = None
                        if img_bytes:
                            safe_img_name = f"{nome_final.replace(' ', '_')}.jpg"
                            img_path = user_dir / safe_img_name
                            img_path.write_bytes(img_bytes)
                            nova_analise["saved_image"] = safe_img_name
                            st.session_state.imagens_salvas[nome_final] = img_bytes
                    except Exception:
                        # não falha a UI por erro de disco
                        pass

                    # Se o processamento anterior retornou um id no servidor, atualiza metadados via PATCH
                    try:
                        img_id_to_update = st.session_state.get("last_image_id")
                        if img_id_to_update:
                            headers = _auth_headers()
                            patch_body = {"title": nome_final, "description": nova_analise.get("descricao", "")}
                            requests.patch(f"{API_URL}/images/{img_id_to_update}", json=patch_body, headers=headers, timeout=5)
                    except Exception:
                        pass

                    st.session_state.analises_realizadas.append(nova_analise)

                    # salva metadata completa no disco para persistência entre reloads
                    try:
                        meta = {"analises": st.session_state.analises_realizadas}
                        with open(meta_file, "w", encoding="utf-8") as mf:
                            json.dump(meta, mf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

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

