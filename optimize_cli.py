# -*- coding: utf-8 -*-
"""
Cronograma Ana&Mateus — Versão IA-First e Criativa
Features principais:
 - Conexão robusta com Google Sheets (aceita JSON escapado em st.secrets)
 - Normalização segura de colunas, corrige FutureWarning de dtype
 - ID única por linha (coluna 'ID')
 - Marca Hora Conclusão ao finalizar tarefa
 - Smart Rescheduler + Spaced Repetition suggestions
 - Gamificação: XP, Streaks, Badges
 - IA: resumos, micro-planos e quizzes (usa GROQ via st.secrets)
 - Export de Flashcards/Anki (CSV) a partir de quizzes gerados
 - Calendar heatmap de adesão, gráficos de conclusão
 - Focus Mode / Pomodoro (simples, cliente-side)
 - Safe fallbacks se IA ou escrita na planilha não estiverem disponíveis
"""
import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
import requests, json, time, uuid
from typing import Tuple, Optional, List, Any
import matplotlib.pyplot as plt
import base64

# ----------------------------
# Config inicial
# ----------------------------
st.set_page_config(page_title="Cronograma Ana&Mateus", page_icon="🎓", layout="wide")
st.title("Cronograma Ana&Mateus — IA & Criatividade")

# ----------------------------
# Helpers: conexão e parsing
# ----------------------------
@st.cache_resource(ttl=600, show_spinner=False)
def connect_to_google_sheets():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets.get("gcp_service_account", None)
        if not creds_info:
            st.error("❌ gcp_service_account ausente em st.secrets.")
            return None
        if isinstance(creds_info, str):
            try:
                creds_dict = json.loads(creds_info)
            except json.JSONDecodeError:
                creds_dict = json.loads(creds_info.replace('\\\\n', '\\n'))
        else:
            creds_dict = dict(creds_info)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.Client(auth=creds)
        client.session = gspread.http_client.HTTPClient(auth=creds)
        return client
    except Exception as e:
        st.error(f"Erro conectando Google Sheets: {str(e)[:200]}")
        return None

@st.cache_data(ttl=60, show_spinner=False)
def load_data(client, spreadsheet_id: str, sheet_tab_name: str) -> Tuple[pd.DataFrame, Optional[Any], List[str]]:
    """
    Carrega planilha, normaliza colunas e corrige tipos (incl. % concluído -> float 0..1)
    """
    try:
        if not client:
            return pd.DataFrame(), None, []
        # abrir por key ou url
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = client.open_by_url(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_tab_name)
        all_values = worksheet.get_all_values()
        if not all_values:
            return pd.DataFrame(), worksheet, []
        headers = all_values[0]
        data = all_values[1:] if len(all_values) > 1 else []
        df = pd.DataFrame(data, columns=headers)

        # garantir colunas esperadas (preencher com vazios)
        expected = [
            "Data","Dificuldade (1-5)","Status","Aluno(a)","Dia da Semana","Fase do Plano",
            "Matéria (Manhã)","Atividade Detalhada (Manhã)","Teoria Feita (Manhã)","Questões Planejadas (Manhã)",
            "Questões Feitas (Manhã)","% Concluído (Manhã)","Matéria (Tarde)","Atividade Detalhada (Tarde)","Teoria Feita (Tarde)",
            "Questões Planejadas (Tarde)","Questões Feitas (Tarde)","% Concluído (Tarde)","Matéria (Noite)","Atividade Detalhada (Noite)",
            "Teoria Feita (Noite)","Questões Planejadas (Noite)","Questões Feitas (Noite)","% Concluído (Noite)","Exame",
            "Alerta/Comentário","Situação","Prioridade"
        ]
        for c in expected:
            if c not in df.columns:
                df[c] = ""

        # Conversões seguras:
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        # Dificuldade
        df['Dificuldade (1-5)'] = pd.to_numeric(df['Dificuldade (1-5)'], errors='coerce').fillna(0).astype(int)
        # Questões -> int
        for col in df.columns:
            if 'Questões' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        # Teoria -> boolean
        for col in df.columns:
            if 'Teoria Feita' in col:
                df[col] = df[col].astype(str).str.upper().isin(['TRUE','VERDADEIRO','1','SIM','SIM'])
        # % Concluído -> float 0..1 (robusto para '75' ou '75%' ou '0.75')
        for col in df.columns:
            if '% Concluído' in col or '%Concluído' in col:
                s = df[col].astype(str).str.replace('%','').str.replace(',','.').str.strip()
                # remover pontos de milhar se parecer existir (ex: 1.234,56)
                # cuidado: só remover '.' se houver ',' no mesmo valor (padrão BR)
                maybe_thousand = s.str.contains(r'\.\d{3}', regex=True)
                if maybe_thousand.any():
                    s = s.str.replace('.','', regex=False)
                s = pd.to_numeric(s, errors='coerce').fillna(0.0)
                mask = s > 1.0
                if mask.any():
                    s.loc[mask] = s.loc[mask] / 100.0
                s = s.clip(0.0, 1.0).astype(float)
                df[col] = s

        return df, worksheet, headers

    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)[:200]}")
        return pd.DataFrame(), None, []

