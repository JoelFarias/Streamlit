import plotly.express as px
import unicodedata
from fuzzywuzzy import process
import os
import psycopg2 as pg
import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu
from st_aggrid import AgGrid, GridOptionsBuilder

@st.cache_data(ttl=600)
def load_data() -> pd.DataFrame | None:
    try:
        conn = pg.connect(
            host=st.secrets["DB_HOST"],
            database=st.secrets["DB_NAME"],
            user=st.secrets["DB_USERNAME"],
            password=st.secrets["DB_PASSWORD"]
        )
        query = """
        SELECT p.ano_pesquisa, p.numero_habitantes, p.faixa_populacao, 
               m.nome_municipio, u.nome_uf, r.nome_regiao, 
               m.latitude, m.longitude 
        FROM populacao p
        JOIN municipio m ON p.codigo_municipio_dv = m.codigo_municipio_dv
        JOIN unidade_federacao u ON m.cd_uf = u.cd_uf
        JOIN regiao r ON u.cd_regiao = r.cd_regiao
        """
        df = pd.read_sql(query, conn)
        mapeamento_colunas = {
            'ano_pesquisa': 'Ano', 'numero_habitantes': 'População',
            'faixa_populacao': 'Faixa de População', 'nome_municipio': 'Município',
            'nome_uf': 'Estados', 'nome_regiao': 'Regiões',
            'latitude': 'Latitude', 'longitude': 'Longitude'
        }
        df.rename(columns=mapeamento_colunas, inplace=True)
        df['Ano'] = df['Ano'].astype(str)
        df['População'] = pd.to_numeric(df['População'], errors='coerce')
        return df
    except (pg.Error, Exception) as e:
        st.error(f"Erro ao carregar dados: {e}")
        return None

def filter_data(df: pd.DataFrame, ano: str, estado: str, regiao: str) -> pd.DataFrame:
    return df[
        (df['Ano'] == ano) &
        ((df['Estados'] == estado) if estado != "Todos" else True) &
        ((df['Regiões'] == regiao) if regiao != "Todas" else True)
    ]

def get_dataframe() -> pd.DataFrame | None:
    return st.session_state.get('df', None)

def remover_acentos_e_lower(texto: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    ).lower()

def sugerir_municipios(municipio_digitado: str, df: pd.DataFrame, limite: int = 5) -> list[str]:
    municipios = df['Município'].unique()
    municipios_normalizados = [remover_acentos_e_lower(m) for m in municipios]

    municipio_digitado_normalizado = remover_acentos_e_lower(municipio_digitado)
    sugestoes = process.extract(municipio_digitado_normalizado, municipios_normalizados, limit=limite)

    return [municipios[municipios_normalizados.index(m)] for m, _ in sugestoes]

def exibir_visualizacao(df: pd.DataFrame, x_col: str, y_col: str, grafico: str):
    if df.empty:
        st.warning("Nenhum dado disponível para os filtros selecionados.")
        return

    if not pd.api.types.is_numeric_dtype(df[y_col]):
        st.error(f"Erro: A coluna '{y_col}' precisa ser numérica para este gráfico.")
        return

    try:
        if grafico == 'Barra':
            fig = px.bar(df, x=x_col, y=y_col, color='Estados', barmode='group', title=f'{y_col} por {x_col}')
        elif grafico == 'Pizza':
            fig = px.pie(df, names=x_col, values=y_col, title=f'Distribuição de {y_col} por {x_col}')
        elif grafico == 'Linha':
            fig = px.line(df, x=x_col, y=y_col, color='Estados', title=f'{y_col} ao longo de {x_col}')
        st.plotly_chart(fig)
    except ValueError as e:
        st.error(f"Erro ao exibir o gráfico: {e}")

def display_map(df: pd.DataFrame):
    if df.empty or 'Latitude' not in df.columns or 'Longitude' not in df.columns:
        st.write("Dados de latitude e longitude não disponíveis.")
        return

    mapa_fig = px.scatter_mapbox(
        df, lat="Latitude", lon="Longitude", size="População", color="Estados",
        hover_name="Município", title="Distribuição Populacional",
        mapbox_style="carto-positron", zoom=3
    )
    st.plotly_chart(mapa_fig)

def carregar_dados():
    with st.spinner('Carregando dados...'):
        df = load_data()  
        if df is not None:
            st.success("Dados carregados com sucesso!") 
            st.dataframe(df.head())
            st.session_state.df = df

def exibir_estatisticas():
    df = get_dataframe()
    if df is not None:
        ano_pesquisa = st.sidebar.selectbox("Ano da Pesquisa", sorted(df['Ano'].unique(), reverse=True))
        estado = st.sidebar.selectbox("Estado", ["Todos"] + sorted(df['Estados'].unique()))
        regiao = st.sidebar.selectbox("Região", ["Todas"] + sorted(df['Regiões'].unique()))

        filtered_df = filter_data(df, ano_pesquisa, estado, regiao)

        if not filtered_df.empty:
            stats = filtered_df['População'].describe().reset_index()
            stats.columns = ["Métrica", "População"]
            translate = {
                "count": "Quantidade de Municípios",
                "mean": "Média da População por Município",
                "std": "Desvio Padrão",
                "min": "Município com a menor População",
                "25%": "1º Quartil (25%)",
                "50%": "Mediana (50%)",
                "75%": "3º Quartil (75%)",
                "max": "Município com a maior População"
            }
            stats['Métrica'] = stats['Métrica'].map(translate)

            gb = GridOptionsBuilder.from_dataframe(stats)
            gb.configure_column("Métrica", header_name="Métrica", width=200)
            gb.configure_column("População", header_name="Valor", width=200)
            grid_options = gb.build()

            st.write("### Estatísticas Descritivas da População:")
            AgGrid(
                stats,
                gridOptions=grid_options,
                height=300,
                fit_columns_on_grid_load=True
            )
        else:
            st.warning("Nenhum dado encontrado para os filtros selecionados.")

def css():
    st.markdown(
        """
        <style>
        body { font-family: Arial, sans-serif; }
        @media (prefers-color-scheme: light) {
            body { background-color: #ffffff; color: #000000; }
            .sidebar .sidebar-content { background-color: #f0f0f0; }
        }
        @media (prefers-color-scheme: dark) {
            body { background-color: #1d1d1d; color: #ffffff; }
            .sidebar .sidebar-content { background-color: #2c2c2c; }
        }
        </style>
        """, 
        unsafe_allow_html=True
    )

def main():
    css() 
    st.markdown("<h1>Análise de Dados Populacionais</h1>", unsafe_allow_html=True)

    menu = option_menu(
        menu_title="Menu",
        options=["Carregar Dados", "Estatísticas", "Visualização"],
        icons=["cloud-upload", "bar-chart", "eye"],
        menu_icon="cast",
        default_index=0,
        orientation="vertical",
    )

    if menu == "Carregar Dados":
        carregar_dados()
    elif menu == "Estatísticas":
        exibir_estatisticas()
    elif menu == "Visualização":
        df = get_dataframe()
        if df is not None:
            display_map(df)
        else:
            st.warning("Por favor, carregue os dados primeiro.")
    
if __name__ == "__main__":
    main()
