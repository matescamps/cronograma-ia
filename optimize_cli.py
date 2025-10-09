# -*- coding: utf-8 -*-
"""
Cronograma Ana&Mateus
App Streamlit IA-first para gerenciamento de cronograma de estudos.
Requisitos: st.secrets com chaves:
  - gcp_service_account (json string ou dict)
  - SPREADSHEET_ID_OR_URL
  - SHEET_TAB_NAME
  - GROQ_API_KEY (opcional, se quiser IA)
  - GROQ_API_URL (opcional - endpoint)
"""
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
import requests
import json
import time
from typing import Tuple, Optional, List, Any
import matplotlib.pyplot as plt
import numpy as np
import uuid

# =============================================================================
# CONFIGURAÇÃO INICIAL
# =============================================================================

st.set_page_config(
    layout="wide",
    page_title="Cronograma Ana&Mateus",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# =============================================================================
# UTILIDADES E CONEXÃO
# =============================================================================

@st.cache_resource(ttl=600, show_spinner=False)
def connect_to_google_sheets():
    """
    Conexão robusta com Google Sheets; aceita JSON com quebras escapadas.
    Retorna cliente gspread ou None.
    """
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_info = st.secrets.get("gcp_service_account", None)
        if not creds_info:
            st.error("❌ Secrets GCP ausente: defina 'gcp_service_account' em st.secrets.")
            return None

        # suporta string JSON com \n escapados ou dicionário
        if isinstance(creds_info, str):
            try:
                creds_dict = json.loads(creds_info)
            except json.JSONDecodeError:
                try:
                    creds_dict = json.loads(creds_info.replace('\\\\n', '\\n'))
                except Exception:
                    st.error("❌ Formato inválido em gcp_service_account. Verifique o JSON em secrets.")
                    return None
        else:
            creds_dict = dict(creds_info)

        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.Client(auth=creds)
        client.session = gspread.http_client.HTTPClient(auth=creds)
        return client
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao Google Sheets: {str(e)[:300]}")
        return None

@st.cache_data(ttl=60, show_spinner=False)
def load_data(client, spreadsheet_id: str, sheet_tab_name: str) -> Tuple[pd.DataFrame, Optional[Any], List[str]]:
    """
    Carrega e normaliza os dados da planilha.
    Retorna (df, worksheet, headers_list).
    """
    try:
        if not client:
            return pd.DataFrame(), None, []
        # tenta abrir por key, se falhar tenta por url
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = client.open_by_url(spreadsheet_id)

        worksheet = spreadsheet.worksheet(sheet_tab_name)
        all_values = worksheet.get_all_values()
        if not all_values or len(all_values) < 1:
            return pd.DataFrame(), worksheet, []

        headers = all_values[0]
        data = all_values[1:] if len(all_values) > 1 else []
        df = pd.DataFrame(data, columns=headers)

        # garantir colunas fornecidas por você (preencher vazios se necessário)
        required = [
            "Data","Dificuldade (1-5)","Status","Aluno(a)","Dia da Semana","Fase do Plano",
            "Matéria (Manhã)","Atividade Detalhada (Manhã)","Teoria Feita (Manhã)","Questões Planejadas (Manhã)",
            "Questões Feitas (Manhã)","% Concluído (Manhã)","Matéria (Tarde)","Atividade Detalhada (Tarde)","Teoria Feita (Tarde)",
            "Questões Planejadas (Tarde)","Questões Feitas (Tarde)","% Concluído (Tarde)","Matéria (Noite)","Atividade Detalhada (Noite)",
            "Teoria Feita (Noite)","Questões Planejadas (Noite)","Questões Feitas (Noite)","% Concluído (Noite)","Exame",
            "Alerta/Comentário","Situação","Prioridade"
        ]
        for c in required:
            if c not in df.columns:
                df[c] = ""

        # coluna ID: se existir no cabeçalho, ok; senão não cria aqui (função separada fará isso)
        # conversões e normalizações
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        df['Dificuldade (1-5)'] = pd.to_numeric(df['Dificuldade (1-5)'], errors='coerce').fillna(0).astype(int)
        for col in df.columns:
            if 'Questões' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            if '% Concluído' in col:
                s = df[col].astype(str).str.replace('%','').str.replace(',','.').str.strip()
                s = pd.to_numeric(s, errors='coerce').fillna(0.0)
                mask = s > 1.0
                s.loc[mask] = s.loc[mask] / 100.0
                df[col] = s.clip(0.0, 1.0)
            if 'Teoria Feita' in col:
                df[col] = df[col].astype(str).str.upper().isin(['TRUE','VERDADEIRO','1','SIM'])

        return df, worksheet, headers

    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ Aba '{sheet_tab_name}' não encontrada!")
        return pd.DataFrame(), None, []
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {str(e)[:200]}")
        return pd.DataFrame(), None, []

# =============================================================================
# FUNÇÕES IA (Groq) E HELPERS
# =============================================================================

def call_groq_api(prompt: str, max_retries: int = 2) -> str:
    """
    Chamada robusta para Groq API. Usa st.secrets['GROQ_API_URL'] se presente.
    Se GROQ_API_KEY ausente, retorna mensagem indicando isso.
    """
    groq_key = st.secrets.get('GROQ_API_KEY', None)
    if not groq_key:
        return "⚠️ GROQ API Key ausente em st.secrets."

    groq_url = st.secrets.get('GROQ_API_URL', "").strip()
    # montar endpoint
    if groq_url:
        endpoint = groq_url
        # heurística: se endpoint parece raiz, acrescenta /chat/completions
        if endpoint.endswith('/v1') or endpoint.endswith('/v1/'):
            endpoint = endpoint.rstrip('/') + "/chat/completions"
    else:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"

    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gemma2-9b-it",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 700
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                j = resp.json()
                choices = j.get('choices') or []
                if choices and isinstance(choices, list):
                    first = choices[0]
                    if isinstance(first, dict):
                        if 'message' in first and isinstance(first['message'], dict) and 'content' in first['message']:
                            return first['message']['content']
                        if 'text' in first:
                            return first['text']
                # fallback: return primeiro campo textual encontrado ou json truncado
                text = json.dumps(j)[:2000]
                return text
            elif resp.status_code == 401:
                return "⚠️ API Key inválida. Verifique suas credenciais."
            else:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return f"⚠️ Erro IA {resp.status_code}: {resp.text[:300]}"
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                continue
            return "⚠️ Timeout na conexão com IA."
        except Exception as e:
            return f"⚠️ Erro: {str(e)[:200]}"
    return "⚠️ Não foi possível conectar com a IA."

def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        try:
            return int(float(str(x).replace(',', '.')))
        except Exception:
            return default

def build_activity_summary_prompt(row, period_label: str) -> str:
    subj = row.get(f"Matéria ({period_label})", "") or row.get(f"Matéria ({period_label})", "")
    act = row.get(f"Atividade Detalhada ({period_label})", "")
    exam = row.get("Exame", "")
    difficulty = int(row.get("Dificuldade (1-5)", 0) or 0)
    prompt = (
        f"Você é um coach de estudos. Resuma em 1 parágrafo e gere 3 passos práticos para estudar:"
        f"\nMatéria: {subj}\nAtividade: {act}\nExame: {exam}\nDificuldade (1-5): {difficulty}\n"
        "Entrega: 1 parágrafo + 'Plano: 1) ... 2) ... 3) ...' — objetivo prático e direto."
    )
    return prompt

def generate_quiz_prompt(row, period_label: str, num_questions: int = 3) -> str:
    subj = row.get(f"Matéria ({period_label})", "")
    desc = row.get(f"Atividade Detalhada ({period_label})", "")
    prompt = (
        f"Crie um mini-quiz de {num_questions} questões sobre '{subj}' com foco em {desc}. "
        "Forneça: número da questão, enunciado, 4 alternativas (A-D), e coloque a letra da resposta correta no final em 'Gabarito:'. "
        "Responda em português."
    )
    return prompt

# =============================================================================
# FUNÇÕES DE INTERAÇÃO COM A PLANILHA
# =============================================================================

def try_update_cell(worksheet, row_idx: int, col_idx: int, value) -> bool:
    try:
        worksheet.update_cell(int(row_idx), int(col_idx), str(value))
        return True
    except Exception as e:
        st.warning(f"⚠️ Falha ao atualizar célula (r{row_idx} c{col_idx}): {str(e)[:150]}")
        return False

def find_row_index_for_item(worksheet, target_date: datetime, aluno: str, atividade_hint: str) -> Optional[int]:
    """
    Heurística: procura a linha que combina Data + Aluno(a) + Atividade Detalhada (qualquer período).
    Retorna índice (1-based) ou None.
    """
    try:
        all_values = worksheet.get_all_values()
        if not all_values or len(all_values) < 1:
            return None
        headers = all_values[0]
        data_rows = all_values[1:]

        def idx_or_none(name):
            try:
                return headers.index(name)
            except ValueError:
                return None

        col_data = idx_or_none("Data")
        col_aluno = idx_or_none("Aluno(a)")
        # prefer Atividade Detalhada (Manhã/Tarde/Noite)
        activity_cols = ["Atividade Detalhada (Manhã)", "Atividade Detalhada (Tarde)", "Atividade Detalhada (Noite)"]
        col_ativ = None
        for c in activity_cols:
            if c in headers:
                col_ativ = headers.index(c)
                break

        for i, row in enumerate(data_rows, start=2):
            match = True
            if col_data is not None and target_date is not None and not pd.isna(target_date):
                try:
                    cell_date = pd.to_datetime(row[col_data], format='%d/%m/%Y', errors='coerce')
                    if pd.isna(cell_date) or cell_date.date() != target_date.date():
                        match = False
                except Exception:
                    match = False
            if match and col_aluno is not None:
                if str(row[col_aluno]).strip().lower() != str(aluno).strip().lower():
                    match = False
            if match and col_ativ is not None and atividade_hint:
                # se a atividade hint está contida no cell => match
                cell_ativ = str(row[col_ativ]).strip().lower()
                if atividade_hint and atividade_hint.strip():
                    if atividade_hint.strip().lower() not in cell_ativ:
                        # permitir parcial: se cell_ativ vazio, não match
                        if cell_ativ == "":
                            match = False
                        else:
                            # ainda considerar match se partes baterem
                            if len(set(atividade_hint.split()) & set(cell_ativ.split())) == 0:
                                match = False
            if match:
                return i
        return None
    except Exception as e:
        st.warning(f"⚠️ Erro ao buscar linha: {str(e)[:150]}")
        return None

def update_sheet_mark_done(worksheet, df_row, headers) -> bool:
    """
    Marca % Concluído (Manhã/Tarde/Noite) = 100% e registra Hora Conclusão (criando a coluna se necessário).
    Retorna True se qualquer atualização foi realizada.
    """
    try:
        if worksheet is None or df_row is None:
            return False

        target_date = df_row.get('Data')
        aluno = str(df_row.get('Aluno(a)', '')).strip()
        atividade_hint = (str(df_row.get('Atividade Detalhada (Manhã)', '') or
                             df_row.get('Atividade Detalhada (Tarde)', '') or
                             df_row.get('Atividade Detalhada (Noite)', ''))).strip()

        row_idx = find_row_index_for_item(worksheet, target_date, aluno, atividade_hint)
        if not row_idx:
            return False

        updated = False
        # atualiza % Concluído por período
        for period in ["Manhã", "Tarde", "Noite"]:
            col_name = f"% Concluído ({period})"
            if col_name in headers:
                col_idx = headers.index(col_name) + 1
                success = try_update_cell(worksheet, row_idx, col_idx, "100%")
                updated = updated or success

        # garantir coluna Hora Conclusão (criar se não existir)
        if 'Hora Conclusão' not in headers:
            try:
                first_row = worksheet.row_values(1)
                # evitar duplicar se já houver coluna vazia no final
                first_row.append('Hora Conclusão')
                worksheet.update('1:1', [first_row])
                headers.append('Hora Conclusão')
            except Exception:
                # se falhar ao criar header, seguimos sem hora
                pass

        if 'Hora Conclusão' in headers:
            col_hora_idx = headers.index('Hora Conclusão') + 1
            hora_atual = datetime.now().strftime('%H:%M:%S')
            if try_update_cell(worksheet, row_idx, col_hora_idx, hora_atual):
                updated = True

        return updated
    except Exception as e:
        st.error(f"❌ Falha ao atualizar planilha: {str(e)[:200]}")
        return False

def ensure_unique_id_column(worksheet, headers) -> List[str]:
    """
    Garante que exista coluna 'ID' no cabeçalho e que cada linha tenha ID único.
    Retorna headers atualizados.
    """
    try:
        if 'ID' in headers:
            # nada a fazer aqui (IDs existentes devem estar)
            return headers
        # adicionar coluna ID ao cabeçalho
        first_row = worksheet.row_values(1)
        first_row.append('ID')
        worksheet.update('1:1', [first_row])
        # agora popular IDs nas linhas que não tiverem
        all_values = worksheet.get_all_values()
        headers_new = all_values[0]
        id_idx = headers_new.index('ID')
        data_rows = all_values[1:]
        updates = []
        for i, row in enumerate(data_rows, start=2):
            # se célula vazia, gerar uuid curto
            try:
                current = row[id_idx] if len(row) > id_idx else ""
            except Exception:
                current = ""
            if not current or str(current).strip() == "":
                new_id = str(uuid.uuid4())[:8]
                updates.append((i, id_idx+1, new_id))
        # aplicar updates (um a um para evitar grandes sobrecargas)
        for r, c, val in updates:
            try:
                worksheet.update_cell(r, c, val)
            except Exception:
                # tentar continuar mesmo se falhar
                pass
        # recarregar headers
        all_values = worksheet.get_all_values()
        return all_values[0]
    except Exception as e:
        st.warning(f"⚠️ Erro ao garantir coluna ID: {str(e)[:150]}")
        return headers

# =============================================================================
# REAGENDADOR INTELIGENTE
# =============================================================================

def smart_reschedule(df: pd.DataFrame, worksheet, headers, aluno: str, pct_threshold: float = 0.5, max_push_days=7) -> dict:
    """
    Tenta reagendar tarefas com % concluído abaixo do threshold.
    Retorna relatório simples.
    """
    report = {"moved": 0, "failed": 0, "details": []}
    try:
        df_copy = df.copy()
        for idx, row in df_copy.iterrows():
            if row.get("Aluno(a)") not in [aluno, "Ambos"]:
                continue
            date = row.get("Data")
            if pd.isna(date):
                continue
            for period in ["Manhã", "Tarde", "Noite"]:
                pct_col = f"% Concluído ({period})"
                if pct_col not in df.columns:
                    continue
                try:
                    pct = float(row.get(pct_col, 0.0) or 0.0)
                except Exception:
                    pct = 0.0
                if pct < pct_threshold:
                    pushed = False
                    for d in range(1, max_push_days+1):
                        new_date = (date + timedelta(days=d)).date()
                        exists = ((df['Data'].dt.date == new_date) & ((df['Aluno(a)'] == aluno) | (df['Aluno(a)'] == 'Ambos'))).any()
                        if not exists:
                            row_idx = find_row_index_for_item(worksheet, date, row.get("Aluno(a)"), row.get(f"Atividade Detalhada ({period})", ""))
                            if row_idx:
                                try:
                                    headers_list = headers
                                    col_idx = headers_list.index("Data") + 1
                                    success = try_update_cell(worksheet, row_idx, col_idx, new_date.strftime('%d/%m/%Y'))
                                    if success:
                                        report["moved"] += 1
                                        report["details"].append(f"{row.get('Aluno(a)')} {period} {date.strftime('%d/%m/%Y')} -> {new_date.strftime('%d/%m/%Y')}")
                                        pushed = True
                                        break
                                    else:
                                        report["failed"] += 1
                                        report["details"].append(f"Falha mover {row.get('Aluno(a)')} {period} {date.strftime('%d/%m/%Y')}")
                                        pushed = False
                                        break
                                except Exception as e:
                                    report["failed"] += 1
                                    report["details"].append(f"Erro: {str(e)[:120]}")
                                    pushed = False
                                    break
                            else:
                                report["failed"] += 1
                                report["details"].append(f"Não encontrou linha para {row.get('Aluno(a)')} {period} {date.strftime('%d/%m/%Y')}")
                                pushed = False
                                break
                    # fim tentativa dias
    except Exception as e:
        report["failed"] += 1
        report["details"].append(f"Erro geral: {str(e)[:150]}")
    return report

# =============================================================================
# ANALYTICS RÁPIDOS
# =============================================================================

def show_analytics(df: pd.DataFrame):
    st.subheader("Analytics Rápidos")
    if df.empty:
        st.info("Sem dados para analytics.")
        return

    def avg_completion(row):
        vals = []
        for p in ["Manhã","Tarde","Noite"]:
            col = f"% Concluído ({p})"
            if col in row.index:
                try:
                    vals.append(float(row[col]))
                except Exception:
                    vals.append(0.0)
        return np.mean(vals) if vals else 0.0

    df['avg_pct'] = df.apply(avg_completion, axis=1)
    agg = df.groupby('Aluno(a)')['avg_pct'].mean().fillna(0.0)
    fig, ax = plt.subplots(figsize=(6,3))
    ax.bar(agg.index.astype(str), agg.values)
    ax.set_ylabel("Média de conclusão")
    ax.set_ylim(0,1)
    ax.set_title("Conclusão média por aluno")
    st.pyplot(fig)

    period_avgs = {}
    for p in ["Manhã","Tarde","Noite"]:
        col = f"% Concluído ({p})"
        if col in df.columns:
            try:
                period_avgs[p] = float(df[col].astype(float).mean())
            except Exception:
                period_avgs[p] = 0.0
        else:
            period_avgs[p] = 0.0
    fig2, ax2 = plt.subplots(figsize=(6,3))
    ax2.bar(list(period_avgs.keys()), [v for v in period_avgs.values()])
    ax2.set_ylim(0,1)
    ax2.set_title("Média % Concluído por período")
    st.pyplot(fig2)

# =============================================================================
# UI PRINCIPAL
# =============================================================================

def show_login_screen():
    st.markdown("""
    <div style="display:flex;justify-content:center;align-items:center;min-height:40vh;">
        <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:28px;border-radius:14px;color:white;">
            <h1 style="margin:0;">Cronograma Ana&Mateus</h1>
            <p style="margin:0;">Bem-vindo — escolha o usuário para começar</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        col_m, col_a = st.columns(2)
        with col_m:
            if st.button("👨‍🎓 Entrar como Mateus", key="login_m"):
                st.session_state.logged_user = "Mateus"
                st.experimental_rerun()
        with col_a:
            if st.button("👩‍🎓 Entrar como Ana", key="login_a"):
                st.session_state.logged_user = "Ana"
                st.experimental_rerun()

def show_dashboard(user: str):
    st.markdown(f"# Cronograma Ana&Mateus — {user}")
    st.markdown("Painel IA-first: use ações rápidas em cada tarefa para gerar resumos, quiz, reagendar ou marcar concluído.")

    client = connect_to_google_sheets()
    if not client:
        st.error("❌ Falha de conexão com Google Sheets. Verifique st.secrets e permissões.")
        return

    spreadsheet_id = st.secrets.get("SPREADSHEET_ID_OR_URL", "")
    sheet_tab_name = st.secrets.get("SHEET_TAB_NAME", "Cronograma")
    df, worksheet, headers = load_data(client, spreadsheet_id, sheet_tab_name)
    if df.empty:
        st.warning("⚠️ A planilha não retornou dados ou está vazia.")
        return

    # garantir coluna ID
    headers = ensure_unique_id_column(worksheet, headers)

    # sidebar: configurações
    st.sidebar.header("Configurações IA & Heurísticas")
    pct_threshold = st.sidebar.slider("Threshold % mínimo por período (smart rescheduler)", 0, 100, 50) / 100.0
    minutes_per_question = st.sidebar.number_input("Minutos estimados por questão (heurística)", min_value=1, max_value=60, value=4)
    num_quiz_q = st.sidebar.slider("Número de questões no quiz gerado", 2, 8, 4)
    ia_enabled = st.sidebar.checkbox("Ativar IA (Groq)", value=True if st.secrets.get('GROQ_API_KEY') else False)
    st.sidebar.markdown("---")
    st.sidebar.markdown("Dica: compartilhe a planilha com o client_email do service account como Editor.")

    # hoje (fuso -3)
    hoje = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    df_valid = df[df['Data'].notna()]
    df_today = df_valid[df_valid['Data'].dt.date == hoje]
    df_user_today = df_today[(df_today['Aluno(a)'] == user) | (df_today['Aluno(a)'] == 'Ambos')]

    if df_user_today.empty:
        st.info("Nenhuma tarefa para hoje. Quer que eu gere um micro-plano baseado nas próximas 7 tarefas?")
        if st.button("🔮 Gerar micro-plano IA para próximas 7 tarefas"):
            df_future = df_valid[(df_valid['Aluno(a)'] == user) | (df_valid['Aluno(a)'] == 'Ambos')]
            df_future = df_future.sort_values('Data').head(7)
            resumen = []
            for _, r in df_future.iterrows():
                if ia_enabled:
                    prompt = build_activity_summary_prompt(r, "Manhã")
                    out = call_groq_api(prompt)
                else:
                    out = f"{r.get('Matéria (Manhã)')} — {r.get('Atividade Detalhada (Manhã)')}"
                resumen.append(f"{r.get('Data').strftime('%d/%m/%Y')}: {out}")
            st.write("\n\n".join(resumen))
        return

    # mostrar tarefas de hoje
    st.subheader("Tarefas de Hoje")
    for idx, row in df_user_today.iterrows():
        date_str = row['Data'].strftime('%d/%m/%Y') if not pd.isna(row['Data']) else "Sem data"
        title = row.get('Matéria (Manhã)') or row.get('Matéria (Tarde)') or row.get('Matéria (Noite)') or "Atividade"
        st.markdown(f"### {title} — {date_str}")
        col1, col2, col3 = st.columns([4,2,2])
        with col1:
            st.markdown(f"**Manhã:** {row.get('Atividade Detalhada (Manhã)')}")
            st.markdown(f"**Tarde:** {row.get('Atividade Detalhada (Tarde)')}")
            st.markdown(f"**Noite:** {row.get('Atividade Detalhada (Noite)')}")
            st.markdown(f"**Prioridade / Situação:** {row.get('Prioridade')} · {row.get('Situação')}")
        with col2:
            try:
                pct_m = float(row.get("% Concluído (Manhã)", 0.0) or 0.0)
            except Exception:
                pct_m = 0.0
            try:
                pct_t = float(row.get("% Concluído (Tarde)", 0.0) or 0.0)
            except Exception:
                pct_t = 0.0
            try:
                pct_n = float(row.get("% Concluído (Noite)", 0.0) or 0.0)
            except Exception:
                pct_n = 0.0
            st.metric("Manhã", f"{int(pct_m*100)}%")
            st.metric("Tarde", f"{int(pct_t*100)}%")
            st.metric("Noite", f"{int(pct_n*100)}%")
        with col3:
            period_choice = st.selectbox(f"Período ({idx})", ["Manhã","Tarde","Noite"], key=f"period_{idx}")
            if st.button("💡 Resumo IA", key=f"res_{idx}"):
                prompt = build_activity_summary_prompt(row, period_choice)
                out = call_groq_api(prompt) if ia_enabled else "IA desativada nas configurações."
                st.info(out)
            if st.button("❓ Gerar Quiz IA", key=f"quiz_{idx}"):
                prompt = generate_quiz_prompt(row, period_choice, num_questions=num_quiz_q)
                out = call_groq_api(prompt) if ia_enabled else "IA desativada nas configurações."
                st.code(out)
            if st.button("✅ Marcar conclusão (100%)", key=f"done_{idx}"):
                success = update_sheet_mark_done(worksheet, row, headers)
                if success:
                    st.success("Tarefa marcada como concluída no Google Sheets (e Hora Conclusão registrada).")
                    load_data.clear()
                    st.experimental_rerun()
                else:
                    st.warning("Não foi possível marcar automaticamente na planilha. Verifique permissões/colunas.")
            if st.button("📤 Reagendar Inteligente", key=f"resch_{idx}"):
                rpt = smart_reschedule(df, worksheet, headers, row.get("Aluno(a)"), pct_threshold)
                st.write(rpt)

    st.markdown("---")
    show_analytics(df)

    st.markdown("---")
    st.subheader("Exportar / Backup")
    if st.button("📥 Exportar CSV (todos dados)"):
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV completo", data=csv, file_name=f"cronograma_all_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

# =============================================================================
# FLUXO PRINCIPAL
# =============================================================================

def main():
    if 'logged_user' not in st.session_state:
        st.session_state.logged_user = None

    # Header com pequenos avisos
    st.sidebar.title("Cronograma Ana&Mateus")
    st.sidebar.write("Sistema IA-first — garanta que o service account tem permissão Editor na planilha.")

    if not st.session_state.logged_user:
        show_login_screen()
    else:
        show_dashboard(st.session_state.logged_user)

if __name__ == "__main__":
    main()