# ----------------------------
# IA: Groq wrapper
# ----------------------------
def call_groq_api(prompt: str, max_retries: int = 2) -> str:
    groq_key = st.secrets.get('GROQ_API_KEY', None)
    if not groq_key:
        return "⚠️ GROQ_API_KEY ausente em st.secrets."
    groq_url = st.secrets.get('GROQ_API_URL', "").strip()
    if groq_url:
        endpoint = groq_url
        if endpoint.endswith('/v1') or endpoint.endswith('/v1/'):
            endpoint = endpoint.rstrip('/') + "/chat/completions"
    else:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"

    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    payload = {"model":"gemma2-9b-it", "messages":[{"role":"user","content":prompt}], "temperature":0.6, "max_tokens":600}

    for attempt in range(max_retries):
        try:
            r = requests.post(endpoint, headers=headers, json=payload, timeout=12)
            if r.status_code == 200:
                j = r.json()
                choices = j.get('choices') or []
                if choices and isinstance(choices, list):
                    first = choices[0]
                    if isinstance(first, dict):
                        if 'message' in first and 'content' in first['message']:
                            return first['message']['content']
                        if 'text' in first:
                            return first['text']
                return json.dumps(j)[:2000]
            elif r.status_code == 401:
                return "⚠️ API Key inválida (401)."
            else:
                if attempt < max_retries-1:
                    time.sleep(1)
                    continue
                return f"⚠️ Erro IA {r.status_code}: {r.text[:300]}"
        except requests.exceptions.Timeout:
            if attempt < max_retries-1:
                continue
            return "⚠️ Timeout na conexão com a IA."
        except Exception as e:
            return f"⚠️ Erro: {str(e)[:200]}"
    return "⚠️ Não foi possível conectar com a IA."

# ----------------------------
# Planilha: IDs, updates e utils
# ----------------------------
def ensure_id_column(worksheet, headers):
    try:
        if 'ID' in headers:
            return headers
        first_row = worksheet.row_values(1)
        first_row.append('ID')
        worksheet.update('1:1', [first_row])
        all_values = worksheet.get_all_values()
        headers_new = all_values[0]
        id_col_idx = headers_new.index('ID')
        data_rows = all_values[1:]
        for i, row in enumerate(data_rows, start=2):
            current = row[id_col_idx] if len(row) > id_col_idx else ""
            if not current or str(current).strip() == "":
                new_id = str(uuid.uuid4())[:8]
                try:
                    worksheet.update_cell(i, id_col_idx+1, new_id)
                except Exception:
                    pass
        all_values = worksheet.get_all_values()
        return all_values[0]
    except Exception as e:
        st.warning(f"Erro ao criar coluna ID: {str(e)[:120]}")
        return headers

