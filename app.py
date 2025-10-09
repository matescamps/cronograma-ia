# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import requests
import json
import time

# =============================================================================
# CONFIGURAÇÃO INICIAL E CONEXÕES
# =============================================================================

# Define o layout da página para "wide" para ocupar a tela inteira
st.set_page_config(layout="wide", page_title="Cronograma Inteligente")

# --- Conexão Segura com a API do Google Sheets ---
@st.cache_resource(ttl=600)
def connect_to_google_sheets():
    try:
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro de Conexão com Google Sheets: Verifique seu arquivo 'secrets.toml'. Detalhes: {e}")
        return None

# --- Carregamento e Cache dos Dados da Planilha ---
@st.cache_data(ttl=60)
def load_data(_client, spreadsheet_id):
    try:
        spreadsheet = _client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet("Schedule") # Nome da sua aba
        df = pd.DataFrame(worksheet.get_all_records())
        
        # Tratamento de dados para garantir os tipos corretos
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        for col in df.columns:
            if 'Questões' in col or 'Dificuldade' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            if 'Teoria Feita' in col:
                df[col] = df[col].apply(lambda x: True if str(x).upper() == 'TRUE' else False)
        return df, worksheet
    except gspread.exceptions.WorksheetNotFound:
        st.error("Erro: A aba 'Schedule' não foi encontrada na sua planilha. Por favor, verifique o nome.")
        return pd.DataFrame(), None
    except Exception as e:
        st.error(f"Erro ao carregar os dados da planilha: {e}")
        return pd.DataFrame(), None

# --- Conexão com a IA (Groq) ---
def call_groq_api(prompt):
    try:
        payload = {
            "model": "gemma2-9b-it",
            "messages": [{"role": "user", "content": prompt}]
        }
        headers = {
            "Authorization": "Bearer " + st.secrets["groq"]["api_key"],
            "Content-Type": "application/json"
        }
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            st.warning(f"A IA não respondeu (Código: {response.status_code}). Verifique sua chave da Groq em 'secrets.toml'.")
            return "Não foi possível obter um conselho da IA no momento."
    except Exception as e:
        st.error(f"Erro crítico na conexão com a IA: {e}")
        return "Erro de conexão com a IA."

# =============================================================================
# ESTILIZAÇÃO E COMPONENTES VISUAIS (CSS)
# =============================================================================

