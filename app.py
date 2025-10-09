# -*- coding: utf-8 -*-
"""
Cronograma Ana&Mateus — Versão atualizada (UI criativa + IA automática)
Principais pontos:
 - Compatível com Streamlit (usa st.query_params para forçar rerun)
 - Visual melhorado via CSS embutido
 - Auto-Coach IA (opcional) gera resumos/plans ao abrir para tarefas do dia
 - Fallback automático de modelo Groq e fallback local quando IA indisponível
 - Correções: load_data(_client), tratamento de % Concluído (evita FutureWarning),
   não sobrescreve client.session, worksheet.update(values=..., range=...)
 - Sem dependência de matplotlib
"""
import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
import requests, json, time, uuid, re
from typing import Tuple, Optional, List, Any

# ----------------------------
# Configuração inicial
# ----------------------------
st.set_page_config(page_title="Cronograma Ana&Mateus", page_icon="🎓", layout="wide")
# inject creative CSS
st.markdown("""
<style>
:root{
  --bg1:#0f172a; --bg2:#0ea5e9; --card:#ffffff;
  --accent1:#7c3aed; --accent2:#06b6d4;
}
body {background: linear-gradient(135deg,var(--bg1),#0b1220); color:#e6eef8;}
.block-container{max-width:1200px; padding:1rem 2rem;}
.header-card{
  background:linear-gradient(90deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
  border-radius:16px; padding:20px; box-shadow: 0 6px 30px rgba(2,6,23,0.7); margin-bottom:14px;
}
h1 {font-family: 'Poppins', sans-serif; font-weight:700; color: #fff;}
.coach-badge {display:inline-block; background: linear-gradient(90deg,var(--accent1),var(--accent2)); color:white; padding:6px 10px; border-radius:12px; font-weight:700;}
.card {background: white; color:#0b1220; border-radius:12px; padding:14px; box-shadow:0 10px 30px rgba(2,6,23,0.45); }
.small-muted {font-size:12px; color:#93c5fd;}
.task-title {font-weight:800; font-size:20px;}
.metric-box{background:linear-gradient(90deg,#fef3c7,#fde68a); border-radius:10px; padding:8px 12px; font-weight:700;}
.btn-fancy {background: linear-gradient(90deg,#7c3aed,#06b6d4); color:white; padding:8px 12px; border-radius:8px; border:none;}
</style>
""", unsafe_allow_html=True)

st.title("Cronograma — Ana & Mateus ✨")
st.markdown("<div class='header-card'><div style='display:flex;justify-content:space-between;align-items:center'><div><h1 style='margin:0;'>Cronograma Ana&Mateus</h1><div class='small-muted'>Interface criativa com IA integrada — automático ou manual</div></div><div><span class='coach-badge'>Coach IA</span></div></div></div>", unsafe_allow_html=True)

# ----------------------------
# small helpers
# ----------------------------
def safe_rerun():
    """Força rerun sem usar experimental_rerun"""
    try:
        st.query_params = {"_refresh": str(int(time.time()))}
    except Exception:
        st.session_state['_forced_reload'] = st.session_state.get('_forced_reload', 0) + 1

def clean_number_like_series(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str)
    s = s.str.replace(r'[\[\]\'"]', '', regex=True)
    s = s.str.strip()
    has_thousand = s.str.contains(r'\.\d{3}', regex=True)
    if has_thousand.any():
        s = s.where(~has_thousand, s.str.replace('.', '', regex=False))
    s = s.str.replace(',', '.', regex=False)
    s = s.str.replace(r'[^\d\.\-]', '', regex=True)
    return pd.to_numeric(s, errors='coerce').fillna(0.0)

