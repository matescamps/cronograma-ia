# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
import requests
import json
import time
import base64

# =============================================================================
# CONFIGURAÇÃO INICIAL
# =============================================================================

st.set_page_config(
    layout="wide", 
    page_title="StudyFlow Pro",
    page_icon="🎓",
    initial_sidebar_state="collapsed"
)

# =============================================================================
# FUNÇÕES DE CONEXÃO (MANTIDAS)
# =============================================================================

@st.cache_resource(ttl=600)
def connect_to_google_sheets():
    try:
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]

        if isinstance(creds_info, str):
            try:
                creds_dict = json.loads(creds_info)
            except json.JSONDecodeError:
                st.error("Erro nas credenciais do Google Sheets")
                return None
        else:
            creds_dict = creds_info

        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

@st.cache_data(ttl=60)
def load_data(_client, spreadsheet_id, sheet_tab_name):
    try:
        spreadsheet = _client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_tab_name) 
        df = pd.DataFrame(worksheet.get_all_records())
        
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        for col in df.columns:
            if 'Questões' in col or 'Dificuldade' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            if 'Teoria Feita' in col:
                df[col] = df[col].apply(lambda x: True if str(x).upper() == 'TRUE' else False)
            if '% Concluído' in col:
                df[col] = df[col].astype(str).str.replace('%', '', regex=False).str.replace(',', '.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                df.loc[df[col] > 1, col] = df.loc[df[col] > 1, col] / 100.0
                df[col] = df[col].clip(0, 1)
                df[col] = df[col].astype(float)

        return df, worksheet
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame(), None

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
        else:
            return "Coach IA temporariamente indisponível."
    except Exception as e:
        return "Erro ao conectar com Coach IA."

# =============================================================================
# CSS ULTRA MODERNO E PROFISSIONAL
# =============================================================================

def load_premium_css():
    st.markdown("""
    <style>
        /* Imports de fontes modernas */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Poppins:wght@600;700;800&display=swap');
        
        /* Reset e Base */
        * {
            font-family: 'Inter', sans-serif;
        }
        
        .block-container {
            padding: 1rem 3rem 3rem 3rem !important;
            max-width: 100% !important;
        }
        
        /* Ocultar elementos padrão do Streamlit */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Background animado */
        .stApp {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            background-attachment: fixed;
        }
        
        /* =========================
           TELA DE LOGIN
        ========================= */
        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 80vh;
            animation: fadeIn 0.8s ease-out;
        }
        
        .login-card {
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(20px);
            border-radius: 30px;
            padding: 60px 80px;
            box-shadow: 0 30px 90px rgba(0, 0, 0, 0.3);
            text-align: center;
            max-width: 550px;
            width: 100%;
            animation: slideUp 0.8s ease-out;
        }
        
        .login-logo {
            font-size: 80px;
            margin-bottom: 20px;
            animation: bounce 2s infinite;
        }
        
        .login-title {
            font-family: 'Poppins', sans-serif;
            font-size: 42px;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 15px;
        }
        
        .login-subtitle {
            font-size: 18px;
            color: #666;
            margin-bottom: 50px;
            font-weight: 400;
        }
        
        .user-select-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            padding: 30px;
            margin: 15px 0;
            cursor: pointer;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
        }
        
        .user-select-card:hover {
            transform: translateY(-10px) scale(1.02);
            box-shadow: 0 20px 50px rgba(102, 126, 234, 0.5);
        }
        
        .user-avatar {
            font-size: 70px;
            margin-bottom: 15px;
            filter: drop-shadow(0 5px 15px rgba(0,0,0,0.2));
        }
        
        .user-name {
            font-family: 'Poppins', sans-serif;
            font-size: 28px;
            font-weight: 700;
            color: white;
            margin: 0;
            text-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        
        /* =========================
           DASHBOARD PRINCIPAL
        ========================= */
        .dashboard-header {
            background: white;
            border-radius: 25px;
            padding: 35px 45px;
            margin-bottom: 35px;
            box-shadow: 0 15px 45px rgba(0,0,0,0.1);
            animation: slideDown 0.6s ease-out;
        }
        
        .user-greeting {
            display: flex;
            align-items: center;
            gap: 25px;
        }
        
        .user-avatar-main {
            font-size: 80px;
            filter: drop-shadow(0 5px 15px rgba(0,0,0,0.15));
        }
        
        .greeting-text h1 {
            font-family: 'Poppins', sans-serif;
            font-size: 38px;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0 0 8px 0;
        }
        
        .greeting-text p {
            font-size: 18px;
            color: #666;
            margin: 0;
        }
        
        .logout-btn {
            margin-left: auto;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 5px 15px rgba(245, 87, 108, 0.3);
        }
        
        .logout-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(245, 87, 108, 0.5);
        }
        
        /* Coach IA Card */
        .coach-card {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            border-radius: 25px;
            padding: 30px 40px;
            margin-bottom: 35px;
            box-shadow: 0 15px 45px rgba(245, 87, 108, 0.3);
            color: white;
            animation: fadeIn 0.8s ease-out 0.2s both;
        }
        
        .coach-icon {
            font-size: 50px;
            margin-bottom: 15px;
            filter: drop-shadow(0 5px 15px rgba(0,0,0,0.2));
        }
        
        .coach-title {
            font-family: 'Poppins', sans-serif;
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 15px;
            text-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        
        .coach-message {
            font-size: 17px;
            line-height: 1.7;
            font-weight: 400;
        }
        
        /* Section Title */
        .section-title {
            font-family: 'Poppins', sans-serif;
            font-size: 32px;
            font-weight: 800;
            color: white;
            margin: 40px 0 25px 0;
            text-align: center;
            text-shadow: 0 3px 15px rgba(0,0,0,0.3);
        }
        
        /* Study Cards Premium */
        .study-card-premium {
            background: white;
            border-radius: 25px;
            padding: 35px;
            height: 100%;
            box-shadow: 0 15px 45px rgba(0,0,0,0.1);
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            position: relative;
            overflow: hidden;
            animation: fadeInUp 0.6s ease-out;
        }
        
        .study-card-premium::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        }
        
        .study-card-premium:hover {
            transform: translateY(-10px);
            box-shadow: 0 25px 65px rgba(0,0,0,0.2);
        }
        
        .period-badge {
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 14px;
            margin-bottom: 20px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .badge-manha {
            background: linear-gradient(135deg, #FA8BFF 0%, #2BD2FF 100%);
            color: white;
        }
        
        .badge-tarde {
            background: linear-gradient(135deg, #FDEB71 0%, #F8D800 100%);
            color: #333;
        }
        
        .badge-noite {
            background: linear-gradient(135deg, #4A00E0 0%, #8E2DE2 100%);
            color: white;
        }
        
        .subject-title {
            font-family: 'Poppins', sans-serif;
            font-size: 26px;
            font-weight: 700;
            color: #2D3748;
            margin-bottom: 15px;
        }
        
        .activity-description {
            font-size: 16px;
            color: #4A5568;
            line-height: 1.7;
            margin-bottom: 25px;
            padding-left: 15px;
            border-left: 3px solid #E2E8F0;
        }
        
        .stats-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 25px 0;
        }
        
        .stat-box {
            background: linear-gradient(135deg, #f6f8fb 0%, #e9ecef 100%);
            padding: 15px;
            border-radius: 15px;
            text-align: center;
        }
        
        .stat-label {
            font-size: 13px;
            color: #718096;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: 800;
            color: #2D3748;
        }
        
        .progress-container {
            margin-top: 25px;
        }
        
        .progress-label {
            font-size: 14px;
            font-weight: 600;
            color: #4A5568;
            margin-bottom: 10px;
        }
        
        .progress-bar-custom {
            width: 100%;
            height: 14px;
            background: #E2E8F0;
            border-radius: 20px;
            overflow: hidden;
            position: relative;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            transition: width 1s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            box-shadow: 0 2px 10px rgba(102, 126, 234, 0.5);
        }
        
        /* Save Button */
        .save-button-container {
            text-align: center;
            margin: 50px 0;
        }
        
        /* Checkbox customizado */
        .stCheckbox {
            margin: 20px 0;
        }
        
        /* Number input customizado */
        .stNumberInput {
            margin: 15px 0;
        }
        
        /* Animações */
        @keyframes fadeIn {
            from {
                opacity: 0;
            }
            to {
                opacity: 1;
            }
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(50px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes bounce {
            0%, 100% {
                transform: translateY(0);
            }
            50% {
                transform: translateY(-10px);
            }
        }
        
        /* Responsividade */
        @media (max-width: 768px) {
            .login-card {
                padding: 40px 30px;
            }
            
            .dashboard-header {
                padding: 25px 20px;
            }
            
            .user-greeting {
                flex-direction: column;
                text-align: center;
            }
            
            .study-card-premium {
                padding: 25px 20px;
            }
        }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# TELA DE LOGIN
# =============================================================================

def show_login_screen():
    st.markdown("""
    <div class="login-container">
        <div class="login-card">
            <div class="login-logo">🎓</div>
            <h1 class="login-title">StudyFlow Pro</h1>
            <p class="login-subtitle">Seu cronograma inteligente de estudos</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        col_mateus, col_ana = st.columns(2)
        
        with col_mateus:
            if st.button("👨‍🎓", key="mateus", use_container_width=True):
                st.session_state.logged_user = "Mateus"
                st.session_state.login_time = datetime.now()
                st.rerun()
            st.markdown("<p style='text-align:center; font-size:22px; font-weight:700; color:white; margin-top:10px;'>Mateus</p>", unsafe_allow_html=True)
        
        with col_ana:
            if st.button("👩‍🎓", key="ana", use_container_width=True):
                st.session_state.logged_user = "Ana"
                st.session_state.login_time = datetime.now()
                st.rerun()
            st.markdown("<p style='text-align:center; font-size:22px; font-weight:700; color:white; margin-top:10px;'>Ana</p>", unsafe_allow_html=True)

# =============================================================================
# DASHBOARD PRINCIPAL
# =============================================================================

def show_dashboard(user):
    # Header com saudação
    hora_atual = datetime.now().hour
    saudacao = "Bom dia" if 5 <= hora_atual < 12 else "Boa tarde" if hora_atual < 18 else "Boa noite"
    emoji_user = "👨‍🎓" if user == "Mateus" else "👩‍🎓"
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(f"""
        <div class="dashboard-header">
            <div class="user-greeting">
                <div class="user-avatar-main">{emoji_user}</div>
                <div class="greeting-text">
                    <h1>{saudacao}, {user}!</h1>
                    <p>{datetime.now().strftime('%d de %B de %Y')}</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 Sair", use_container_width=True, type="secondary"):
            del st.session_state.logged_user
            st.rerun()
    
    # Conectar e carregar dados
    client = connect_to_google_sheets()
    if not client:
        st.error("Erro ao conectar com Google Sheets")
        return

    spreadsheet_id = st.secrets["SPREADSHEET_ID_OR_URL"]
    sheet_tab_name = st.secrets["SHEET_TAB_NAME"]
    df, worksheet = load_data(client, spreadsheet_id, sheet_tab_name)

    if df.empty:
        st.warning("Nenhum dado encontrado na planilha")
        return

    # Filtrar dados do dia
    hoje = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    df_hoje = df[df['Data'].dt.date == hoje]
    df_usuario_hoje = df_hoje[(df_hoje['Aluno(a)'] == user) | (df_hoje['Aluno(a)'] == 'Ambos')]

    if df_usuario_hoje.empty:
        st.markdown("""
        <div class="coach-card">
            <div class="coach-icon">🎉</div>
            <div class="coach-title">Dia Livre!</div>
            <div class="coach-message">Você não tem tarefas agendadas para hoje. Aproveite para descansar ou revisar conteúdos anteriores!</div>
        </div>
        """, unsafe_allow_html=True)
        return

    row = df_usuario_hoje.iloc[0]

    # Briefing da IA
    if 'briefing' not in st.session_state or st.session_state.get('briefing_user') != user:
        with st.spinner("🧠 Coach IA preparando seu briefing..."):
            progresso_manha = row.get('% Concluído (Manhã)', 0) * 100
            tarefa_manha = row.get('Atividade Detalhada (Manhã)', 'N/A')

            prompt = f"""
            Você é um coach motivador para vestibulandos de medicina. {saudacao}!
            Prepare um briefing curto e energético para {user}.
            Progresso de hoje - Manhã: {tarefa_manha} ({progresso_manha:.0f}% concluído).
            
            Regras:
            - Máximo 3 frases
            - Seja motivador e específico
            - Se for manhã, foque na tarefa. Se tarde/noite, comente o progresso e próximos passos.
            """
            st.session_state.briefing = call_groq_api(prompt)
            st.session_state.briefing_user = user

    st.markdown(f"""
    <div class="coach-card">
        <div class="coach-icon">🤖</div>
        <div class="coach-title">Coach IA</div>
        <div class="coach-message">{st.session_state.briefing}</div>
    </div>
    """, unsafe_allow_html=True)

    # Título da seção
    st.markdown('<h2 class="section-title">📚 Seu Plano de Hoje</h2>', unsafe_allow_html=True)
    
    # Cards de estudo
    col_manha, col_tarde, col_noite = st.columns(3)
    periodos_config = {
        "Manhã": {"col": col_manha, "badge": "badge-manha", "emoji": "🌅"},
        "Tarde": {"col": col_tarde, "badge": "badge-tarde", "emoji": "☀️"},
        "Noite": {"col": col_noite, "badge": "badge-noite", "emoji": "🌙"}
    }
    
    for periodo, config in periodos_config.items():
        with config["col"]:
            mat_col = f'Matéria ({periodo})'
            ativ_col = f'Atividade Detalhada ({periodo})'
            teoria_col = f'Teoria Feita ({periodo})'
            plan_col = f'Questões Planejadas ({periodo})'
            feitas_col = f'Questões Feitas ({periodo})'
            prog_col = f'% Concluído ({periodo})'
            
            materia = row[mat_col]
            atividade = row[ativ_col]
            teoria = bool(row[teoria_col])
            planejadas = int(row[plan_col])
            feitas = int(row[feitas_col])
            progresso = float(row.get(prog_col, 0))
            
            st.markdown(f"""
            <div class="study-card-premium">
                <span class="period-badge {config['badge']}">{config['emoji']} {periodo}</span>
                <h3 class="subject-title">{materia}</h3>
                <p class="activity-description">{atividade}</p>
            """, unsafe_allow_html=True)
            
            # Checkbox de teoria
            st.checkbox(
                "✅ Teoria Concluída", 
                value=teoria, 
                key=f"teoria_{periodo}",
                help=f"Marque quando terminar a teoria de {periodo.lower()}"
            )
            
            # Input de questões
            if planejadas > 0:
                st.number_input(
                    f"Questões Resolvidas",
                    min_value=0,
                    max_value=planejadas,
                    value=feitas,
                    key=f"feitas_{periodo}",
                    help=f"Você planejou fazer {planejadas} questões"
                )
                
                st.markdown(f"""
                <div class="stats-row">
                    <div class="stat-box">
                        <div class="stat-label">Planejadas</div>
                        <div class="stat-value">{planejadas}</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Concluídas</div>
                        <div class="stat-value">{feitas}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Barra de progresso
            st.markdown(f"""
            <div class="progress-container">
                <div class="progress-label">Progresso do {periodo}: {progresso*100:.0f}%</div>
                <div class="progress-bar-custom">
                    <div class="progress-fill" style="width: {progresso*100}%"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)

    # Botão de salvar
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("💾 Salvar Progresso", use_container_width=True, type="primary"):
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
                    st.success("✅ Progresso salvo com sucesso!")
                    time.sleep(1.5)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Erro ao salvar. Tente novamente.")

# =============================================================================
# MAIN
# =============================================================================

def main():
    load_premium_css()
    
    # Inicializar session state
    if 'logged_user' not in st.session_state:
        st.session_state.logged_user = None
    
    # Verificar login
    if st.session_state.logged_user is None:
        show_login_screen()
    else:
        show_dashboard(st.session_state.logged_user)

if __name__ == "__main__":
    main()