def load_css():
    st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem; padding-bottom: 2rem; padding-left: 5rem; padding-right: 5rem;
        }
        .study-card {
            background-color: #FFFFFF; border-radius: 15px; padding: 25px;
            margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            border: 1px solid #E0E0E0; transition: all 0.3s ease-in-out;
            animation: fadeIn 0.5s ease-out;
        }
        .study-card:hover {
            box-shadow: 0 8px 24px rgba(0,0,0,0.12); transform: translateY(-5px);
        }
        body[data-theme="dark"] .study-card {
            background-color: #2E2E2E; border: 1px solid #424242;
        }
        .stProgress > div > div > div > div { border-radius: 10px; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .avatar {
            vertical-align: middle; width: 50px; height: 50px;
            border-radius: 50%; margin-right: 15px;
        }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# LÓGICA PRINCIPAL DO APLICATIVO
# =============================================================================

def main():
    load_css()
    
    st.title("🚀 Cronograma de Estudos Inteligente")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        user = st.radio("Quem está estudando agora?", ["Mateus", "Ana"], horizontal=True, label_visibility="collapsed")

    avatar_url = "https://placehold.co/100x100/E8F0FE/1a73e8?text=M" if user == "Mateus" else "https://placehold.co/100x100/E6F4EA/1e8e3e?text=A"
    st.markdown(f"## <img src='{avatar_url}' class='avatar'>Bem-vindo(a), {user}!", unsafe_allow_html=True)
    
    client = connect_to_google_sheets()
    if not client: return

    spreadsheet_id = st.secrets["google_sheets"]["spreadsheet_id"]
    df, worksheet = load_data(client, spreadsheet_id)

    if df.empty: return

    hoje = datetime.now().date()
    df_hoje = df[df['Data'].dt.date == hoje]
    df_usuario_hoje = df_hoje[(df_hoje['Aluno(a)'] == user) | (df_hoje['Aluno(a)'] == 'Ambos')]

    if df_usuario_hoje.empty:
        st.info("Você não tem tarefas agendadas para hoje. Aproveite para descansar ou revisar pendências!")
        return

    row = df_usuario_hoje.iloc[0]

    # --- BRIEFING DA IA ---
    if 'briefing' not in st.session_state or st.session_state.user != user:
        with st.spinner("🧠 Coach IA preparando seu briefing do dia..."):
            hora_atual = datetime.now().hour
            saudacao = "Bom dia" if 5 <= hora_atual < 12 else "Boa tarde" if hora_atual < 18 else "Boa noite"
            
            progresso_manha = row['% Concluído (Manhã)'] * 100 if '% Concluído (Manhã)' in row else 0
            tarefa_manha = row['Atividade Detalhada (Manhã)']

            prompt = f"""
            Você é um coach de vestibulandos de medicina. O momento atual é {saudacao}. 
            Prepare um briefing curto e motivador para {user}.
            Progresso de {user} Hoje: Tarefa da Manhã: {tarefa_manha}, Progresso da Manhã: {progresso_manha:.0f}%.
            Sua Missão: Se for "Bom dia", dê uma dica para a tarefa da manhã. Se for "Boa tarde" ou "Boa noite", comente o progresso da manhã e dê o foco para o próximo período. Seja direto (2-3 frases).
            """
            st.session_state.briefing = call_groq_api(prompt)
            st.session_state.user = user

    st.info(f"**💡 Coach IA diz:** {st.session_state.briefing}")

    st.header("Seu Plano de Batalha para Hoje")
    
    col_manha, col_tarde, col_noite = st.columns(3)
    periodos = {"Manhã": col_manha, "Tarde": col_tarde, "Noite": col_noite}
    
    for periodo, coluna in periodos.items():
        with coluna:
            with st.container():
                st.markdown('<div class="study-card">', unsafe_allow_html=True)
                
                mat_col, ativ_col, teoria_col, plan_col, feitas_col = (
                    f'Matéria ({periodo})', f'Atividade Detalhada ({periodo})',
                    f'Teoria Feita ({periodo})', f'Questões Planejadas ({periodo})',
                    f'Questões Feitas ({periodo})'
                )
                
                st.subheader(row[mat_col])
                st.markdown(row[ativ_col])
                
                st.checkbox("Teoria Concluída", value=bool(row[teoria_col]), key=f"teoria_{periodo}")
                
                if row[plan_col] > 0:
                    st.number_input(
                        f"Questões Feitas (de {row[plan_col]})", 
                        min_value=0, max_value=int(row[plan_col]), 
                        value=int(row[feitas_col]), key=f"feitas_{periodo}"
                    )
                
                progresso = row[f'% Concluído ({periodo})']
                cor_barra = "#1e8e3e" if progresso > 0.8 else "#f9ab00" if progresso > 0.4 else "#d93025"
                st.markdown(f'<style>.stProgress > div > div > div > div {{background-color: {cor_barra};}}</style>', unsafe_allow_html=True)
                st.progress(progresso)
                
                st.markdown('</div>', unsafe_allow_html=True)

    # --- LÓGICA PARA SALVAR DADOS (VERSÃO CORRIGIDA E COMPLETA) ---
    if st.button("✅ Salvar Progresso do Dia"):
        with st.spinner("Salvando na nuvem..."):
            row_index = df_usuario_hoje.index[0] + 2
            
            updates = []
            
            # Mapeamento de colunas da planilha
            col_map = {
                'Manhã': {'teoria': 'I', 'feitas': 'K'},
                'Tarde': {'teoria': 'O', 'feitas': 'Q'},
                'Noite': {'teoria': 'U', 'feitas': 'W'}
            }
            
            for periodo, cols in col_map.items():
                teoria_val = st.session_state[f"teoria_{periodo}"]
                feitas_val = row[f'Questões Feitas ({periodo})']
                if f"feitas_{periodo}" in st.session_state:
                    feitas_val = st.session_state[f"feitas_{periodo}"]
                
                updates.append({'range': f"{cols['teoria']}{row_index}", 'values': [[teoria_val]]})
                updates.append({'range': f"{cols['feitas']}{row_index}", 'values': [[int(feitas_val)]]})

            if worksheet:
                worksheet.batch_update(updates)
                st.success("Progresso salvo com sucesso!")
                time.sleep(1)
                st.cache_data.clear() # Limpa o cache para forçar a releitura dos dados
                st.rerun()
            else:
                st.error("Não foi possível salvar. A conexão com a planilha falhou.")

if __name__ == "__main__":
    main()