# ----------------------------
# Connect Google Sheets
# ----------------------------
@st.cache_resource(ttl=600, show_spinner=False)
def connect_to_google_sheets():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets.get("gcp_service_account", None)
        if not creds_info:
            return None, None
        if isinstance(creds_info, str):
            try:
                creds_dict = json.loads(creds_info)
            except Exception:
                creds_dict = json.loads(creds_info.replace('\\\\n','\n'))
        else:
            creds_dict = dict(creds_info)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.Client(auth=creds)
        client_email = creds_dict.get("client_email")
        return client, client_email
    except Exception as e:
        st.error("Erro ao conectar ao Google Sheets — verifique st.secrets (não cole chaves aqui).")
        st.write(str(e)[:300])
        return None, None

# ----------------------------
# load_data with _client
# ----------------------------
@st.cache_data(ttl=60, show_spinner=False)
def load_data(_client, spreadsheet_id: str, sheet_tab_name: str):
    try:
        if not _client: return pd.DataFrame(), None, []
        try:
            spreadsheet = _client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = _client.open_by_url(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_tab_name)
        all_values = worksheet.get_all_values()
        if not all_values: return pd.DataFrame(), worksheet, []
        headers = all_values[0]
        data = all_values[1:] if len(all_values)>1 else []
        df = pd.DataFrame(data, columns=headers)

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

        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        df['Dificuldade (1-5)'] = pd.to_numeric(df['Dificuldade (1-5)'], errors='coerce').fillna(0).astype(int)
        for col in df.columns:
            if 'Questões' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            if 'Teoria Feita' in col:
                df[col] = df[col].astype(str).str.upper().isin(['TRUE','VERDADEIRO','1','SIM'])
            if '% Concluído' in col or '%Concluído' in col:
                s_raw = df[col].astype(str)
                s = clean_number_like_series(s_raw)
                mask = s > 1.0
                if mask.any():
                    s.loc[mask] = s.loc[mask] / 100.0
                s = s.clip(0.0,1.0).astype(float)
                df[col] = s
        return df, worksheet, headers
    except Exception as e:
        st.error("Erro ao carregar dados da planilha.")
        st.write(str(e)[:400])
        return pd.DataFrame(), None, []

# ----------------------------
# Groq wrapper with fallback
# ----------------------------
def call_groq_api_with_model(prompt: str, model: str, max_retries: int = 2):
    groq_key = st.secrets.get('GROQ_API_KEY', None)
    if not groq_key:
        return False, "GROQ_API_KEY ausente em st.secrets.", None
    groq_url = st.secrets.get('GROQ_API_URL', "").strip()
    if groq_url:
        endpoint = groq_url
        if endpoint.endswith('/v1') or endpoint.endswith('/v1/'):
            endpoint = endpoint.rstrip('/') + "/chat/completions"
    else:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type":"application/json"}
    payload = {"model": model, "messages":[{"role":"user","content":prompt}], "temperature":0.6, "max_tokens":600}
    for attempt in range(max_retries):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                j = resp.json()
                choices = j.get('choices') or []
                if choices and isinstance(choices, list):
                    first = choices[0]
                    if isinstance(first, dict):
                        if 'message' in first and 'content' in first['message']:
                            return True, first['message']['content'], model
                        if 'text' in first:
                            return True, first['text'], model
                return True, json.dumps(j)[:3000], model
            if resp.status_code == 401:
                return False, "API Key inválida (401).", model
            try:
                errj = resp.json()
                err = errj.get('error') or {}
                code = err.get('code') or errj.get('code')
                msg = err.get('message') or str(errj)
                if code == 'model_decommissioned' or ('decommission' in msg.lower() or 'deprecat' in msg.lower()):
                    return False, f"model_decommissioned: {msg}", model
                if attempt < max_retries-1:
                    time.sleep(1)
                    continue
                return False, f"Erro IA {resp.status_code}: {msg}", model
            except ValueError:
                if attempt < max_retries-1:
                    time.sleep(1)
                    continue
                return False, f"Erro IA {resp.status_code}: {resp.text[:300]}", model
        except requests.exceptions.Timeout:
            if attempt < max_retries-1:
                continue
            return False, "Timeout na conexão com a IA.", model
        except Exception as e:
            return False, f"Erro: {str(e)[:200]}", model
    return False, "Não foi possível conectar com a IA.", model