def find_row_index(worksheet, date_val: datetime, aluno: str, activity_hint: str) -> Optional[int]:
    try:
        all_values = worksheet.get_all_values()
        if not all_values: return None
        headers = all_values[0]
        rows = all_values[1:]
        try:
            col_date = headers.index('Data')
        except ValueError:
            col_date = None
        try:
            col_aluno = headers.index('Aluno(a)')
        except ValueError:
            col_aluno = None
        # preferir Atividade Detalhada cols
        act_col = None
        for name in ["Atividade Detalhada (Manhã)","Atividade Detalhada (Tarde)","Atividade Detalhada (Noite)"]:
            if name in headers:
                act_col = headers.index(name)
                break
        for i, r in enumerate(rows, start=2):
            ok = True
            if col_date is not None and date_val is not None and not pd.isna(date_val):
                try:
                    cell_date = pd.to_datetime(r[col_date], format='%d/%m/%Y', errors='coerce')
                    if pd.isna(cell_date) or cell_date.date() != date_val.date():
                        ok = False
                except Exception:
                    ok = False
            if ok and col_aluno is not None:
                if str(r[col_aluno]).strip().lower() != str(aluno).strip().lower():
                    ok = False
            if ok and act_col is not None and activity_hint:
                cell_act = str(r[act_col]).strip().lower()
                if activity_hint.strip().lower() not in cell_act and cell_act != "":
                    # partial matching fallback
                    if len(set(activity_hint.split()) & set(cell_act.split())) == 0:
                        ok = False
            if ok:
                return i
        return None
    except Exception as e:
        st.warning(f"Erro find_row_index: {str(e)[:120]}")
        return None

def try_update_cell(worksheet, r:int, c:int, value) -> bool:
    try:
        worksheet.update_cell(int(r), int(c), str(value))
        return True
    except Exception as e:
        st.warning(f"Falha ao atualizar célula r{r}c{c}: {str(e)[:120]}")
        return False

def mark_done(worksheet, df_row, headers) -> bool:
    try:
        if worksheet is None or df_row is None: return False
        target_date = df_row.get('Data')
        aluno = str(df_row.get('Aluno(a)','')).strip()
        activity_hint = (str(df_row.get('Atividade Detalhada (Manhã)') or df_row.get('Atividade Detalhada (Tarde)') or df_row.get('Atividade Detalhada (Noite)') or "")).strip()
        row_idx = find_row_index(worksheet, target_date, aluno, activity_hint)
        if not row_idx: return False
        updated = False
        for p in ["Manhã","Tarde","Noite"]:
            col_name = f"% Concluído ({p})"
            if col_name in headers:
                ci = headers.index(col_name) + 1
                if try_update_cell(worksheet, row_idx, ci, "100%"):
                    updated = True
        # Hora Conclusão: criar se necessário
        if 'Hora Conclusão' not in headers:
            try:
                first_row = worksheet.row_values(1)
                first_row.append('Hora Conclusão')
                worksheet.update('1:1', [first_row])
                headers.append('Hora Conclusão')
            except Exception:
                pass
        if 'Hora Conclusão' in headers:
            ci = headers.index('Hora Conclusão') + 1
            if try_update_cell(worksheet, row_idx, ci, datetime.now().strftime('%H:%M:%S')):
                updated = True
        return updated
    except Exception as e:
        st.error(f"Erro ao marcar concluído: {str(e)[:150]}")
        return False

# ----------------------------
# Gamificação & heurísticas
# ----------------------------
def compute_xp(df: pd.DataFrame, aluno: str) -> Tuple[int,int]:
    """
    XP simples: +10 por período 100% concluído; streak = dias consecutivos com ao menos 1 período 100%
    """
    xp = 0
    # dias com conclusão total
    df_aluno = df[(df['Aluno(a)']==aluno) | (df['Aluno(a)']=='Ambos')].copy()
    if df_aluno.empty:
        return 0,0
    df_aluno['date_only'] = df_aluno['Data'].dt.date
    days = sorted(df_aluno['date_only'].dropna().unique())
    # compute streak: consecutive days ending today (or last date in data)
    streak = 0
    today = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    # find most recent day in days that <= today
    last_day = max([d for d in days if d <= today]) if any(d <= today for d in days) else None
    cur = last_day
    while cur:
        day_rows = df_aluno[df_aluno['date_only']==cur]
        complete_day = False
        for p in ["Manhã","Tarde","Noite"]:
            col = f"% Concluído ({p})"
            if col in day_rows.columns:
                if (day_rows[col].astype(float) >= 1.0).any():
                    complete_day = True
        if complete_day:
            streak += 1
            cur = cur - timedelta(days=1)
        else:
            break
    # XP
    for p in ["Manhã","Tarde","Noite"]:
        col = f"% Concluído ({p})"
        if col in df_aluno.columns:
            xp += int((df_aluno[col].astype(float) >= 1.0).sum()) * 10
    return xp, streak

