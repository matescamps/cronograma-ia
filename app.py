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
        creds_info = st.secrets["gcp_service_account"]

        # Verifica se as credenciais foram coladas como uma string JSON no secrets.toml.
        if isinstance(creds_info, str):
            try:
                creds_dict = json.loads(creds_info)
            except json.JSONDecodeError:
                st.error("Erro Crítico: O formato das suas credenciais 'gcp_service_account' em secrets.toml parece ser uma string JSON inválida. Por favor, verifique se copiou o conteúdo do arquivo .json corretamente.")
                return None
        else:
            creds_dict = creds_info

        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro de Conexão com Google Sheets: Verifique seu arquivo 'secrets.toml'. Detalhes: {e}")
        return None

# --- Carregamento e Cache dos Dados da Planilha ---
@st.cache_data(ttl=60)
def load_data(_client, spreadsheet_id, sheet_tab_name):
    try:
        spreadsheet = _client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_tab_name) 
        df = pd.DataFrame(worksheet.get_all_records())
        
        # Tratamento de dados para garantir os tipos corretos
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        for col in df.columns:
            if 'Questões' in col or 'Dificuldade' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            if 'Teoria Feita' in col:
                df[col] = df[col].apply(lambda x: True if str(x).upper() == 'TRUE' else False)
            
            # --- CORREÇÃO APLICADA AQUI ---
            # Normaliza as colunas de porcentagem para o intervalo [0.0, 1.0] e garante o tipo float
            if '% Concluído' in col:
                # Limpa e converte para número
                df[col] = df[col].astype(str).str.replace('%', '', regex=False).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
                # Normaliza se o valor estiver em escala de 100 (ex: 75 -> 0.75)
                df.loc[df[col] > 1, col] = df.loc[df[col] > 1, col] / 100.0
                
                # Garante que o valor não ultrapasse 1.0
                df[col] = df[col].clip(0, 1)

                # Garante que o tipo final seja float, resolvendo o erro 'int64'
                df[col] = df[col].astype(float)


        return df, worksheet
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Erro: A aba '{sheet_tab_name}' não foi encontrada na sua planilha. Por favor, verifique o nome em secrets.toml.")
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
            "Authorization": "Bearer " + st.secrets["GROQ_API_KEY"],
            "Content-Type": "application/json"
        }
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        elif response.status_code == 401:
            st.error("Erro de Autenticação (401): Sua chave da Groq (GROQ_API_KEY) é inválida ou expirou. Por favor, gere uma nova chave no site da Groq e atualize seu arquivo 'secrets.toml'.")
            return "Erro de autenticação com a IA."
        else:
            st.warning(f"A IA não respondeu (Código: {response.status_code}). Verifique sua chave GROQ_API_KEY em 'secrets.toml'. Detalhes: {response.text}")
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

    spreadsheet_id = st.secrets["SPREADSHEET_ID_OR_URL"]
    sheet_tab_name = st.secrets["SHEET_TAB_NAME"]
    df, worksheet = load_data(client, spreadsheet_id, sheet_tab_name)

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
            
            progresso_manha = row.get('% Concluído (Manhã)', 0) * 100
            tarefa_manha = row.get('Atividade Detalhada (Manhã)', 'N/A')

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
                
                progresso = row.get(f'% Concluído ({periodo})', 0)
                cor_barra = "#1e8e3e" if progresso > 0.8 else "#f9ab00" if progresso > 0.4 else "#d93025"
                st.markdown(f'<style>.stProgress > div > div > div > div {{background-color: {cor_barra};}}</style>', unsafe_allow_html=True)
                st.progress(progresso)
                
                st.markdown('</div>', unsafe_allow_html=True)

    # --- LÓGICA PARA SALVAR DADOS (VERSÃO CORRIGIDA E COMPLETA) ---
    if st.button("✅ Salvar Progresso do Dia"):
        with st.spinner("Salvando na nuvem..."):
            row_index = df_usuario_hoje.index[0] + 2
            
            updates = []
            
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
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Não foi possível salvar. A conexão com a planilha falhou.")

if __name__ == "__main__":
    main()