def call_groq_api(prompt: str):
    configured_model = st.secrets.get('GROQ_MODEL', "").strip()
    if not configured_model:
        configured_model = "gemma2-9b-it"
    fallback_model = st.secrets.get('GROQ_FALLBACK_MODEL', "llama-3.1-8b-instant")
    ok, text, used = call_groq_api_with_model(prompt, configured_model)
    if ok:
        return True, text, used
    if isinstance(text, str) and ('model_decommissioned' in text or 'deprecat' in text.lower() or 'decommission' in text.lower()):
        ok2, text2, used2 = call_groq_api_with_model(prompt, fallback_model)
        if ok2:
            note = f"(Modelo {configured_model} descontinuado; fallback {fallback_model})\n\n"
            return True, note + text2, used2
        else:
            return False, f"Falha ao usar fallback {fallback_model}: {text2}", used2 or fallback_model
    return False, text, used

# ----------------------------
# Fallback local
# ----------------------------
def fallback_summary(row, period_label: str) -> str:
    subj = row.get(f"Matéria ({period_label})", "") or "a matéria"
    act = row.get(f"Atividade Detalhada ({period_label})", "") or ""
    diff = int(row.get("Dificuldade (1-5)", 0) or 0)
    base = f"Resumo prático: foque em {subj}. {'Revisão rápida (conceitos).' if diff<=2 else 'Resolver questões + revisão ativa.'}"
    if act:
        base += f" Atividade: {act}."
    plan = "Plano: 1) Leitura 15-25min 2) Questões 20-40min 3) Registrar 3 flashcards."
    return f"{base}\n\n{plan}"

def fallback_quiz(row, period_label: str, n:int=3):
    subj = row.get(f"Matéria ({period_label})", "Matéria")
    desc = row.get(f"Atividade Detalhada ({period_label})", "")
    text = f"Mini-quiz sobre {subj} — {desc}\n\n"
    cards=[]
    for i in range(n):
        if i==0:
            q=f"O que é o conceito central de '{subj}'?"
            a="Resposta: resumo do conceito."
        elif i==1:
            q=f"Resolva/explique um exemplo prático relacionado a '{desc or subj}'."
            a="Resposta: resolução explicada."
        else:
            q=f"V/F: Afirmação comum sobre '{subj}'. Justifique."
            a="Resposta: Verdadeiro/Falso + justificativa."
        text += f"{i+1}. {q}\n"
        cards.append((q,a))
    return text, cards

# ----------------------------
# Planilha helpers (use named args in update)
# ----------------------------
def ensure_id_column(worksheet, headers):
    try:
        if 'ID' in headers:
            return headers
        first_row = worksheet.row_values(1)
        first_row.append('ID')
        worksheet.update(values=[first_row], range='1:1')
        all_values = worksheet.get_all_values()
        headers_new = all_values[0]
        id_idx = headers_new.index('ID')
        rows = all_values[1:]
        for i, r in enumerate(rows, start=2):
            current = r[id_idx] if len(r) > id_idx else ""
            if not current or str(current).strip()=="":
                try:
                    worksheet.update_cell(i, id_idx+1, str(uuid.uuid4())[:8])
                except Exception:
                    pass
        all_values = worksheet.get_all_values()
        return all_values[0]
    except Exception as e:
        st.warning("Erro ao garantir coluna ID: " + str(e)[:200])
        return headers