def recommend_spaced_repetition(df_row):
    """
    Gera sugestão simples de repetição: se dificuldade alto -> revisar em 24h, 72h, 7d
    """
    d = int(df_row.get("Dificuldade (1-5)",0) or 0)
    if d >= 4:
        return ["24 horas", "72 horas", "7 dias"]
    if d == 3:
        return ["48 horas", "7 dias"]
    if d <= 2:
        return ["72 horas", "10 dias"]
    return ["72 horas", "7 dias"]

# ----------------------------
# Quizzes / Anki export
# ----------------------------
def generate_quiz_and_anki(row, period, n=4, ia_enabled=True):
    prompt = f"Crie um mini-quiz de {n} questões sobre '{row.get(f'Matéria ({period})','')}' com foco em {row.get(f'Atividade Detalhada ({period})','')}. Forneça alternativas A-D e Gabarito. Responda em português."
    if ia_enabled:
        out = call_groq_api(prompt)
    else:
        out = "IA desativada."
    # tentativa simples de extrair Q/A (o ideal é parsear; aqui retornamos texto bruto)
    # gerar CSV Anki simples: Frente = Pergunta; Verso = Resposta
    anki_cards = []
    # tentar extrair linhas que pareçam "1." ou "Q1" - heurística simples
    lines = out.splitlines()
    q_text = ""
    a_text = ""
    current_q = None
    for L in lines:
        if L.strip().startswith(('1','2','3','4')):
            # nova questão (heurística)
            if current_q:
                anki_cards.append((current_q, a_text))
            current_q = L.strip()
            a_text = ""
        elif L.strip().upper().startswith("GABARITO"):
            a_text = L.strip()
        else:
            if current_q:
                current_q += " " + L.strip()
    if current_q:
        anki_cards.append((current_q, a_text))
    # fallback: se não parseou, colocar todo quiz como um card
    if not anki_cards:
        anki_cards = [(f"Quiz sobre {row.get(f'Matéria ({period})','')}", out)]
    return out, anki_cards

def anki_csv_download(anki_cards, filename):
    df = pd.DataFrame(anki_cards, columns=['Front','Back'])
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Baixar CSV Anki", data=csv, file_name=filename, mime="text/csv")

# ----------------------------
# Visualizações criativas
# ----------------------------
def calendar_heatmap(df: pd.DataFrame, aluno: str):
    # mapa de calor simples: dias do mês x conclusão média
    df_a = df[(df['Aluno(a)']==aluno) | (df['Aluno(a)']=='Ambos')].copy()
    if df_a.empty:
        st.info("Sem dados para heatmap.")
        return
    df_a['date'] = df_a['Data'].dt.date
    agg = df_a.groupby('date').apply(lambda g: np.mean([g.get('% Concluído (Manhã)',0).astype(float).mean() if '% Concluído (Manhã)' in g else 0,
                                                        g.get('% Concluído (Tarde)',0).astype(float).mean() if '% Concluído (Tarde)' in g else 0,
                                                        g.get('% Concluído (Noite)',0).astype(float).mean() if '% Concluído (Noite)' in g else 0]))
    agg = agg.fillna(0)
    dates = list(agg.index)
    vals = list(agg.values)
    fig, ax = plt.subplots(figsize=(10,3))
    ax.plot(dates, vals, marker='o')
    ax.set_ylim(0,1)
    ax.set_title("Progresso diário médio")
    st.pyplot(fig)

