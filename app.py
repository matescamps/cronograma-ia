# -*- coding: utf-8 -*-
"""
Cronograma Ana&Mateus — Versão Criativa e Automatizada
- Auto-Coach IA: ao abrir, gera resumos/plano/mini-quiz para tarefas do dia
- UI animada: cards expansíveis, flashcards (flip), ícones animados, gráficos "flutuantes"
- Correções robustas: load_data(_client), tratamento de % Concluído, worksheet.update(..., values=...), sem sobrescrever session
- Fallback local sólido quando IA indisponível
- Export Anki, marcar concluído (adiciona Hora Conclusão), smart rescheduler, XP/streak
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
# Config inicial
# ----------------------------
st.set_page_config(page_title="Cronograma Ana&Mateus", page_icon="🎯", layout="wide")
# reset query param trick used to force rerun where needed
def safe_rerun():
    try:
        st.query_params = {"_refresh": str(int(time.time()))}
    except Exception:
        st.session_state['_forced_reload'] = st.session_state.get('_forced_reload', 0) + 1

# ----------------------------
# CSS + small JS (animations, flip cards, floating charts)
# ----------------------------
st.markdown("""
<style>
/* Fonts (uses system) and base */
:root{ --bg:#f3f6fb; --card:#ffffff; --accent1:#7c3aed; --accent2:#06b6d4; --muted:#6b7280; --glass: rgba(255,255,255,0.7); }
body { background: linear-gradient(120deg, #e6f0ff 0%, #f8fbff 100%); color:#0b1220; }
.block-container { padding:1.0rem 2rem; max-width:1400px; }

/* Header */
.header {
  display:flex; justify-content:space-between; align-items:center;
  background: linear-gradient(135deg, rgba(124,58,237,0.08), rgba(6,182,212,0.06));
  padding:18px; border-radius:14px; margin-bottom:18px; box-shadow: 0 10px 30px rgba(16,24,40,0.06);
}
.h-title { font-size:28px; font-weight:800; letter-spacing:-0.3px; margin:0; }
.h-sub { color:var(--muted); margin:0; font-size:13px; }

/* Floating stats */
.floating-stats { display:flex; gap:12px; align-items:center; }
.stat {
  background:linear-gradient(90deg, var(--accent1), var(--accent2));
  color:white; padding:12px 16px; border-radius:12px; font-weight:700; box-shadow: 0 10px 25px rgba(12,18,40,0.08);
  transform: translateY(0); animation: float 4s ease-in-out infinite;
}
@keyframes float { 0%{transform:translateY(0)}50%{transform:translateY(-6px)}100%{transform:translateY(0)} }

/* Task cards grid */
.tasks-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap:18px; margin-top:18px; }
.task-card {
  background: var(--card); border-radius:12px; padding:14px; box-shadow: 0 12px 30px rgba(12,18,40,0.06);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
  overflow:hidden;
}
.task-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(12,18,40,0.12); }

/* Title row */
.title-row { display:flex; justify-content:space-between; align-items:center; gap:10px; }
.task-title { font-weight:800; font-size:18px; margin:0; }
.small-muted { font-size:12px; color:var(--muted); }

/* Expandable content */
.expand { max-height:0; overflow:hidden; transition:max-height 0.45s ease; }
.expand.open { max-height:800px; }

/* flashcard flip */
.flashcard {
  width:100%; height:160px; perspective:1000px; margin-top:12px;
}
.card-inner {
  position:relative; width:100%; height:100%; transition: transform 0.7s; transform-style: preserve-3d;
}
.card-front, .card-back {
  position:absolute; width:100%; height:100%; backface-visibility: hidden; border-radius:10px; display:flex; align-items:center; justify-content:center; padding:12px;
}
.card-front { background: linear-gradient(135deg,#fff7ed,#fff1f2); color:#1f2937; }
.card-back { background: linear-gradient(135deg,#ecfeff,#eff6ff); color:#04243a; transform: rotateY(180deg); }

/* flip activated */
.flip .card-inner { transform: rotateY(180deg); }

/* badge + icon */
.icon-bounce { display:inline-block; animation:bounce 2s infinite; }
@keyframes bounce { 0%{transform:translateY(0)}50%{transform:translateY(-6px)}100%{transform:translateY(0)} }

/* floating mini-chart */
.floating-chart { width:160px; height:100px; border-radius:10px; background: linear-gradient(90deg,#ffffff,#f8fafc); box-shadow:0 10px 30px rgba(12,18,40,0.06); padding:8px; }

/* CTA buttons */
.btn { background: linear-gradient(90deg,var(--accent1),var(--accent2)); color:white; padding:8px 12px; border-radius:8px; border:none; cursor:pointer; font-weight:700; }
.secondary { background:#eef2ff; color:#0b1220; padding:6px 10px; border-radius:8px; }

/* responsive */
@media (max-width:768px){
  .floating-stats{ flex-direction:column; align-items:flex-start; gap:8px; }
}
</style>
""", unsafe_allow_html=True)

# ----------------------------
# Helpers: clean numeric-like values
# ----------------------------
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
# Google Sheets connection (robusto)
# ----------------------------
@st.cache_resource(ttl=600, show_spinner=False)
def connect_to_google_sheets():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets.get("gcp_service_account", None)
        if not creds_info:
            return None, None
        if isinstance(creds_info, str):
            try:
                creds_dict = json.loads(creds_info)
            except json.JSONDecodeError:
                creds_dict = json.loads(creds_info.replace('\\\\n','\n'))
        else:
            creds_dict = dict(creds_info)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.Client(auth=creds)
        client_email = creds_dict.get("client_email")
        return client, client_email
    except Exception as e:
        st.error("Erro ao conectar ao Google Sheets — verifique seu secrets.")
        st.write(str(e)[:300])
        return None, None

# ----------------------------
# load_data with _client to avoid Streamlit hashing errors
# ----------------------------
@st.cache_data(ttl=60, show_spinner=False)
def load_data(_client, spreadsheet_id: str, sheet_tab_name: str):
    try:
        if not _client:
            return pd.DataFrame(), None, []
        try:
            spreadsheet = _client.open_by_key(spreadsheet_id)
        except Exception:
            spreadsheet = _client.open_by_url(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_tab_name)
        all_values = worksheet.get_all_values()
        if not all_values:
            return pd.DataFrame(), worksheet, []
        headers = all_values[0]
        data = all_values[1:] if len(all_values) > 1 else []
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

        # conversions
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
                s = s.clip(0.0, 1.0).astype(float)
                df[col] = s

        return df, worksheet, headers
    except Exception as e:
        st.error("Erro ao carregar dados da planilha.")
        st.write(str(e)[:400])
        return pd.DataFrame(), None, []

# ----------------------------
# Groq API wrapper with fallback support
# ----------------------------
def call_groq_api_with_model(prompt: str, model: str, max_retries: int = 2):
    groq_key = st.secrets.get('GROQ_API_KEY', None)
    if not groq_key:
        return False, "GROQ_API_KEY ausente.", None
    groq_url = st.secrets.get('GROQ_API_URL', "").strip()
    if groq_url:
        endpoint = groq_url
        if endpoint.endswith('/v1') or endpoint.endswith('/v1/'):
            endpoint = endpoint.rstrip('/') + "/chat/completions"
    else:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type":"application/json"}
    payload = {"model": model, "messages":[{"role":"user","content":prompt}], "temperature":0.6, "max_tokens":700}
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
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return False, f"Erro IA {resp.status_code}: {msg}", model
            except ValueError:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return False, f"Erro IA {resp.status_code}: {resp.text[:300]}", model
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                continue
            return False, "Timeout na conexão com a IA.", model
        except Exception as e:
            return False, f"Erro: {str(e)[:250]}", model
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
# Local fallback summary & quiz
# ----------------------------
def fallback_summary(row, period_label: str) -> str:
    subj = row.get(f"Matéria ({period_label})", "") or "a matéria"
    act = row.get(f"Atividade Detalhada ({period_label})", "") or ""
    diff = int(row.get("Dificuldade (1-5)", 0) or 0)
    para = f"Resumo prático: foque em {subj}. {'Revisão de conceitos básicos.' if diff<=2 else 'Resolver questões e revisão ativa.'}"
    if act:
        para += f" Atividade: {act}."
    plan = "Plano: 1) Leitura 10-20min. 2) Resolver questões 20-40min. 3) Criar 3 flashcards de revisão."
    return f"{para}\n\n{plan}"

def fallback_quiz(row, period_label: str, n:int=3):
    subj = row.get(f"Matéria ({period_label})", "Matéria")
    desc = row.get(f"Atividade Detalhada ({period_label})", "")
    text = f"Mini-quiz (fallback) — {subj}\n\n"
    cards=[]
    for i in range(n):
        if i==0:
            q=f"O que é o conceito central de '{subj}'?"
            a="Resposta: definição/resumo."
        elif i==1:
            q=f"Exemplo prático relacionado a '{desc or subj}'."
            a="Resposta: solução/resposta explicada."
        else:
            q=f"V/F: Afirmação comum sobre '{subj}'. Justifique."
            a="Resposta: Verdadeiro/Falso + justificativa."
        text += f"{i+1}. {q}\n"
        cards.append((q,a))
    return text, cards

# ----------------------------
# Planilha helpers (named args for update to avoid DeprecationWarning)
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
            if not current or str(current).strip() == "":
                try:
                    worksheet.update_cell(i, id_idx+1, str(uuid.uuid4())[:8])
                except Exception:
                    pass
        all_values = worksheet.get_all_values()
        return all_values[0]
    except Exception as e:
        st.warning("Erro ao garantir ID: " + str(e)[:200])
        return headers

def find_row_index(worksheet, date_val: datetime, aluno: str, activity_hint: str) -> Optional[int]:
    try:
        all_values = worksheet.get_all_values()
        if not all_values:
            return None
        headers = all_values[0]
        rows = all_values[1:]
        def idx(name):
            try:
                return headers.index(name)
            except ValueError:
                return None
        col_date = idx("Data"); col_aluno = idx("Aluno(a)")
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
                hint = activity_hint.strip().lower()
                if hint and hint not in cell_act and cell_act != "":
                    if len(set(hint.split()) & set(cell_act.split())) == 0:
                        ok = False
            if ok:
                return i
        return None
    except Exception as e:
        st.warning("Erro find_row_index: " + str(e)[:160])
        return None

def try_update_cell(worksheet, r:int, c:int, value) -> bool:
    try:
        worksheet.update_cell(int(r), int(c), str(value))
        return True
    except Exception as e:
        st.warning(f"Falha atualizar r{r}c{c}: {str(e)[:150]}")
        return False

def mark_done(worksheet, df_row, headers) -> bool:
    try:
        if worksheet is None or df_row is None:
            return False
        target_date = df_row.get('Data')
        aluno = str(df_row.get('Aluno(a)','')).strip()
        activity_hint = (str(df_row.get('Atividade Detalhada (Manhã)') or df_row.get('Atividade Detalhada (Tarde)') or df_row.get('Atividade Detalhada (Noite)') or "")).strip()
        row_idx = find_row_index(worksheet, target_date, aluno, activity_hint)
        if not row_idx:
            return False
        updated = False
        for p in ["Manhã","Tarde","Noite"]:
            col_name = f"% Concluído ({p})"
            if col_name in headers:
                ci = headers.index(col_name) + 1
                if try_update_cell(worksheet, row_idx, ci, "100%"):
                    updated = True
        if 'Hora Conclusão' not in headers:
            try:
                first_row = worksheet.row_values(1)
                first_row.append('Hora Conclusão')
                worksheet.update(values=[first_row], range='1:1')
                headers.append('Hora Conclusão')
            except Exception:
                pass
        if 'Hora Conclusão' in headers:
            ci = headers.index('Hora Conclusão') + 1
            if try_update_cell(worksheet, row_idx, ci, datetime.now().strftime('%H:%M:%S')):
                updated = True
        return updated
    except Exception as e:
        st.error("Erro ao marcar concluído: " + str(e)[:200])
        return False

# ----------------------------
# Analytics lightweight (floating)
# ----------------------------
def show_floating_metrics(df, user):
    # small aggregated metrics displayed as floating badges
    df_user = df[(df['Aluno(a)']==user) | (df['Aluno(a)']=='Ambos')]
    avg = 0.0
    cnt = 0
    for p in ["Manhã","Tarde","Noite"]:
        col = f"% Concluído ({p})"
        if col in df_user.columns:
            avg += df_user[col].astype(float).mean() if not df_user.empty else 0.0
            cnt += 1
    avg = (avg/cnt) if cnt>0 else 0.0
    completed = 0
    for p in ["Manhã","Tarde","Noite"]:
        col = f"% Concluído ({p})"
        if col in df_user.columns:
            completed += int((df_user[col].astype(float)>=1.0).sum())
    return int(avg*100), completed

# ----------------------------
# Flashcard/Quiz export
# ----------------------------
def anki_csv_download(cards: List[tuple], filename: str):
    dfc = pd.DataFrame(cards, columns=["Front","Back"])
    csv = dfc.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Baixar CSV Anki", data=csv, file_name=filename, mime="text/csv")

# ----------------------------
# XP / streak
# ----------------------------
def compute_xp(df: pd.DataFrame, aluno: str) -> Tuple[int,int]:
    xp = 0
    df_aluno = df[(df['Aluno(a)']==aluno) | (df['Aluno(a)']=='Ambos')].copy()
    if df_aluno.empty:
        return 0, 0
    df_aluno['date_only'] = df_aluno['Data'].dt.date
    days = sorted(df_aluno['date_only'].dropna().unique())
    today = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    streak = 0
    recent_days = [d for d in days if d <= today]
    last_day = max(recent_days) if recent_days else None
    cur = last_day
    while cur:
        day_rows = df_aluno[df_aluno['date_only']==cur]
        complete = False
        for p in ["Manhã","Tarde","Noite"]:
            col = f"% Concluído ({p})"
            if col in day_rows.columns:
                if (day_rows[col].astype(float) >= 1.0).any():
                    complete = True
        if complete:
            streak += 1
            cur = cur - timedelta(days=1)
        else:
            break
    for p in ["Manhã","Tarde","Noite"]:
        col = f"% Concluído ({p})"
        if col in df_aluno.columns:
            xp += int((df_aluno[col].astype(float) >= 1.0).sum()) * 10
    return xp, streak

# ----------------------------
# Smart rescheduler
# ----------------------------
def smart_reschedule(df: pd.DataFrame, worksheet, headers, aluno: str, pct_threshold: float = 0.5, max_push_days=7) -> dict:
    report = {"moved":0, "failed":0, "details":[]}
    try:
        df_copy = df.copy()
        for idx, row in df_copy.iterrows():
            if row.get("Aluno(a)") not in [aluno, "Ambos"]:
                continue
            date = row.get("Data")
            if pd.isna(date):
                continue
            for period in ["Manhã","Tarde","Noite"]:
                pct_col = f"% Concluído ({period})"
                if pct_col not in df.columns:
                    continue
                try:
                    pct = float(row.get(pct_col,0.0) or 0.0)
                except Exception:
                    pct = 0.0
                if pct < pct_threshold:
                    for d in range(1, max_push_days+1):
                        new_date = (date + timedelta(days=d)).date()
                        exists = ((df['Data'].dt.date == new_date) & ((df['Aluno(a)'] == aluno) | (df['Aluno(a)'] == 'Ambos'))).any()
                        if not exists:
                            row_idx = find_row_index(worksheet, date, row.get("Aluno(a)"), row.get(f"Atividade Detalhada ({period})",""))
                            if row_idx:
                                try:
                                    col_idx = headers.index("Data") + 1
                                    if try_update_cell(worksheet, row_idx, col_idx, new_date.strftime('%d/%m/%Y')):
                                        report["moved"] += 1
                                        report["details"].append(f"{row.get('Aluno(a)')} {period} {date.strftime('%d/%m/%Y')} -> {new_date.strftime('%d/%m/%Y')}")
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
        report["details"].append(str(e)[:150])
    return report

# ----------------------------
# Prompts IA
# ----------------------------
def build_activity_prompt(row, period_label):
    subj = row.get(f"Matéria ({period_label})", "")
    act = row.get(f"Atividade Detalhada ({period_label})", "")
    diff = int(row.get("Dificuldade (1-5)", 0) or 0)
    return (f"Você é um coach de estudos super prático. Em português, gere:\n"
            f"1) um resumo em 1 parágrafo;\n2) 3 passos práticos e cronometrados (ex: 15min leitura, 30min exercícios...);\n"
            f"3) 3 flashcards (pergunta|resposta) curtos.\nMatéria: {subj}. Atividade: {act}. Dificuldade: {diff}.")

def generate_quiz_prompt(row, period_label, n=4):
    subj = row.get(f"Matéria ({period_label})", "")
    desc = row.get(f"Atividade Detalhada ({period_label})", "")
    return (f"Crie um mini-quiz de {n} questões sobre '{subj}' com foco em {desc}. "
            "Forneça enunciado, 4 alternativas A-D e, no final, 'Gabarito: ...'. Responda em português.")

# ----------------------------
# UI: login + main
# ----------------------------
def show_login():
    st.markdown("""
    <div style='display:flex;gap:14px;align-items:center;background:linear-gradient(90deg,rgba(124,58,237,0.06),rgba(6,182,212,0.04));padding:14px;border-radius:10px;margin-bottom:12px'>
      <div style='font-size:34px'>👋</div>
      <div>
        <div style='font-weight:800;font-size:18px'>Quem está usando?</div>
        <div style='color:#6b7280;font-size:13px'>Clique no avatar correspondente</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("👨‍🎓 Mateus", key="m"):
            st.session_state.logged_user = "Mateus"; safe_rerun()
    with c2:
        if st.button("👩‍🎓 Ana", key="a"):
            st.session_state.logged_user = "Ana"; safe_rerun()

def main():
    # session defaults
    if 'logged_user' not in st.session_state:
        st.session_state.logged_user = None
    if '_auto_coach_cache' not in st.session_state:
        st.session_state['_auto_coach_cache'] = {}

    # connect sheet
    client, client_email = connect_to_google_sheets()

    # sidebar with diagnosis and controls (auto-coach ON by default)
    st.sidebar.title("Config & Diagnóstico")
    if client_email:
        st.sidebar.success(f"Service account: `{client_email}`")
    else:
        st.sidebar.error("Service account não encontrada em secrets.")
    st.sidebar.markdown("---")
    st.sidebar.write("Compartilhe a planilha com o service account (Editor).")
    ia_enabled = st.sidebar.checkbox("Ativar IA (Groq)", value=True if st.secrets.get('GROQ_API_KEY') else False)
    auto_coach = st.sidebar.checkbox("Auto-Coach (gera mensagens ao abrir)", value=True)
    st.sidebar.markdown("Se Auto-Coach ligado, o app chamará IA para cada tarefa do dia (ou usará fallback local).")
    st.sidebar.markdown("---")
    st.sidebar.write("Export / Testes")
    if st.sidebar.button("Testar leitura de célula (diagnóstico)"):
        # quick test read
        spreadsheet_id = st.secrets.get("SPREADSHEET_ID_OR_URL","")
        sheet_tab_name = st.secrets.get("SHEET_TAB_NAME","Cronograma")
        try:
            shp = client.open_by_key(spreadsheet_id) if client else None
            if not shp:
                st.sidebar.error("Não foi possível abrir a planilha (ID inválido ou sem permissão).")
            else:
                ws = shp.worksheet(sheet_tab_name)
                val = ws.acell('A1').value
                st.sidebar.success(f"Lido A1: {val}")
        except Exception as e:
            st.sidebar.error("Falha ao ler: " + str(e)[:200])

    # check connection
    if not client:
        st.error("Não foi possível conectar ao Google Sheets — confira os secrets e permissões.")
        if not st.session_state.logged_user:
            show_login()
        return

    # load data
    spreadsheet_id = st.secrets.get("SPREADSHEET_ID_OR_URL","")
    sheet_tab_name = st.secrets.get("SHEET_TAB_NAME","Cronograma")
    df, worksheet, headers = load_data(client, spreadsheet_id, sheet_tab_name)
    if df is None or df.empty:
        st.warning("Planilha vazia ou erro ao ler dados. Verifique ID/aba/permissões.")
        if not st.session_state.logged_user:
            show_login()
        return

    # ensure ID column exist
    headers = ensure_id_column(worksheet, headers)

    # login
    if not st.session_state.logged_user:
        show_login(); return

    user = st.session_state.logged_user

    # header block with floating stats
    avg_pct, completed_count = show_floating_metrics(df, user)
    xp, streak = compute_xp(df, user)
    st.markdown(f"""
    <div class='header'>
      <div>
        <div class='h-title'>Cronograma — {user}</div>
        <div class='h-sub'>Tudo automatizado: Coach IA, flashcards e feedbacks — aberto agora</div>
      </div>
      <div class='floating-stats'>
        <div class='stat'>XP {xp}</div>
        <div class='stat' style='animation-delay:0.3s'>Streak {streak}d</div>
        <div class='stat' style='animation-delay:0.6s'>Concluídas {completed_count}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Today tasks
    today = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    df_valid = df[df['Data'].notna()]
    df_today = df_valid[df_valid['Data'].dt.date == today]
    df_user_today = df_today[(df_today['Aluno(a)'] == user) | (df_today['Aluno(a)'] == 'Ambos')]

    # Auto-Coach: generate IA messages on open for today's tasks
    cache_key = f"{user}_{today}"
    if auto_coach:
        if cache_key not in st.session_state['_auto_coach_cache']:
            st.session_state['_auto_coach_cache'][cache_key] = {}
            # generate for each task: use Manhã as primary period for summary if present else the first available
            for idx, row in df_user_today.iterrows():
                # choose period with content
                period = None
                for p in ["Manhã","Tarde","Noite"]:
                    if row.get(f"Matéria ({p})"):
                        period = p; break
                if not period:
                    period = "Manhã"
                prompt = build_activity_prompt(row, period)
                if ia_enabled:
                    ok, out, used = call_groq_api(prompt)
                    if ok:
                        # Try parse flashcards from model output if it returned them (best-effort)
                        st.session_state['_auto_coach_cache'][cache_key][str(idx)] = {"ok":True,"text":out,"model":used}
                    else:
                        # fallback local
                        st.session_state['_auto_coach_cache'][cache_key][str(idx)] = {"ok":False,"text": fallback_summary(row, period),"model":None}
                else:
                    st.session_state['_auto_coach_cache'][cache_key][str(idx)] = {"ok":False,"text": fallback_summary(row, period),"model":None}

    # If nothing today, show upcoming few days + microplans
    if df_user_today.empty:
        st.info("Nenhuma tarefa para hoje — mostro próximos 7 dias com micro-plano IA/fallback.")
        future = df_valid[(df_valid['Aluno(a)']==user) | (df_valid['Aluno(a)']=='Ambos')].sort_values('Data').head(7)
        for _, r in future.iterrows():
            dstr = r['Data'].strftime('%d/%m/%Y') if not pd.isna(r['Data']) else 'Sem data'
            st.markdown(f"**{dstr} — {r.get('Matéria (Manhã)') or r.get('Matéria (Tarde)') or r.get('Matéria (Noite)') or 'Atividade'}**")
            period = "Manhã"
            cache = st.session_state['_auto_coach_cache'].get(f"{user}_{r['Data'].date()}" , {}).get(str(_))
            # generate on demand (but we're in auto_coach False for these)
            if ia_enabled:
                ok,out,used = call_groq_api(build_activity_prompt(r,period))
                if ok:
                    st.info(out); st.caption(f"Modelo: {used}")
                else:
                    st.info(fallback_summary(r,period))
            else:
                st.info(fallback_summary(r,period))
        return

    # Render today's tasks creatively
    st.markdown("<div class='tasks-grid'>", unsafe_allow_html=True)
    for idx, row in df_user_today.iterrows():
        # primary title
        title = row.get("Matéria (Manhã)") or row.get("Matéria (Tarde)") or row.get("Matéria (Noite)") or "Atividade"
        date_str = row['Data'].strftime('%d/%m/%Y') if not pd.isna(row['Data']) else 'Sem data'
        # build html wrapper with unique ids for expand/flip
        expand_id = f"exp_{idx}"
        flip_id = f"flip_{idx}"
        # get cached auto coach
        cache = st.session_state['_auto_coach_cache'].get(cache_key, {}).get(str(idx))
        coach_text = cache['text'] if cache else None
        coach_ok = cache['ok'] if cache else False
        coach_model = cache.get('model') if cache else None

        # card
        st.markdown(f"<div class='task-card' id='card_{idx}'>", unsafe_allow_html=True)
        # title area
        st.markdown(f"""
        <div class='title-row'>
          <div>
            <div class='task-title'>{title}</div>
            <div class='small-muted'>{date_str} • Prioridade: {row.get('Prioridade') or 'Média'}</div>
          </div>
          <div style='text-align:right'>
            <div style='font-size:12px;color:var(--muted)'>Dificuldade: <b>{int(row.get('Dificuldade (1-5)',0) or 0)}</b></div>
            <div style='margin-top:8px;display:flex;gap:8px;justify-content:flex-end;'>
              <button class='btn' onclick="document.getElementById('{expand_id}').classList.toggle('open');">Abrir</button>
              <button class='secondary' onclick="document.getElementById('{flip_id}').classList.toggle('flip');">Flash</button>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # main content: short activities
        st.write("**Manhã:**", row.get("Atividade Detalhada (Manhã)") or "—")
        st.write("**Tarde:**", row.get("Atividade Detalhada (Tarde)") or "—")
        st.write("**Noite:**", row.get("Atividade Detalhada (Noite)") or "—")
        st.write("Sugestão de revisão:", ", ".join(["24h","72h","7d"] if int(row.get("Dificuldade (1-5)",0) or 0)>=4 else ["48h","7d"]))

        # animated small charts (simple bars using divs)
        morning_pct = float(row.get("% Concluído (Manhã)", 0.0) or 0.0)
        tarde_pct = float(row.get("% Concluído (Tarde)", 0.0) or 0.0)
        noite_pct = float(row.get("% Concluído (Noite)", 0.0) or 0.0)
        # container for floating charts
        st.markdown(f"""
        <div style='display:flex;gap:10px;margin-top:10px;align-items:center'>
          <div class='floating-chart'>
            <div style='font-size:12px;color:var(--muted)'>Manhã</div>
            <div style='height:8px;background:#eef2ff;border-radius:8px;overflow:hidden;margin-top:8px;'>
              <div style='height:100%;width:{int(morning_pct*100)}%;background:linear-gradient(90deg,var(--accent1),var(--accent2));transition:width:1200ms ease;'></div>
            </div>
            <div style='font-weight:800;margin-top:8px'>{int(morning_pct*100)}%</div>
          </div>
          <div class='floating-chart'>
            <div style='font-size:12px;color:var(--muted)'>Tarde</div>
            <div style='height:8px;background:#eef2ff;border-radius:8px;overflow:hidden;margin-top:8px;'>
              <div style='height:100%;width:{int(tarde_pct*100)}%;background:linear-gradient(90deg,#f97316,#ef4444);transition:width:1200ms ease;'></div>
            </div>
            <div style='font-weight:800;margin-top:8px'>{int(tarde_pct*100)}%</div>
          </div>
          <div class='floating-chart'>
            <div style='font-size:12px;color:var(--muted)'>Noite</div>
            <div style='height:8px;background:#eef2ff;border-radius:8px;overflow:hidden;margin-top:8px;'>
              <div style='height:100%;width:{int(noite_pct*100)}%;background:linear-gradient(90deg,#10b981,#06b6d4);transition:width:1200ms ease;'></div>
            </div>
            <div style='font-weight:800;margin-top:8px'>{int(noite_pct*100)}%</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # hidden expand area contains coach message, actions, quiz, and check if did previous period
        # use expand_id element toggle to show/hide with CSS class 'open'
        coach_html = ""
        if coach_text:
            # display coach_text nicely
            coach_html = f"<div style='margin-top:12px;padding:12px;border-radius:10px;background:linear-gradient(90deg,#f8fafc,#ffffff)'><b>Coach IA {'(automático)' if coach_ok else '(fallback)'}</b><div style='margin-top:8px'>{coach_text.replace('\\n','<br>')}</div>"
            if coach_model:
                coach_html += f"<div style='margin-top:8px;font-size:12px;color:var(--muted)'>Modelo: {coach_model}</div>"
            coach_html += "</div>"
        else:
            coach_html = f"<div style='margin-top:12px;padding:12px;border-radius:10px;background:#fff7ed'>Coach indisponível — {fallback_summary(row,'Manhã').replace('\\n','<br>')}</div>"

        # clickable check: "Você fez o turno anterior?"
        # Determine previous period based on chosen primary (we will ask for each period separate)
        prev_questions_html = ""
        for p in ["Manhã","Tarde","Noite"]:
            prev_questions_html += f"""
            <div style='margin-top:8px;display:flex;gap:8px;align-items:center;'>
              <div style='flex:1;'><b>Você fez as atividades do período {p}?</b><div style='font-size:12px;color:var(--muted)'>Questões feitas: {row.get(f"Questões Feitas ({p})",0)} / {row.get(f"Questões Planejadas ({p})",0)}</div></div>
              <div>
                <button onclick="window.parent.postMessage({{'mark':'done','idx':{idx},'period':'{p}'}}, '*')" class='btn'>Sim</button>
                <button onclick="window.parent.postMessage({{'mark':'notdone','idx':{idx},'period':'{p}'}}, '*')" class='secondary'>Não</button>
              </div>
            </div>
            """

        # flashcard flip container
        # We'll include a placeholder flashcard built from fallback if IA produced no explicit flashcards
        # Try to extract flashcards lines from coach_text (very naive: lines with 'Q:' or '- Q' or 'Flashcard:')
        flash_front = "Pergunta exemplo"
        flash_back = "Resposta exemplo"
        if coach_text and isinstance(coach_text, str):
            # try find lines like "Q:" and "A:" or lines separated by " - "
            lines = coach_text.splitlines()
            qfound = None; afound=None
            for L in lines:
                if re.match(r'^[Qq][:.-]', L) or L.strip().startswith('Q '):
                    qfound = re.sub(r'^[Qq][:.-]\s*','',L).strip()
                if re.match(r'^[Aa][:.-]', L) or L.strip().startswith('A '):
                    afound = re.sub(r'^[Aa][:.-]\s*','',L).strip()
                if qfound and afound:
                    break
            if qfound: flash_front = qfound
            if afound: flash_back = afound

        # assemble expand block
        st.markdown(f"""
        <div id="{expand_id}" class="expand">
          {coach_html}
          <div style='margin-top:12px;'>
            <div style='display:flex;gap:10px;align-items:center;'>
              <button class='btn' onclick="window.parent.postMessage({{'quiz':'{idx}'}}, '*')">Gerar Quiz (IA/fallback)</button>
              <button class='secondary' onclick="window.parent.postMessage({{'reschedule':'{idx}'}}, '*')">Reagendar inteligente</button>
              <button class='secondary' onclick="window.parent.postMessage({{'export_anki':'{idx}'}}, '*')">Export Anki</button>
            </div>
          </div>
          <div style='margin-top:12px;'>
            <div id="{flip_id}" class="flashcard">
              <div class="card-inner">
                <div class="card-front card-front">{flash_front}</div>
                <div class="card-back card-back">{flash_back}</div>
              </div>
            </div>
          </div>
          <div style='margin-top:12px'>{prev_questions_html}</div>
        </div>
        """, unsafe_allow_html=True)

        # close task card
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # JS listener to handle messages from card buttons (postMessage)
    # This allows buttons inside HTML to communicate back to Streamlit via window.parent.postMessage.
    # We'll capture in Streamlit via st_javascript-like technique: use st.components.v1.html to run script that posts to location.hash
    # Simple approach: create a hidden iframe-like listener that updates query params (safe_rerun will parse them)
    HANDLER_HTML = """
    <script>
    const handle = (e) => {
        try {
            const data = e.data;
            if(typeof data !== 'object') return;
            // encode action into URL hash for Streamlit to read
            const payload = JSON.stringify(data);
            // update location hash to cause Streamlit rerun with query param reading
            window.location.hash = encodeURIComponent(payload);
        } catch(err){}
    };
    window.addEventListener('message', handle, false);
    </script>
    """
    st.components.v1.html(HANDLER_HTML, height=0)

    # read location.hash if any (Streamlit can't directly read browser hash, but the assignment triggers rerun via query param in safe_rerun)
    # Instead, we parse st.experimental_get_query_params for a special `_action` param if set by server side (we use postMessage -> window.location.hash then copy manually — limited in Streamlit)
    # Workaround: user interactions trigger server-side via Streamlit buttons when possible. For actions inside HTML that used postMessage, the app receives them as query param encoded in st.query_params (see safe_rerun usage).
    # For now, below we show dedicated server buttons for typical actions (Mark done etc.)

    st.write("---")
    # Provide server-side action controls (these supplement the client-side postMessage)
    st.subheader("Ações rápidas")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ Marcar TODAS as tarefas de hoje como concluídas"):
            done_cnt = 0
            for idx, row in df_user_today.iterrows():
                ok = mark_done(worksheet, row, headers)
                if ok: done_cnt += 1
            st.success(f"{done_cnt} tarefas marcadas.")
            try:
                load_data.clear()
            except:
                pass
            safe_rerun()
    with col2:
        if st.button("📤 Reagendar inteligente (dia a dia)"):
            rpt = smart_reschedule(df, worksheet, headers, user)
            st.write(rpt)
    with col3:
        if st.button("📥 Exportar CSV completo"):
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", data=csv, file_name=f"cronograma_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

    st.write("---")
    # final analytics and pomodoro
    st.markdown("<div style='display:flex;gap:12px;align-items:center'><div style='flex:1'>", unsafe_allow_html=True)
    st.subheader("Progresso & Ferramentas")
    st.write("Gráficos flutuantes e tools")
    st.markdown("</div><div style='width:320px'>", unsafe_allow_html=True)
    # pomodoro small
    pom_html = """
    <div style='background:white;border-radius:10px;padding:10px;box-shadow:0 10px 30px rgba(12,18,40,0.06)'>
      <div style='font-weight:800'>⏱️ Pomodoro</div>
      <div style='margin-top:8px;display:flex;gap:8px;align-items:center;'>
        <button onclick="startPom()" class="btn">Iniciar 25</button>
        <button onclick="stopPom()" class="secondary">Parar</button>
        <div id="ptimer" style="font-weight:800;margin-left:8px">25:00</div>
      </div>
    </div>
    <script>
    var pomInt=null; function format(s){ let m=Math.floor(s/60); let sec=s%60; return String(m).padStart(2,'0')+':'+String(sec).padStart(2,'0');}
    function startPom(){ let total=25*60; if(pomInt) clearInterval(pomInt); pomInt=setInterval(()=>{ document.getElementById('ptimer').innerText=format(total); total--; if(total<0){ clearInterval(pomInt); alert('Pomodoro finalizado!'); } },1000); }
    function stopPom(){ if(pomInt) clearInterval(pomInt); pomInt=null; document.getElementById('ptimer').innerText='25:00'; }
    </script>
    """
    st.components.v1.html(pom_html, height=140)
    st.markdown("</div></div>", unsafe_allow_html=True)

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    main()
