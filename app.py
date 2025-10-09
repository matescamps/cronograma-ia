# -*- coding: utf-8 -*-
"""
Cronograma Ana&Mateus — Versão sem matplotlib, resiliente à depreciação de modelos Groq
- Usa gráficos nativos do Streamlit (st.bar_chart / st.line_chart)
- Corrige FutureWarning ao normalizar % Concluído
- Fallback automático de modelo Groq se 'model_decommissioned' for detectado
- Fallback local (resumo + quiz) se IA indisponível
- ID por linha, Hora Conclusão, smart rescheduler, export Anki, Pomodoro (cliente-side)
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
st.title("Cronograma Ana&Mateus — IA & Criatividade")

# ----------------------------
# Utils: limpar strings numéricas problemáticas
# ----------------------------
def clean_number_like_series(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str)
    s = s.str.replace(r'[\[\]\'"]', '', regex=True)   # remove colchetes/aspas
    s = s.str.strip()
    # remover pontos de milhar quando houver formato BR (p.ex. '1.234,56')
    has_thousand = s.str.contains(r'\.\d{3}', regex=True)
    if has_thousand.any():
        s = s.where(~has_thousand, s.str.replace('.','', regex=False))
    s = s.str.replace(',', '.', regex=False)
    s = s.str.replace(r'[^\d\.\-]', '', regex=True)
    return pd.to_numeric(s, errors='coerce').fillna(0.0)

# ----------------------------
# Conexão Google Sheets
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
        st.error(f"Erro ao conectar ao Google Sheets: {str(e)[:300]}")
        return None

# ----------------------------
# Carregar e normalizar dados (evita FutureWarning)
# ----------------------------
@st.cache_data(ttl=60, show_spinner=False)
def load_data(client, spreadsheet_id: str, sheet_tab_name: str) -> Tuple[pd.DataFrame, Optional[Any], List[str]]:
    try:
        if not client:
            return pd.DataFrame(), None, []
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

        # garantir colunas esperadas
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

        # Conversões
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
        df['Dificuldade (1-5)'] = pd.to_numeric(df['Dificuldade (1-5)'], errors='coerce').fillna(0).astype(int)

        # Questões -> int
        for col in df.columns:
            if 'Questões' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

        # Teoria Feita -> bool
        for col in df.columns:
            if 'Teoria Feita' in col:
                df[col] = df[col].astype(str).str.upper().isin(['TRUE','VERDADEIRO','1','SIM'])

        # % Concluído -> float 0..1 robusto
        for col in df.columns:
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
        st.error(f"Erro ao carregar dados: {str(e)[:300]}")
        return pd.DataFrame(), None, []

# ----------------------------
# Groq API wrapper com fallback automático de modelo
# ----------------------------
def call_groq_api_with_model(prompt: str, model: str, max_retries: int = 2) -> Tuple[bool, str, Optional[str]]:
    groq_key = st.secrets.get('GROQ_API_KEY', None)
    if not groq_key:
        return False, "⚠️ GROQ_API_KEY ausente em st.secrets.", None

    groq_url = st.secrets.get('GROQ_API_URL', "").strip()
    if groq_url:
        endpoint = groq_url
        if endpoint.endswith('/v1') or endpoint.endswith('/v1/'):
            endpoint = endpoint.rstrip('/') + "/chat/completions"
    else:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"

    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role":"user","content":prompt}], "temperature":0.6, "max_tokens":700}

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
                return False, "⚠️ API Key inválida (401).", model
            # tentar entender erro (model_decommissioned etc)
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
            return False, "⚠️ Timeout na conexão com a IA.", model
        except Exception as e:
            return False, f"⚠️ Erro: {str(e)[:250]}", model
    return False, "⚠️ Não foi possível conectar com a IA.", model

def call_groq_api(prompt: str) -> Tuple[bool, str, str]:
    configured_model = st.secrets.get('GROQ_MODEL', "").strip()
    if not configured_model:
        configured_model = "gemma2-9b-it"  # legacy default; will be caught if decommissioned
    fallback_model = st.secrets.get('GROQ_FALLBACK_MODEL', "llama-3.1-8b-instant")

    ok, text, used = call_groq_api_with_model(prompt, configured_model)
    if ok:
        return True, text, used
    # se erro por model_decommissioned, tenta fallback
    if isinstance(text, str) and ('model_decommissioned' in text or 'deprecat' in text.lower() or 'decommission' in text.lower()):
        ok2, text2, used2 = call_groq_api_with_model(prompt, fallback_model)
        if ok2:
            notice = f"(Modelo {configured_model} descontinuado; usado fallback {fallback_model})\n\n"
            return True, notice + text2, used2
        else:
            return False, f"Falha ao usar fallback {fallback_model}: {text2}", used2 or fallback_model
    return False, text, used

# ----------------------------
# Fallback local (gerador simples de resumo e quiz)
# ----------------------------
def fallback_summary(row, period_label: str) -> str:
    subj = row.get(f"Matéria ({period_label})", "") or "a matéria"
    act = row.get(f"Atividade Detalhada ({period_label})", "") or ""
    diff = int(row.get("Dificuldade (1-5)", 0) or 0)
    para = f"Resumo prático: foque em {subj}. {'Comece revisando conceitos básicos.' if diff<=2 else 'Priorize resolução de questões e revisão ativa.'}"
    if act:
        para += f" Atividade: {act}."
    plan = "Plano: 1) Leitura rápida (10-20 min). 2) Resolver questões (20-40 min). 3) Revisar erros e criar 3 flashcards."
    return f"{para}\n\n{plan}"

def fallback_quiz(row, period_label: str, n:int=3):
    subj = row.get(f"Matéria ({period_label})", "Matéria")
    desc = row.get(f"Atividade Detalhada ({period_label})", "")
    text = f"Mini-quiz (fallback) sobre {subj} — foco: {desc}\n\n"
    cards = []
    for i in range(n):
        if i == 0:
            q = f"O que é o conceito principal de '{subj}'?"
            a = "Resposta: definição/resumo do conceito."
        elif i == 1:
            q = f"Exemplo prático ou problema simples relacionado a '{desc or subj}'."
            a = "Resposta: solução explicada."
        else:
            q = f"V/F: Afirmação comum sobre '{subj}' (justifique)."
            a = "Resposta: Verdadeiro/Falso + justificativa."
        text += f"{i+1}. {q}\n"
        cards.append((q, a))
    return text, cards

# ----------------------------
# Planilha helpers (ID, encontrar linha, atualizar)
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
        st.warning(f"Erro ao garantir ID: {str(e)[:120]}")
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
        st.warning(f"Erro find_row_index: {str(e)[:120]}")
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
        # Hora Conclusão
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
        st.error(f"Erro ao marcar concluído: {str(e)[:200]}")
        return False

# ----------------------------
# Analytics (usando Streamlit charts)
# ----------------------------
def show_analytics(df: pd.DataFrame):
    st.subheader("Analytics Rápidos")
    if df.empty:
        st.info("Sem dados para analytics.")
        return
    # média de conclusão por aluno
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
    df_local = df.copy()
    df_local['avg_pct'] = df_local.apply(avg_completion, axis=1)
    agg = df_local.groupby('Aluno(a)')['avg_pct'].mean().fillna(0.0)
    if not agg.empty:
        st.write("Conclusão média por aluno")
        st.bar_chart(agg)

    # média por período
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
    st.write("Média % Concluído por período")
    st.bar_chart(pd.Series(period_avgs))

def calendar_progress_chart(df: pd.DataFrame, aluno: str):
    df_a = df[(df['Aluno(a)'] == aluno) | (df['Aluno(a)']=='Ambos')].copy()
    if df_a.empty:
        st.info("Sem dados para calendar progress.")
        return
    df_a['date'] = df_a['Data'].dt.date
    # média por dia
    def day_mean(g):
        vals = []
        for p in ["Manhã","Tarde","Noite"]:
            col = f"% Concluído ({p})"
            if col in g.columns:
                try:
                    vals.append(g[col].astype(float).mean())
                except Exception:
                    vals.append(0.0)
        return np.mean(vals) if vals else 0.0
    agg = df_a.groupby('date').apply(day_mean).rename("mean_completion")
    if not agg.empty:
        st.write("Progresso diário médio")
        st.line_chart(agg)

# ----------------------------
# Pomodoro widget (cliente-side)
# ----------------------------
def pomodoro_widget():
    st.write("### ⏱️ Focus Mode — Pomodoro (local)")
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
# Quiz -> Anki export
# ----------------------------
def anki_csv_download(cards: List[tuple], filename: str):
    dfc = pd.DataFrame(cards, columns=["Front","Back"])
    csv = dfc.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Baixar CSV Anki", data=csv, file_name=filename, mime="text/csv")

# ----------------------------
# UI principal
# ----------------------------
def show_login():
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👨‍🎓 Entrar como Mateus"):
            st.session_state.logged_user = "Mateus"
            st.experimental_rerun()
    with col2:
        if st.button("👩‍🎓 Entrar como Ana"):
            st.session_state.logged_user = "Ana"
            st.experimental_rerun()

def main():
    if 'logged_user' not in st.session_state:
        st.session_state.logged_user = None
    st.sidebar.title("Cronograma Ana&Mateus")
    st.sidebar.write("Compartilhe a planilha com o client_email do service account como Editor.")
    client = connect_to_google_sheets()
    if not client:
        st.stop()
    spreadsheet_id = st.secrets.get("SPREADSHEET_ID_OR_URL", "")
    sheet_tab_name = st.secrets.get("SHEET_TAB_NAME", "Cronograma")
    df, worksheet, headers = load_data(client, spreadsheet_id, sheet_tab_name)
    if df.empty:
        st.warning("Planilha vazia ou sem dados válidos.")
        return
    headers = ensure_id_column(worksheet, headers)

    user = st.session_state.get('logged_user', None)
    if not user:
        show_login()
        return

    st.header(f"Cronograma — {user}")

    ia_enabled = st.sidebar.checkbox("Ativar IA (Groq)", value=True if st.secrets.get('GROQ_API_KEY') else False)
    threshold = st.sidebar.slider("Threshold para re-agendamento (%)", 0, 100, 50) / 100.0
    st.sidebar.markdown("---")
    st.sidebar.write("Se a IA estiver indisponível o app gera fallback local (resumo + quiz).")

    today = (datetime.now(timezone.utc) - timedelta(hours=3)).date()
    df_valid = df[df['Data'].notna()]
    df_today = df_valid[df_valid['Data'].dt.date == today]
    df_user_today = df_today[(df_today['Aluno(a)'] == user) | (df_today['Aluno(a)'] == 'Ambos')]

    # Quick XP & streak (simplificado)
    xp, streak = compute_xp(df, user)
    colx1, colx2 = st.columns(2)
    colx1.metric("XP acumulado", xp)
    colx2.metric("Streak (dias)", streak)

    if df_user_today.empty:
        st.info("Nenhuma tarefa para hoje — você pode gerar um micro-plano IA ou revisar próximos dias.")
        if st.button("🔮 Gerar micro-plano IA para próximas 7 tarefas"):
            future = df_valid[(df_valid['Aluno(a)']==user) | (df_valid['Aluno(a)']=='Ambos')].sort_values('Data').head(7)
            outputs = []
            for _, r in future.iterrows():
                if ia_enabled:
                    ok, out, used = call_groq_api(build_activity_prompt(r, "Manhã"))
                    if ok:
                        outputs.append(f"{r['Data'].strftime('%d/%m/%Y')}: {out}")
                    else:
                        outputs.append(f"{r['Data'].strftime('%d/%m/%Y')}: (IA indisponível) {fallback_summary(r,'Manhã')}")
                else:
                    outputs.append(f"{r['Data'].strftime('%d/%m/%Y')}: {fallback_summary(r,'Manhã')}")
            st.write("\n\n".join(outputs))
        calendar_progress_chart(df, user)
        return

    # Mostrar tarefas de hoje com ações
    for idx, row in df_user_today.iterrows():
        st.markdown("---")
        title = row.get("Matéria (Manhã)") or row.get("Matéria (Tarde)") or row.get("Matéria (Noite)") or "Atividade"
        st.subheader(f"{title} — {row['Data'].strftime('%d/%m/%Y') if not pd.isna(row['Data']) else 'Sem data'}")
        c1, c2, c3 = st.columns([4,2,2])

        with c1:
            st.write("Manhã:", row.get("Atividade Detalhada (Manhã)") or "—")
            st.write("Tarde:", row.get("Atividade Detalhada (Tarde)") or "—")
            st.write("Noite:", row.get("Atividade Detalhada (Noite)") or "—")
            st.write("Sugestão de revisão:", ", ".join(recommend_spaced_repetition(row)))
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
            period = st.selectbox("Período", ["Manhã","Tarde","Noite"], key=f"period_{idx}")
            if st.button("💡 Coach IA (Resumo)", key=f"coach_{idx}"):
                if ia_enabled:
                    ok, out, used_model = call_groq_api(build_activity_prompt(row, period))
                    if ok:
                        st.info(out)
                        st.caption(f"Modelo usado: {used_model}")
                    else:
                        st.warning("Coach IA indisponível: " + out)
                        st.info(fallback_summary(row, period))
                else:
                    st.info(fallback_summary(row, period))
            if st.button("❓ Gerar Quiz + Anki", key=f"quiz_{idx}"):
                if ia_enabled:
                    ok, out, used_model = call_groq_api(generate_quiz_prompt(row, period, 4))
                    if ok:
                        st.code(out)
                        st.caption(f"Modelo usado: {used_model}")
                        # heurística: não parseamos, oferecemos download do texto bruto como txt
                        b = out.encode('utf-8')
                        st.download_button("📥 Baixar Quiz (txt)", data=b, file_name=f"quiz_{user}_{row['Data'].strftime('%Y%m%d')}.txt", mime="text/plain")
                    else:
                        st.warning("IA indisponível — gerando fallback local.")
                        txt, cards = fallback_quiz(row, period, 3)
                        st.code(txt)
                        anki_csv_download(cards, f"anki_{user}_{row['Data'].strftime('%Y%m%d')}.csv")
                else:
                    txt, cards = fallback_quiz(row, period, 3)
                    st.code(txt)
                    anki_csv_download(cards, f"anki_{user}_{row['Data'].strftime('%Y%m%d')}.csv")
            if st.button("✅ Marcar Concluído (100%)", key=f"done_{idx}"):
                ok = mark_done(worksheet, row, headers)
                if ok:
                    st.success("Marcado concluído e Hora Conclusão registrada.")
                    load_data.clear()
                    st.experimental_rerun()
                else:
                    st.warning("Não foi possível marcar concluído (verifique permissões).")
            if st.button("📤 Reagendar Inteligente", key=f"resch_{idx}"):
                rpt = smart_reschedule(df, worksheet, headers, user, threshold)
                st.write(rpt)

    st.markdown("---")
    pomodoro_widget()
    st.markdown("---")
    show_analytics(df)
    calendar_progress_chart(df, user)

    st.markdown("---")
    if st.button("📥 Exportar CSV completo"):
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", data=csv, file_name=f"cronograma_all_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

# ----------------------------
# Funções auxiliares (XP/streak, spaced repetition, rescheduler)
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
    # find last day <= today
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

def recommend_spaced_repetition(df_row):
    d = int(df_row.get("Dificuldade (1-5)", 0) or 0)
    if d >= 4:
        return ["24h","72h","7d"]
    if d == 3:
        return ["48h","7d"]
    return ["72h","10d"]

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
    return (f"Você é um coach de estudos experiente. Resuma em 1 parágrafo e entregue 3 passos práticos."
            f" Matéria: {subj}. Atividade: {act}. Dificuldade: {diff}. Responda em português.")

def generate_quiz_prompt(row, period_label, n=4):
    subj = row.get(f"Matéria ({period_label})", "")
    desc = row.get(f"Atividade Detalhada ({period_label})", "")
    return (f"Crie um mini-quiz de {n} questões sobre '{subj}' com foco em {desc}. "
            "Forneça enunciado, 4 alternativas A-D e, no final, 'Gabarito: A,B,...'. Responda em português.")

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    main()