def find_row_index(worksheet, date_val: datetime, aluno: str, activity_hint: str) -> Optional[int]:
    try:
        all_values = worksheet.get_all_values()
        if not all_values: return None
        headers = all_values[0]
        rows = all_values[1:]
        def idx(name):
            try: return headers.index(name)
            except ValueError: return None
        col_date = idx("Data"); col_aluno = idx("Aluno(a)")
        act_col = None
        for name in ["Atividade Detalhada (Manhã)","Atividade Detalhada (Tarde)","Atividade Detalhada (Noite)"]:
            if name in headers:
                act_col = headers.index(name); break
        for i, r in enumerate(rows, start=2):
            ok=True
            if col_date is not None and date_val is not None and not pd.isna(date_val):
                try:
                    cell_date = pd.to_datetime(r[col_date], format='%d/%m/%Y', errors='coerce')
                    if pd.isna(cell_date) or cell_date.date() != date_val.date():
                        ok=False
                except Exception: ok=False
            if ok and col_aluno is not None:
                if str(r[col_aluno]).strip().lower() != str(aluno).strip().lower(): ok=False
            if ok and act_col is not None and activity_hint:
                cell_act = str(r[act_col]).strip().lower()
                hint = activity_hint.strip().lower()
                if hint and hint not in cell_act and cell_act != "":
                    if len(set(hint.split()) & set(cell_act.split())) == 0:
                        ok=False
            if ok: return i
        return None
    except Exception as e:
        st.warning("Erro find_row_index: " + str(e)[:160])
        return None

def try_update_cell(worksheet, r:int, c:int, value) -> bool:
    try:
        worksheet.update_cell(int(r), int(c), str(value))
        return True
    except Exception as e:
        st.warning(f"Falha ao atualizar r{r}c{c}: {str(e)[:150]}")
        return False

def mark_done(worksheet, df_row, headers) -> bool:
    try:
        if worksheet is None or df_row is None: return False
        target_date = df_row.get('Data')
        aluno = str(df_row.get('Aluno(a)','')).strip()
        activity_hint = str(df_row.get('Atividade Detalhada (Manhã)') or df_row.get('Atividade Detalhada (Tarde)') or df_row.get('Atividade Detalhada (Noite)') or "")
        row_idx = find_row_index(worksheet, target_date, aluno, activity_hint)
        if not row_idx: return False
        updated=False
        for p in ["Manhã","Tarde","Noite"]:
            col_name = f"% Concluído ({p})"
            if col_name in headers:
                ci = headers.index(col_name)+1
                if try_update_cell(worksheet, row_idx, ci, "100%"):
                    updated=True
        if 'Hora Conclusão' not in headers:
            try:
                first_row = worksheet.row_values(1)
                first_row.append('Hora Conclusão')
                worksheet.update(values=[first_row], range='1:1')
                headers.append('Hora Conclusão')
            except Exception:
                pass
        if 'Hora Conclusão' in headers:
            ci = headers.index('Hora Conclusão')+1
            if try_update_cell(worksheet, row_idx, ci, datetime.now().strftime('%H:%M:%S')):
                updated=True
        return updated
    except Exception as e:
        st.error("Erro mark_done: "+str(e)[:200])
        return False

# ----------------------------
# Analytics using st charts
# ----------------------------
def show_analytics(df):
    st.subheader("Visão geral — Progresso")
    if df.empty:
        st.info("Sem dados para analytics.")
        return
    def avg_completion(row):
        vals=[]
        for p in ["Manhã","Tarde","Noite"]:
            col=f"% Concluído ({p})"
            if col in row.index:
                try: vals.append(float(row[col]))
                except: vals.append(0.0)
        return np.mean(vals) if vals else 0.0
    df_local = df.copy()
    df_local['avg_pct'] = df_local.apply(avg_completion, axis=1)
    agg = df_local.groupby('Aluno(a)')['avg_pct'].mean().fillna(0.0)
    if not agg.empty:
        st.write("Conclusão média por aluno")
        st.bar_chart(agg)
    period_avgs={}
    for p in ["Manhã","Tarde","Noite"]:
        col=f"% Concluído ({p})"
        if col in df.columns:
            try: period_avgs[p]=float(df[col].astype(float).mean())
            except: period_avgs[p]=0.0
        else: period_avgs[p]=0.0
    st.write("Média por período")
    st.bar_chart(pd.Series(period_avgs))