# ----------------------------
# Focus Mode / Pomodoro (cliente-side simple)
# ----------------------------
def pomodoro_widget():
    st.write("### ⏱️ Focus Mode — Pomodoro (local)")
    # simples JS countdown que roda no navegador (não bloqueante)
    js = """
    <div id="pomodoro">
      <div style="display:flex;gap:10px;align-items:center;">
        <button id="start">Iniciar 25:00</button>
        <button id="stop">Parar</button>
        <div id="timer" style="font-weight:800;margin-left:12px;">25:00</div>
      </div>
    </div>
    <script>
    let timerInterval = null;
    function format(s){ let m = Math.floor(s/60); let sec = s%60; return String(m).padStart(2,'0')+':'+String(sec).padStart(2,'0'); }
    document.getElementById('start').onclick = () => {
      let total = 25*60;
      if(timerInterval) clearInterval(timerInterval);
      timerInterval = setInterval(()=> {
        document.getElementById('timer').innerText = format(total);
        total--;
        if(total<0){ clearInterval(timerInterval); new Audio('https://actions.google.com/sounds/v1/alarms/alarm_clock.ogg').play(); alert('Pomodoro finalizado!');}
      }, 1000);
    };
    document.getElementById('stop').onclick = () => { if(timerInterval) clearInterval(timerInterval); timerInterval=null; document.getElementById('timer').innerText='25:00'; };
    </script>
    """
    st.components.v1.html(js, height=120)

# ----------------------------
# UI principal
# ----------------------------
def show_login():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if st.button("👨‍🎓 Entrar como Mateus"):
            st.session_state.logged_user = "Mateus"
            st.experimental_rerun()
        if st.button("👩‍🎓 Entrar como Ana"):
            st.session_state.logged_user = "Ana"
            st.experimental_rerun()

