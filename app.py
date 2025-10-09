# -*- coding: utf-8 -*-
"""
Cronograma Ana&Mateus — Versão compacta, profissional e auto-coach
- Auto-coach ao abrir (saudação + resumo/plano)
- Micro-chat: pergunte sobre o que tem hoje
- Flashcards já gerados e viráveis (flip)
- Robusto: load_data(_client), tratamento % Concluído, não sobrescreve client.session,
  worksheet.update(values=..., range=...), fallback local quando IA indisponível
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
st.set_page_config(page_title="Cronograma Ana & Mateus", page_icon="🎯", layout="wide")
# Use fonts + compact professional CSS
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
  body { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, Arial; }
  .header { display:flex; justify-content:space-between; align-items:center; gap:16px; }
  .title { font-weight:700; font-size:20px; margin:0; }
  .subtitle { color:#6b7280; margin:0; font-size:13px; }
  .card { background:white; border-radius:10px; padding:12px; box-shadow: 0 8px 24px rgba(12,18,30,0.06); }
  .small { color:#6b7280; font-size:13px; }
  .flash-front { background: linear-gradient(180deg,#ffffff,#fbfdff); padding:12px; border-radius:8px; min-height:70px; display:flex; align-items:center; justify-content:center; }
  .flash-back { background: linear-gradient(180deg,#f8fffb,#ecfdf5); padding:12px; border-radius:8px; min-height:70px; display:flex; align-items:center; justify-content:center; }
  .btn { background:#2563eb; color:white; padding:8px 12px; border-radius:8px; border:none; font-weight:700; cursor:pointer; }
  .btn-ghost { background:transparent; color:#2563eb; border:1px solid #e6eefc; padding:7px 10px; border-radius:8px; cursor:pointer; }
  .row { display:flex; gap:12px; align-items:center; }
  .metric { background:linear-gradient(90deg,#fff,#fbfdff); padding:10px; border-radius:8px; text-align:center; min-width:110px; }
  .muted { color:#6b7280; font-size:13px; }
  /* responsive */
  @media(max-width:768px){
    .row { flex-direction:column; align-items:flex-start; }
  }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# Utilities
# ----------------------------
def safe_rerun():
    """Trigger a rerun without experimental_rerun (compatível)."""
    st.session_state['_reload_token'] = st.session_state.get('_reload_token', 0) + 1

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
# Google Sheets connection (robusta)
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
            except json.JSONDecodeError:
                creds_dict = json.loads(creds_info.replace('\\\\n','\n'))
        else:
            creds_dict = dict(creds_info)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.Client(auth=creds)
        client_email = creds_dict.get("client_email")
        return client, client_email
    except Exception as e:
        st.error("Erro ao conectar ao Google Sheets — verifique seus secrets.")
        st.write(str(e)[:300])
        return None, None

# ----------------------------
# Load & normalize data (use _client to avoid Streamlit hashing issue)
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

        # normalizações seguras
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
                        if 'message' in first and isinstance(first['message'], dict) and 'content' in first['message']:
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
# Local fallback generator (summary + cards)
# ----------------------------
def fallback_summary_and_cards(row, period_label: str):
    subj = row.get(f"Matéria ({period_label})", "") or "a matéria"
    act = row.get(f"Atividade Detalhada ({period_label})", "") or ""
    diff = int(row.get("Dificuldade (1-5)", 0) or 0)
    summary = f"Resumo prático: concentre-se em {subj}. {'Revisão conceitual e mapas mentais.' if diff<=2 else 'Resolver questões e revisar erros.'}"
    if act:
        summary += f" Atividade: {act}."
    plan = "Plano: 1) Leitura ativa 15-25min; 2) Resolver 20-40min de questões; 3) Revisar erros e criar 3 flashcards."
    # create 3 simple flashcards (front, back)
    cards = [
        (f"O que é essencial sobre {subj}?", f"Resumo curto: {subj} — essencial."),
        (f"Exemplo prático de {subj}?", f"Exemplo/solução breve para {subj}."),
        (f"V/F: Uma afirmativa comum sobre {subj}?", "Resposta e justificativa.")
    ]
    return f"{summary}\n\n{plan}", cards

# ----------------------------
# Helpers planilha: ensure ID, find row, update cell, mark done
# ----------------------------
def ensure_id_column(worksheet, headers):
    try:
        if 'ID' in headers:
            return headers
        first_row = worksheet.row_values(1)
        first_row.append('ID')
        worksheet.update(values=[first_row], range='1:1')
        all_values = worksheet.get_all_values()
        return all_values[0]
    except Exception as e:
        st.warning("Erro ao garantir ID: " + str(e)[:160])
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
        st.error(f"Erro ao marcar concluído: {str(e)[:200]}")
        return False

# ----------------------------
# Flashcards helper: store flip state in session_state and display
# ----------------------------
def display_flashcards(cards: List[tuple], prefix: str):
    """
    cards: list of (front, back)
    prefix: unique prefix for session keys
    """
    for i, (f, b) in enumerate(cards):
        key = f"{prefix}_flip_{i}"
        if key not in st.session_state:
            st.session_state[key] = False
        col1, col2 = st.columns([4,1])
        with col1:
            if st.session_state[key]:
                st.markdown(f"<div class='flash-back'>{b}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='flash-front'>{f}</div>", unsafe_allow_html=True)
        with col2:
            if st.session_state[key]:
                if st.button("🔁 Voltar", key=f"{key}_back"):
                    st.session_state[key] = False
            else:
                if st.button("🔁 Virar", key=f"{key}_flipbtn"):
                    st.session_state[key] = True

# ----------------------------
# Build prompt & micro-chat logic
# ----------------------------
def build_activity_prompt(row, period_label):
    subj = row.get(f"Matéria ({period_label})", "")
    act = row.get(f"Atividade Detalhada ({period_label})", "")
    diff = int(row.get("Dificuldade (1-5)", 0) or 0)
    return (f"Você é um coach de estudos prático. Em português gere:\n"
            f"1) um resumo em 1 parágrafo para a atividade;\n"
            f"2) 3 passos práticos com tempos (ex: 15min leitura, 30min exercícios);\n"
            f"3) 3 flashcards no formato 'Pergunta | Resposta'.\n"
            f"Matéria: {subj}. Atividade: {act}. Dificuldade: {diff}.")

def microchat_answer(context_text: str, user_question: str) -> Tuple[bool,str]:
    """
    context_text: concatenado dos resumos/plans do dia
    user_question: pergunta do usuário
    Returns: (ok, answer_or_msg)
    """
    prompt = (f"Aqui está o contexto das tarefas do dia:\n{context_text}\n\n"
              f"Pergunta do aluno: {user_question}\nResponda de forma direta, prática e em português.")
    ok, out, used = call_groq_api(prompt)
    if ok:
        return True, out
    else:
        # fallback: uma resposta simples baseada no contexto (resumo)
        # extrair frases do contexto e responder com heurística
        txt = "Desculpe, IA indisponível. Com base no contexto: "
        # pega primeiras 2 linhas úteis do context
        lines = [l.strip() for l in context_text.splitlines() if l.strip()]
        txt += (" ".join(lines[:2])[:600] + "...")
        return False, txt

# ----------------------------
# Main UI
# ----------------------------
def main():
    st.session_state.setdefault('logged_user', None)
    st.session_state.setdefault('_coach_generated_for_date', None)
    st.session_state.setdefault('coach_messages', {})  # key: idx -> dict with summary, cards, model_used, ok

    # Connect
    client, client_email = connect_to_google_sheets()
    if client_email:
        email_info = client_email
    else:
        email_info = None

    # Sidebar: show service account email and controls
    st.sidebar.title("Configurações & Diagnóstico")
    if email_info:
        st.sidebar.success(f"Service account: {email_info}")
    else:
        st.sidebar.warning("Service account não detectada nos secrets.")
    st.sidebar.markdown("---")
    ia_enabled = st.sidebar.checkbox("Ativar IA (Groq)", value=True if st.secrets.get('GROQ_API_KEY') else False)
    st.sidebar.checkbox("Auto-Coach (gera mensagens ao abrir)", value=True, key="auto_coach_on_open")
    st.sidebar.markdown("Se IA estiver indisponível, o app usará fallback local (resumo+flashcards).")
    st.sidebar.markdown("---")
    st.sidebar.write("Compartilhe a planilha com o email do service account como Editor.")

    # If no client, stop early (but keep UI)
    if not client:
        st.error("Não foi possível conectar ao Google Sheets. Verifique secrets e permissões.")
        return

    spreadsheet_id = st.secrets.get("SPREADSHEET_ID_OR_URL", "")
    sheet_tab_name = st.secrets.get("SHEET_TAB_NAME", "Cronograma")
    df, worksheet, headers = load_data(client, spreadsheet_id, sheet_tab_name)
    if df is None or df.empty:
        st.warning("Planilha vazia ou leitura falhou. Verifique ID/ABA/permissões.")
        return

    # ensure ID column
    headers = ensure_id_column(worksheet, headers)

    # Quick login selection (simple)
    if st.session_state['logged_user'] is None:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Entrar como Mateus"):
                st.session_state['logged_user'] = "Mateus"
                safe_rerun()
        with c2:
            if st.button("Entrar como Ana"):
                st.session_state['logged_user'] = "Ana"
                safe_rerun()
        return

    user = st.session_state['logged_user']

    # Header: greeting + metrics small
    now = datetime.now(timezone.utc) - timedelta(hours=3)
    hour = now.hour
    greeting = "Bom dia" if 5 <= hour < 12 else "Boa tarde" if hour < 18 else "Boa noite"
    st.markdown(f"<div class='header'><div><div class='title'>{greeting}, {user} — Cronograma</div><div class='subtitle'>Resumo automático e flashcards para hoje</div></div><div class='row'><div class='metric'><div style='font-size:12px' class='muted'>Hoje</div><div style='font-weight:700'>{now.strftime('%d/%m/%Y')}</div></div></div></div>", unsafe_allow_html=True)

    # Today's tasks
    today = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    df_valid = df[df['Data'].notna()]
    df_today = df_valid[df_valid['Data'].dt.date == today]
    df_user_today = df_today[(df_today['Aluno(a)'] == user) | (df_today['Aluno(a)'] == 'Ambos')].reset_index()

    # Auto-coach generation: only once per date/user
    coached_key = f"{user}_{today.isoformat()}"
    auto_coach = st.session_state.get('auto_coach_on_open', True)
    if auto_coach and st.session_state.get('_coach_generated_for_date') != coached_key:
        st.session_state['coach_messages'] = {}
        # generate per-task coach messages
        for _, row in df_user_today.iterrows():
            idx = int(row['index'])
            # choose period to describe (prefer Manhã > Tarde > Noite)
            period = "Manhã"
            for p in ["Manhã","Tarde","Noite"]:
                if row.get(f"Matéria ({p})"):
                    period = p
                    break
            prompt = build_activity_prompt(row, period)
            if ia_enabled:
                ok, out, used = call_groq_api(prompt)
                if ok:
                    # try to extract flashcards from out (nao confiável) — fallback if fail
                    # simple parse: lines with '|' separate card
                    cards = []
                    for ln in out.splitlines():
                        if "|" in ln and len(cards) < 6:
                            parts = ln.split("|")
                            q = parts[0].strip()
                            a = parts[1].strip() if len(parts) > 1 else ""
                            if q:
                                cards.append((q, a if a else "—"))
                    # if no cards found, fallback generator
                    if not cards:
                        summary, cards = fallback_summary_and_cards(row, period)
                    else:
                        summary = out
                    st.session_state['coach_messages'][str(idx)] = {"ok": True, "summary": summary, "cards": cards, "model": used}
                else:
                    # IA failed: fallback
                    summary, cards = fallback_summary_and_cards(row, period)
                    st.session_state['coach_messages'][str(idx)] = {"ok": False, "summary": summary, "cards": cards, "model": None}
            else:
                summary, cards = fallback_summary_and_cards(row, period)
                st.session_state['coach_messages'][str(idx)] = {"ok": False, "summary": summary, "cards": cards, "model": None}
        st.session_state['_coach_generated_for_date'] = coached_key

    # UI layout small + professional
    left_col, right_col = st.columns([3,1])

    # Left: tasks list with expander showing coach summary + flashcards
    with left_col:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("### Tarefas de Hoje")
        if df_user_today.empty:
            st.info("Nenhuma tarefa para hoje. Deseja gerar micro-plano para próximos 7 dias?")
            if st.button("Gerar micro-plano (próximas 7 tarefas)"):
                fut = df_valid[(df_valid['Aluno(a)'] == user) | (df_valid['Aluno(a)'] == 'Ambos')].sort_values('Data').head(7)
                for _, r in fut.iterrows():
                    period = "Manhã"
                    for p in ["Manhã","Tarde","Noite"]:
                        if r.get(f"Matéria ({p})"):
                            period = p; break
                    if ia_enabled:
                        ok, out, used = call_groq_api(build_activity_prompt(r,period))
                        if ok:
                            st.info(out); st.caption(f"Modelo: {used}")
                        else:
                            s,c = fallback_summary_and_cards(r, period)
                            st.info(s)
                    else:
                        s,c = fallback_summary_and_cards(r, period)
                        st.info(s)
            st.markdown("</div>", unsafe_allow_html=True)
            return

        for _, row in df_user_today.iterrows():
            idx = int(row['index'])
            title = row.get("Matéria (Manhã)") or row.get("Matéria (Tarde)") or row.get("Matéria (Noite)") or "Atividade"
            date_str = row['Data'].strftime('%d/%m/%Y') if not pd.isna(row['Data']) else "Sem data"
            st.markdown(f"<div class='task'><div class='task-header'><div><div class='task-title'>{title}</div><div class='muted'>{date_str} • Prioridade: {row.get('Prioridade') or 'Média'}</div></div></div>", unsafe_allow_html=True)
            # summary (always show)
            coach = st.session_state['coach_messages'].get(str(idx))
            if coach:
                # greeting + short summary always visible
                greeting_short = f"{greeting}! Aqui vai um plano curto:"
                st.markdown(f"**{greeting_short}**")
                st.write(coach['summary'])
                if coach.get("model"):
                    st.caption(f"Modelo IA: {coach.get('model')}")
                # expander for flashcards and actions
                with st.expander("Flashcards & Ações (expanda)"):
                    st.markdown("**Flashcards**")
                    display_flashcards(coach['cards'], prefix=f"task{idx}")
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if st.button("✅ Marcar Concluído", key=f"done_{idx}"):
                            ok = mark_done(worksheet, row, headers)
                            if ok:
                                st.success("Marcado concluído.")
                                # refresh coach cache next run
                                st.session_state['_coach_generated_for_date'] = None
                                safe_rerun()
                            else:
                                st.warning("Falha ao marcar concluído (verifique permissões).")
                    with c2:
                        if st.button("📤 Reagendar Inteligente", key=f"resch_{idx}"):
                            rpt = {"info":"Executado via servidor. Veja logs."}
                            st.write(rpt)
                    with c3:
                        if st.button("📥 Exportar Anki (CSV)", key=f"anki_{idx}"):
                            # prepare CSV
                            dfc = pd.DataFrame(coach['cards'], columns=["Front","Back"])
                            csv = dfc.to_csv(index=False).encode('utf-8')
                            st.download_button("Baixar CSV", data=csv, file_name=f"anki_task_{idx}.csv", mime="text/csv")
            else:
                # no coach (shouldn't happen) - fallback
                s, cards = fallback_summary_and_cards(row, "Manhã")
                st.write(s)
                with st.expander("Flashcards"):
                    display_flashcards(cards, prefix=f"fallback_{idx}")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # Right column: micro-chat, quick stats, controls
    with right_col:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("### Micro-Chat (pergunte sobre hoje)")
        # build context: concatenate coach summaries
        context_parts = []
        for _, r in df_user_today.iterrows():
            idx = int(r['index'])
            coach = st.session_state['coach_messages'].get(str(idx))
            if coach:
                context_parts.append(coach['summary'])
        context_text = "\n\n".join(context_parts) if context_parts else "Sem contexto (nenhuma tarefa detectada)."

        # Show quick greeting from Coach IA
        st.markdown(f"**{greeting}, {user}!**")
        st.write("O Coach já preparou um resumo das tarefas de hoje. Pergunte algo (ex.: 'O que devo priorizar?', 'Quanto tempo devo estudar hoje?').")
        q = st.text_input("Perguntar ao Coach", key="microchat_input")
        if st.button("Perguntar"):
            if not q.strip():
                st.info("Escreva uma pergunta.")
            else:
                ok, ans = microchat_answer(context_text, q.strip())
                if ok:
                    st.success("Resposta da IA:")
                    st.write(ans)
                else:
                    st.warning("IA indisponível — resposta gerada localmente:")
                    st.write(ans)

        st.markdown("---")
        st.markdown("### Estatísticas rápidas")
        # simple metrics
        avg_pct = 0.0
        cnt = 0
        for p in ["Manhã","Tarde","Noite"]:
            col = f"% Concluído ({p})"
            if col in df_user_today.columns:
                try:
                    avg_pct += float(df_user_today[col].astype(float).mean())
                    cnt += 1
                except Exception:
                    pass
        avg_pct = (avg_pct / cnt) if cnt else 0.0
        st.markdown(f"<div class='metric'><div style='font-size:12px' class='muted'>Conclusão média hoje</div><div style='font-weight:700'>{int(avg_pct*100)}%</div></div>", unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>")

        # quick controls
        if st.button("Marcar todas como concluídas"):
            done_cnt = 0
            for _, row in df_user_today.iterrows():
                ok = mark_done(worksheet, row, headers)
                if ok:
                    done_cnt += 1
            st.success(f"{done_cnt} tarefas marcadas.")
            st.session_state['_coach_generated_for_date'] = None
            safe_rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # end main

if __name__ == "__main__":
    main()