def calendar_progress_chart(df, aluno):
    df_a = df[(df['Aluno(a)']==aluno) | (df['Aluno(a)']=='Ambos')].copy()
    if df_a.empty:
        st.info("Sem dados de progresso para este aluno.")
        return
    df_a['date'] = df_a['Data'].dt.date
    def day_mean(g):
        vals=[]
        for p in ["Manhã","Tarde","Noite"]:
            col=f"% Concluído ({p})"
            if col in g.columns:
                try: vals.append(g[col].astype(float).mean())
                except: vals.append(0.0)
        return np.mean(vals) if vals else 0.0
    agg = df_a.groupby('date').apply(day_mean).rename("mean_completion")
    if not agg.empty:
        st.write("Progresso diário")
        st.line_chart(agg)

# ----------------------------
# Pomodoro (client-side)
# ----------------------------
def pomodoro_widget():
    st.write("⏱️ Focus Mode")
    js = """
    <div>
      <button id="start">Iniciar 25:00</button>
      <button id="stop">Parar</button>
      <span id="timer" style="font-weight:800;margin-left:12px;">25:00</span>
    </div>
    <script>
    let timerInterval=null;
    function format(s){ let m=Math.floor(s/60); let sec=s%60; return String(m).padStart(2,'0')+':'+String(sec).padStart(2,'0'); }
    document.getElementById('start').onclick=()=>{ let total=25*60; if(timerInterval) clearInterval(timerInterval); timerInterval=setInterval(()=>{ document.getElementById('timer').innerText=format(total); total--; if(total<0){ clearInterval(timerInterval); alert('Pomodoro finalizado!'); } },1000); }
    document.getElementById('stop').onclick=()=>{ if(timerInterval) clearInterval(timerInterval); timerInterval=null; document.getElementById('timer').innerText='25:00'; }
    </script>
    """
    st.components.v1.html(js, height=80)

# ----------------------------
# Anki export
# ----------------------------
def anki_csv_download(cards, filename):
    dfc = pd.DataFrame(cards, columns=["Front","Back"])
    csv = dfc.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Baixar CSV (Anki)", data=csv, file_name=filename, mime="text/csv")

# ----------------------------
# XP / streak / re-agendamento inteligente
# ----------------------------
def compute_xp(df, aluno):
    xp=0
    df_aluno = df[(df['Aluno(a)']==aluno) | (df['Aluno(a)']=='Ambos')].copy()
    if df_aluno.empty: return 0,0
    df_aluno['date_only'] = df_aluno['Data'].dt.date
    days = sorted(df_aluno['date_only'].dropna().unique())
    today = (datetime.now(timezone.utc)-timedelta(hours=3)).date()
    streak=0
    recent=[d for d in days if d<=today]
    last = max(recent) if recent else None
    cur=last
    while cur:
        day_rows = df_aluno[df_aluno['date_only']==cur]
        complete=False
        for p in ["Manhã","Tarde","Noite"]:
            col=f"% Concluído ({p})"
            if col in day_rows.columns and (day_rows[col].astype(float) >= 1.0).any():
                complete=True
        if complete: streak+=1; cur=cur-timedelta(days=1)
        else: break
    for p in ["Manhã","Tarde","Noite"]:
        col=f"% Concluído ({p})"
        if col in df_aluno.columns:
            xp += int((df_aluno[col].astype(float) >= 1.0).sum()) * 10
    return xp, streak

def recommend_spaced_repetition(row):
    d = int(row.get("Dificuldade (1-5)",0) or 0)
    if d>=4: return ["24h","72h","7d"]
    if d==3: return ["48h","7d"]
    return ["72h","10d"]