def main_ui():
    client = connect_to_google_sheets()
    if not client:
        st.stop()
    spreadsheet_id = st.secrets.get("SPREADSHEET_ID_OR_URL", "")
    sheet_tab_name = st.secrets.get("SHEET_TAB_NAME", "Cronograma")
    df, worksheet, headers = load_data(client, spreadsheet_id, sheet_tab_name)
    if df.empty:
        st.warning("Planilha vazia ou sem dados válidos.")
        return

    # garantir ID
    headers = ensure_id_column(worksheet, headers)

    # Sidebar: configurações criativas
    st.sidebar.header("⚙️ Configurações Criativas")
    ia_enabled = st.sidebar.checkbox("Ativar IA (Groq)", value=True if st.secrets.get('GROQ_API_KEY') else False)
    smart_threshold = st.sidebar.slider("Threshold p/ re-agendamento (%)", 0, 100, 50) / 100.0
    anki_include = st.sidebar.checkbox("Ativar export Anki", value=True)
    st.sidebar.markdown("---")
    st.sidebar.write("Gamification: ganhe XP completando períodos (10 XP por período).")

    user = st.session_state.get('logged_user', None)
    if not user:
        show_login()
        return
    st.markdown(f"## Olá, {user} 👋 — seu painel criativo")
    # quick stats XP / streaks
    xp, streak = compute_xp(df, user)
    st.metric("XP acumulado", xp)
    st.metric("Streak (dias consecutivos)", streak)

    # tarefas de hoje
    hoje = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    df_valid = df[df['Data'].notna()]
    df_today = df_valid[df_valid['Data'].dt.date == hoje]
    df_user_today = df_today[(df_today['Aluno(a)']==user) | (df_today['Aluno(a)']=='Ambos')]

    # painel criativo quando sem tarefas hoje
    if df_user_today.empty:
        st.info("Nenhuma tarefa para hoje — quer gerar um micro-plano IA para os próximos 7 dias?")
        if st.button("🔮 Gerar micro-plano IA"):
            df_future = df_valid[(df_valid['Aluno(a)']==user) | (df_valid['Aluno(a)']=='Ambos')].sort_values('Data').head(7)
            cards = []
            for _, r in df_future.iterrows():
                plan = call_groq_api(build_prompt_for_microplan(r)) if ia_enabled else f"{r.get('Matéria (Manhã)','')} — {r.get('Atividade Detalhada (Manhã)','')}"
                cards.append(f"{r['Data'].strftime('%d/%m/%Y')}: {plan}")
            st.write("\n\n".join(cards))
        # mostrar visualizações rápidas
        calendar_heatmap(df, user)
        return

    # listar tarefas de hoje com ações criativas
    st.markdown("### Tarefas de hoje")
    for idx, row in df_user_today.iterrows():
        st.markdown("---")
        title = row.get("Matéria (Manhã)") or row.get("Matéria (Tarde)") or row.get("Matéria (Noite)") or "Atividade"
        st.subheader(f"{title} — {row['Data'].strftime('%d/%m/%Y') if not pd.isna(row['Data']) else 'Sem data'}")
        c1, c2, c3 = st.columns([4,2,2])
        with c1:
            st.write("**Manhã:**", row.get("Atividade Detalhada (Manhã)") or "—")
            st.write("**Tarde:**", row.get("Atividade Detalhada (Tarde)") or "—")
            st.write("**Noite:**", row.get("Atividade Detalhada (Noite)") or "—")
            st.write("Sugestão de revisão (Spaced Repetition):", ", ".join(recommend_spaced_repetition(row)))
        with c2:
            for p in ["Manhã","Tarde","Noite"]:
                col = f"% Concluído ({p})"
                val = 0.0
                if col in row.index:
                    try:
                        val = float(row[col] or 0.0)
                    except Exception:
                        val = 0.0
                st.metric(p, f"{int(val*100)}%")
        with c3:
            period = st.selectbox(f"Período ({idx})", ["Manhã","Tarde","Noite"], key=f"period_sel_{idx}")
            if st.button("💡 Resumo IA", key=f"res_{idx}"):
                if ia_enabled:
                    prompt = build_activity_summary_prompt(row, period)
                    out = call_groq_api(prompt)
                else:
                    out = "IA desativada."
                st.info(out)
            if st.button("❓ Gerar Quiz + Anki", key=f"quiz_{idx}"):
                out, cards = generate_quiz_and_anki(row, period, n=4, ia_enabled=ia_enabled)
                st.code(out)
                if anki_include:
                    anki_csv_download(cards, f"anki_{user}_{row['Data'].strftime('%Y%m%d')}.csv")
            if st.button("✅ Marcar Concluído (100%)", key=f"done_{idx}"):
                ok = mark_done(worksheet, row, headers)
                if ok:
                    st.success("Marcado concluído e Hora Conclusão registrada.")
                    load_data.clear()
                    st.experimental_rerun()
                else:
                    st.warning("Não foi possível marcar (verifique permissões).")
            if st.button("📤 Reagendar Inteligente", key=f"resch_{idx}"):
                rpt = smart_reschedule_wrapper(df, worksheet, headers, user, smart_threshold)
                st.write(rpt)

    # Focus Mode
    st.markdown("---")
    pomodoro_widget()

    # Analytics e calendar
    st.markdown("---")
    st.header("Análises criativas")
    show_small_analytics(df, user)
    calendar_heatmap(df, user)

    # Export geral
    st.markdown("---")
    if st.button("📥 Export completo CSV"):
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", data=csv, file_name=f"cronograma_all_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

# ----------------------------
# Funções complementares que usamos na UI
# ----------------------------
def build_activity_summary_prompt(row, period_label):
    subj = row.get(f"Matéria ({period_label})", "")
    act = row.get(f"Atividade Detalhada ({period_label})", "")
    exam = row.get("Exame","")
    difficulty = int(row.get("Dificuldade (1-5)",0) or 0)
    return (f"Você é um coach de estudos expert. Resuma em 1 parágrafo e entregue 3 passos práticos "
            f"para estudar: Matéria: {subj}. Atividade: {act}. Exame: {exam}. Dificuldade: {difficulty}. "
            "Formato: 1 parágrafo + 'Plano: 1) ... 2) ... 3) ...'.")

