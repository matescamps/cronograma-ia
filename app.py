import streamlit as st
import pandas as pd
import datetime
import requests

st.set_page_config(page_title="Cronograma Interativo", layout="wide")

st.title("📚 Cronograma de Estudos com IA")

sheet_url = st.text_input("URL da Planilha do Google Sheets")
api_url = st.text_input("URL da API de Otimização (se tiver)")

if sheet_url:
    try:
        df = pd.read_csv(sheet_url)
        st.success("✅ Dados carregados da planilha!")
        st.dataframe(df)
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {e}")

if st.button("📈 Otimizar Cronograma"):
    if api_url:
        try:
            response = requests.post(api_url, json={"data": df.to_dict()})
            st.success("✅ Cronograma otimizado!")
            st.write(response.json())
        except Exception as e:
            st.error(f"Erro na otimização: {e}")
    else:
        st.warning("Informe a URL da API antes de otimizar.")