def smart_reschedule(df, worksheet, headers, aluno, pct_threshold=0.5, max_push_days=7):
    report={"moved":0,"failed":0,"details":[]}
    try:
        df_copy = df.copy()
        for idx, row in df_copy.iterrows():
            if row.get("Aluno(a)") not in [aluno,"Ambos"]: continue
            date = row.get("Data"); 
            if pd.isna(date): continue
            for period in ["Manhã","Tarde","Noite"]:
                pct_col = f"% Concluído ({period})"
                if pct_col not in df.columns: continue
                try: pct = float(row.get(pct_col,0.0) or 0.0)
                except: pct = 0.0
                if pct < pct_threshold:
                    for d in range(1,max_push_days+1):
                        new_date = (date+timedelta(days=d)).date()
                        exists = ((df['Data'].dt.date == new_date) & ((df['Aluno(a)']==aluno)|(df['Aluno(a)']=='Ambos'))).any()
                        if not exists:
                            row_idx = find_row_index(worksheet, date, row.get("Aluno(a)"), row.get(f"Atividade Detalhada ({period})",""))
                            if row_idx:
                                try:
                                    col_idx = headers.index("Data")+1
                                    if try_update_cell(worksheet, row_idx, col_idx, new_date.strftime('%d/%m/%Y')):
                                        report["moved"]+=1
                                        report["details"].append(f"{row.get('Aluno(a)')} {period} {date.strftime('%d/%m/%Y')} -> {new_date.strftime('%d/%m/%Y')}")
                                    else:
                                        report["failed"]+=1
                                    break
                                except Exception as e:
                                    report["failed"]+=1
                                    report["details"].append(str(e)[:120])
                                    break
                            else:
                                report["failed"]+=1
                                report["details"].append("Linha não encontrada")
                                break
    except Exception as e:
        report["failed"]+=1
        report["details"].append(str(e)[:150])
    return report

# ----------------------------
# IA prompts
# ----------------------------
def build_activity_prompt(row, period_label):
    subj = row.get(f"Matéria ({period_label})","")
    act = row.get(f"Atividade Detalhada ({period_label})","")
    diff = int(row.get("Dificuldade (1-5)",0) or 0)
    return f"Você é um coach de estudos. Resuma em 1 parágrafo e entregue 3 passos práticos. Matéria: {subj}. Atividade: {act}. Dificuldade: {diff}. Em português."

def generate_quiz_prompt(row, period_label, n=4):
    subj = row.get(f"Matéria ({period_label})","")
    desc = row.get(f"Atividade Detalhada ({period_label})","")
    return f"Crie um mini-quiz de {n} questões sobre '{subj}' com foco em {desc}. Dê enunciado, alternativas A-D e no final 'Gabarito: A,B,...'. Em português."

# ----------------------------
# Main UI
# ----------------------------
def show_login():
    st.markdown("<div class='card'><div style='display:flex;gap:12px;align-items:center;'><div style='font-size:40px'>👋</div><div><b>Escolha seu perfil</b><div class='small-muted'>Clique para entrar como Mateus ou Ana</div></div></div><hr></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👨‍🎓 Mateus", key="login_m"):
            st.session_state.logged_user = "Mateus"; safe_rerun()
    with col2:
        if st.button("👩‍🎓 Ana", key="login_a"):
            st.session_state.logged_user = "Ana"; safe_rerun()