def build_prompt_for_microplan(row):
    subj = row.get("Matéria (Manhã)") or row.get("Matéria (Tarde)") or row.get("Matéria (Noite)") or ""
    act = row.get("Atividade Detalhada (Manhã)") or row.get("Atividade Detalhada (Tarde)") or row.get("Atividade Detalhada (Noite)") or ""
    return f"Crie um micro-plano de 3 dias para {subj} focando em {act}. Entregue instruções práticas por dia."

def smart_reschedule_wrapper(df, worksheet, headers, aluno, threshold):
    # wrapper leve que chama função com proteção
    try:
        return smart_reschedule(df, worksheet, headers, aluno, threshold)
    except Exception as e:
        return {"error": str(e)}

def smart_reschedule(df, worksheet, headers, aluno: str, pct_threshold: float = 0.5, max_push_days=7):
    report = {"moved":0, "failed":0, "details":[]}
    try:
        for idx, r in df.iterrows():
            if r.get("Aluno(a)") not in [aluno, "Ambos"]:
                continue
            date = r.get("Data")
            if pd.isna(date):
                continue
            for period in ["Manhã","Tarde","Noite"]:
                pct_col = f"% Concluído ({period})"
                if pct_col not in df.columns:
                    continue
                try:
                    pct = float(r.get(pct_col,0.0) or 0.0)
                except Exception:
                    pct = 0.0
                if pct < pct_threshold:
                    # tentar mover para próximo dia livre
                    for d in range(1, max_push_days+1):
                        new_date = (date + timedelta(days=d)).date()
                        exists = ((df['Data'].dt.date == new_date) & ((df['Aluno(a)'] == aluno) | (df['Aluno(a)'] == 'Ambos'))).any()
                        if not exists:
                            row_idx = find_row_index(worksheet, date, r.get("Aluno(a)"), r.get(f"Atividade Detalhada ({period})",""))
                            if row_idx:
                                try:
                                    dcol = headers.index("Data") + 1
                                    if try_update_cell(worksheet, row_idx, dcol, new_date.strftime('%d/%m/%Y')):
                                        report["moved"] += 1
                                        report["details"].append(f"{r.get('Aluno(a)')} {period} {date.strftime('%d/%m/%Y')} -> {new_date.strftime('%d/%m/%Y')}")
                                    else:
                                        report["failed"] += 1
                                    break
                                except Exception as e:
                                    report["failed"] += 1
                                    report["details"].append(str(e)[:120])
                                    break
                            else:
                                report["failed"] += 1
                                report["details"].append("Linha não encontrada para mover")
                                break
    except Exception as e:
        report["failed"] += 1
        report["details"].append(str(e)[:120])
    return report

def show_small_analytics(df, aluno):
    st.write("Métricas rápidas")
    xp, streak = compute_xp(df, aluno)
    st.write(f"- XP: **{xp}**  ·  Streak: **{streak} dias**")
    # gráfico: conclusão média por período
    per = {}
    for p in ["Manhã","Tarde","Noite"]:
        col = f"% Concluído ({p})"
        per[p] = df[col].astype(float).mean() if col in df.columns else 0.0
    fig, ax = plt.subplots(figsize=(6,2.5))
    ax.bar(per.keys(), per.values())
    ax.set_ylim(0,1)
    ax.set_title("Média % concluído por período")
    st.pyplot(fig)

def anki_csv_download(cards, filename):
    # cards = list of (Front, Back)
    dfc = pd.DataFrame(cards, columns=["Front","Back"])
    csv = dfc.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Baixar CSV Anki", data=csv, file_name=filename, mime="text/csv")

# ----------------------------
# Entrypoint
# ----------------------------
def main():
    if 'logged_user' not in st.session_state:
        st.session_state.logged_user = None
    st.sidebar.title("Cronograma Ana&Mateus")
    st.sidebar.write("Dicas: compartilhe a planilha com client_email do service account como Editor.")
    main_ui()

if __name__ == "__main__":
    main()