def main():
    # session init
    if 'logged_user' not in st.session_state: st.session_state.logged_user = None
    if '_auto_coach_cache' not in st.session_state: st.session_state['_auto_coach_cache'] = {}

    # connect
    client, client_email = connect_to_google_sheets()

    # sidebar: diagnosis & controls
    st.sidebar.title("Configurações & Diagnóstico")
    if client_email:
        st.sidebar.success(f"Service account: `{client_email}`")
    else:
        st.sidebar.info("Service account não encontrada nos secrets. Verifique st.secrets['gcp_service_account'].")
    st.sidebar.markdown("---")
    st.sidebar.write("Compartilhe a planilha com o service account (Editor).")
    st.sidebar.markdown("---")
    ia_enabled = st.sidebar.checkbox("Ativar IA (Groq)", value=True if st.secrets.get('GROQ_API_KEY') else False)
    auto_coach = st.sidebar.checkbox("Auto-Coach ao abrir (pode gerar chamadas IA)", value=False)
    st.sidebar.write("Se ativar Auto-Coach, o app chamará a IA para cada tarefa de hoje (limite: 1 chamada por tarefa por sessão).")
    st.sidebar.markdown("---")
    st.sidebar.write("Modelos: configure via secrets: GROQ_MODEL / GROQ_FALLBACK_MODEL")

    if not client:
        st.error("Não foi possível conectar ao Google Sheets — verifique secrets e permissão do service account.")
        return

    spreadsheet_id = st.secrets.get("SPREADSHEET_ID_OR_URL","")
    sheet_tab_name = st.secrets.get("SHEET_TAB_NAME","Cronograma")
    df, worksheet, headers = load_data(client, spreadsheet_id, sheet_tab_name)
    if df is None or df.empty:
        st.warning("Planilha vazia ou erro ao ler. Verifique ID/ABA/permissões.")
        if not st.session_state.logged_user:
            show_login()
        return

    headers = ensure_id_column(worksheet, headers)

    if not st.session_state.logged_user:
        show_login(); return

    user = st.session_state.logged_user
    st.markdown(f"<div style='display:flex;justify-content:space-between;align-items:center'><div><h2 style='margin:0;'>{user} — Hoje</h2><div class='small-muted'>Plano do dia + sugestões automáticas</div></div><div><span class='metric-box'>🎯 Meta: concluir tarefas</span></div></div>", unsafe_allow_html=True)

    today = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    df_valid = df[df['Data'].notna()]
    df_today = df_valid[df_valid['Data'].dt.date == today]
    df_user_today = df_today[(df_today['Aluno(a)']==user) | (df_today['Aluno(a)']=='Ambos')]

    xp, streak = compute_xp(df, user)
    colx1, colx2, colx3 = st.columns([1,1,2])
    colx1.metric("XP", xp)
    colx2.metric("Streak (dias)", streak)
    colx3.metric("Tarefas hoje", len(df_user_today))

    # Auto coach generation
    if auto_coach and ia_enabled:
        # geramos se não gerado nesta sessão para essa data
        cache_key = f"{user}_{today}"
        if cache_key not in st.session_state['_auto_coach_cache']:
            st.session_state['_auto_coach_cache'][cache_key] = {}
            # itera e gera coach para cada tarefa (1 chamada por tarefa)
            for idx, row in df_user_today.iterrows():
                period = "Manhã"
                prompt = build_activity_prompt(row, period)
                ok, out, used = call_groq_api(prompt)
                if ok:
                    st.session_state['_auto_coach_cache'][cache_key][str(idx)] = {"ok":True,"text":out,"model":used}
                else:
                    st.session_state['_auto_coach_cache'][cache_key][str(idx)] = {"ok":False,"text":out,"model":used}
            st.experimental_rerun = safe_rerun  # ensure safe rerun binding (no-op if not used)
    # show tasks
    if df_user_today.empty:
        st.info("Sem tarefas para hoje — gere microplanos ou revise próximos dias.")
        if st.button("🔮 Gerar micro-plano IA (próximas 7)"):
            fut = df_valid[(df_valid['Aluno(a)']==user)|(df_valid['Aluno(a)']=='Ambos')].sort_values('Data').head(7)
            outputs=[]
            for _, r in fut.iterrows():
                if ia_enabled:
                    ok,out,used = call_groq_api(build_activity_prompt(r,"Manhã"))
                    outputs.append((ok,out,used,r.get("Data")))
                else:
                    outputs.append((False,fallback_summary(r,"Manhã"),None,r.get("Data")))
            for ok,out,used,d in outputs:
                st.write(f"**{d.strftime('%d/%m/%Y') if not pd.isna(d) else 'Sem data'}**")
                if ok:
                    st.info(out); st.caption(f"Modelo: {used}")
                else:
                    st.warning("IA indisponível — fallback abaixo"); st.info(out)
        calendar_progress_chart(df, user)
        return

    for idx, row in df_user_today.iterrows():
        st.markdown("<div class='card' style='margin-top:12px;'>", unsafe_allow_html=True)
        title = row.get("Matéria (Manhã)") or row.get("Matéria (Tarde)") or row.get("Matéria (Noite)") or "Atividade"
        st.markdown(f"<div class='task-title'>{title} <span class='small-muted'> — {row['Data'].strftime('%d/%m/%Y') if not pd.isna(row['Data']) else ''}</span></div>", unsafe_allow_html=True)
        left, right = st.columns([3,1])
        with left:
            st.write("**Manhã:**", row.get("Atividade Detalhada (Manhã)") or "—")
            st.write("**Tarde:**", row.get("Atividade Detalhada (Tarde)") or "—")
            st.write("**Noite:**", row.get("Atividade Detalhada (Noite)") or "—")
            st.write("Sugestão revisão:", ", ".join(recommend_spaced_repetition(row)))
            # auto-coach cached display
            cache_key = f"{user}_{today}"
            cached = st.session_state.get('_auto_coach_cache',{}).get(cache_key, {}).get(str(idx))
            if cached:
                if cached['ok']:
                    st.info(cached['text'])
                    st.caption(f"Modelo automático usado: {cached.get('model')}")
                else:
                    st.warning("Coach automático falhou: " + str(cached['text']))
        with right:
            for p in ["Manhã","Tarde","Noite"]:
                col_name = f"% Concluído ({p})"
                val = 0.0
                if col_name in row.index:
                    try: val = float(row[col_name] or 0.0)
                    except: val = 0.0
                st.metric(p, f"{int(val*100)}%")
            st.markdown("---")
            period = st.selectbox("Período", ["Manhã","Tarde","Noite"], key=f"period_{idx}")
            if st.button("💡 Coach IA", key=f"coach_{idx}"):
                if ia_enabled:
                    ok,out,used = call_groq_api(build_activity_prompt(row, period))
                    if ok:
                        st.info(out); st.caption(f"Modelo: {used}")
                    else:
                        st.warning("IA indisponível: " + out); st.info(fallback_summary(row,period))
                else:
                    st.info(fallback_summary(row, period))
            if st.button("❓ Quiz + Anki", key=f"quiz_{idx}"):
                if ia_enabled:
                    ok,out,used = call_groq_api(generate_quiz_prompt(row, period, 4))
                    if ok:
                        st.code(out); st.caption(f"Modelo: {used}")
                        st.download_button("📥 Baixar Quiz (txt)", data=out.encode('utf-8'), file_name=f"quiz_{user}_{row['Data'].strftime('%Y%m%d')}.txt", mime="text/plain")
                    else:
                        st.warning("IA indisponível — fallback local"); txt,cards = fallback_quiz(row, period, 3); st.code(txt); anki_csv_download(cards,f"anki_{user}_{row['Data'].strftime('%Y%m%d')}.csv")
                else:
                    txt,cards = fallback_quiz(row, period, 3); st.code(txt); anki_csv_download(cards,f"anki_{user}_{row['Data'].strftime('%Y%m%d')}.csv")
            if st.button("✅ Marcar Concluído", key=f"done_{idx}"):
                ok = mark_done(worksheet, row, headers)
                if ok:
                    st.success("Marcado concluído.")
                    try: load_data.clear()
                    except: pass
                    safe_rerun()
                else:
                    st.warning("Falha ao marcar concluído (permissões).")
            if st.button("📤 Reagendar Inteligente", key=f"resch_{idx}"):
                rpt = smart_reschedule(df, worksheet, headers, user)
                st.write(rpt)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    pomodoro_widget()
    st.markdown("---")
    show_analytics(df)
    calendar_progress_chart(df, user)
    st.markdown("---")
    st.download_button("📥 Exportar CSV geral", data=df.to_csv(index=False).encode('utf-8'), file_name=f"cronograma_full_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

if __name__ == "__main__":
    main()
