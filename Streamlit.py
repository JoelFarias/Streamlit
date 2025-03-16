import plotly.express as px
import unicodedata
from fuzzywuzzy import process
import os
import psycopg2 as pg
import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu
from st_aggrid import AgGrid, GridOptionsBuilder

st.set_page_config(
    page_title="Análise Populacional",
    page_icon="🌎",
    layout="wide",
    initial_sidebar_state="expanded"
)

CORES = {
    'fundo': '#F8FBFE',
    'destaque': '#2A5C8A',
    'secundaria': '#5DA8A3',
    'texto': '#2C3E50',
    'positivo': '#27AE60',
    'negativo': '#C0392B'
}

def css():
    st.markdown(f"""
    <style>
        [data-testid="stAppViewContainer"] {{
            background: {CORES['fundo']};
        }}
        [data-testid="stSidebar"] {{
            background: #FFFFFF !important;
            border-right: 1px solid {CORES['secundaria']}20;
        }}
        h1, h2, h3 {{
            color: {CORES['destaque']} !important;
        }}
        .stSelectbox [data-baseweb="select"] {{
            border-radius: 8px !important;
            border: 1px solid {CORES['secundaria']} !important;
        }}
        .st-bb {{ /* Blocos Streamlit */
            background: #FFFFFF;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 8px {CORES['secundaria']}10;
        }}
        .stMetric {{
            color: {CORES['destaque']} !important;
        }}
        [data-testid="stMetricValue"] {{
            font-size: 1.4rem !important;
        }}
    </style>
    """, unsafe_allow_html=True)


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
        SELECT p.ano_pesquisa, 
               p.numero_habitantes,
               m.codigo_municipio_dv AS codigo,
               m.nome_municipio,
               u.sigla_uf AS uf,
               r.nome_regiao,
               m.latitude,
               m.longitude 
        FROM populacao p
        JOIN municipio m ON p.codigo_municipio_dv = m.codigo_municipio_dv
        JOIN unidade_federacao u ON m.cd_uf = u.cd_uf
        JOIN regiao r ON u.cd_regiao = r.cd_regiao
        """
        df = pd.read_sql(query, conn)
        
        mapeamento_colunas = {
            'ano_pesquisa': 'Ano',
            'numero_habitantes': 'População',
            'codigo': 'Código',
            'nome_municipio': 'Município',
            'uf': 'UF',
            'nome_regiao': 'Região',
            'latitude': 'Latitude',
            'longitude': 'Longitude'
        }
        
        df.rename(columns=mapeamento_colunas, inplace=True)
        df['Ano'] = df['Ano'].astype(str)
        df['População'] = pd.to_numeric(df['População'], errors='coerce')
        return df.dropna(subset=['População'])
        
    except (pg.Error, Exception) as e:
        st.error(f"Erro ao carregar dados: {e}")
        return None

def filter_data(df: pd.DataFrame, ano: str, uf: str, regiao: str) -> pd.DataFrame:
    filtered = df.copy()
    if ano != "Todos":
        filtered = filtered[filtered['Ano'] == ano]
    if uf != "Todos":
        filtered = filtered[filtered['UF'] == uf]
    if regiao != "Todas":
        filtered = filtered[filtered['Região'] == regiao]
    return filtered

def get_dataframe() -> pd.DataFrame | None:
    return st.session_state.get('df', None)

def sugerir_municipios(municipio_digitado: str, df: pd.DataFrame, limite: int = 5) -> list[str]:
    municipios = df['Município'].unique()
    municipios_normalizados = [remover_acentos_e_lower(m) for m in municipios]
    municipio_digitado_normalizado = remover_acentos_e_lower(municipio_digitado)
    sugestoes = process.extract(municipio_digitado_normalizado, municipios_normalizados, limit=limite)
    return [municipios[municipios_normalizados.index(m)] for m, _ in sugestoes]

def display_graphs(df: pd.DataFrame, x_col: str, y_col: str, grafico: str):
    if df.empty:
        st.warning("Nenhum dado disponível para os filtros selecionados")
        return

    try:
        top_municipios = df.nlargest(10, 'População')['Município'].unique()
        df_filtered = df[df['Município'].isin(top_municipios)]

        if grafico == 'Barra':
            fig = px.bar(
                df_filtered,
                x='Município',
                y='População',
                color='UF',
                template='plotly_white',
                color_discrete_sequence=px.colors.sequential.Blues,
                labels={'População': 'Habitantes'},
                title="Top 10 Municípios Mais Populosos"
            )
        elif grafico == 'Linha':
            df_agg = df_filtered.groupby([x_col, 'Município'])['População'].sum().reset_index()
            fig = px.line(
                df_agg,
                x=x_col,
                y=y_col,
                color='Município',
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Pastel,
                title="Evolução Populacional dos 10 Maiores Municípios"
            )
            
        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis_title='',
            yaxis_title='População',
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(
                title='Município',
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Erro ao gerar visualização: {str(e)}")
        
def display_map(df: pd.DataFrame):
    if not df.empty and 'Latitude' in df.columns and 'Longitude' in df.columns:
        df = df.dropna(subset=['Latitude', 'Longitude'])
        
        fig = px.scatter_mapbox(
            df,
            lat="Latitude",
            lon="Longitude",
            size="População",
            color="UF",
            hover_name="Município",
            hover_data={
                'População': ':,',
                'UF': True,
                'Região': True,
                'Latitude': False,
                'Longitude': False
            },
            zoom=3,
            color_discrete_sequence=px.colors.qualitative.Pastel,
            mapbox_style="carto-positron",
            height=600
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=30, b=0),
            legend=dict(
                title='Estados',
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Dados geográficos insuficientes para exibir o mapa")
        
def carregar_dados():
    with st.spinner('Carregando dados...'):
        df = load_data()
        if df is not None:
            st.session_state.df = df
            st.success("Dados carregados com sucesso!")
            st.dataframe(df.head(3))

def exibir_visualizacao():
    df = get_dataframe()
    if df is None:
        st.warning("Carregue os dados primeiro")
        return

    with st.sidebar:
        st.header("⚙️ Filtros de Visualização")
        num_municipios = st.slider(
            "Número de Municípios nos Gráficos",
            min_value=5,
            max_value=50,
            value=10,
            help="Selecione quantos municípios mostrar nos gráficos de barra e linha"
        )

        ano = st.selectbox(
            "Ano de Referência",
            options=sorted(df['Ano'].unique(), reverse=True),
            key="vis_ano"
        )
        tipo_grafico = st.selectbox(
            "Tipo de Visualização",
            options=["Mapa", "Gráfico de Barras", "Gráfico de Linhas", "Hierarquia"],
            format_func=lambda x: f"📊 {x}",
            key="tipo_grafico"
        )

    filtered_df = df[df['Ano'] == ano]
    if tipo_grafico == "Mapa":
        display_map(filtered_df)
        
    elif tipo_grafico == "Gráfico de Barras":
        display_graphs(filtered_df, 'Município', 'População', 'Barra', num_municipios)
        
    elif tipo_grafico == "Gráfico de Linhas":
        display_graphs(filtered_df, 'Ano', 'População', 'Linha', num_municipios)
        
    elif tipo_grafico == "Hierarquia":
        fig = px.treemap(
            filtered_df,
            path=['Região', 'UF', 'Município'],
            values='População',
            color='População',
            color_continuous_scale='Blues',
            title=f"Distribuição Hierárquica - {ano}"
        )
        fig.update_layout(margin=dict(t=40, l=20, r=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
            
def remover_acentos_e_lower(texto: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    ).lower()


def exibir_visualizacao():
    df = get_dataframe()
    if df is None:
        st.warning("Carregue os dados primeiro")
        return

    with st.sidebar:
        st.header("⚙️ Filtros de Visualização")
        num_municipios = st.slider(
            "Número de Municípios a Mostrar",
            min_value=5,
            max_value=50,
            value=10,
            help="Selecione quantos municípios deseja visualizar"
        )
        ano = st.selectbox(
            "Ano de Referência",
            options=sorted(df['Ano'].unique(), reverse=True),
            key="vis_ano"
        )
        estado = st.selectbox(
            "Estado", 
            options=["Todos"] + sorted(df['UF'].unique()),
            key="vis_estado"
        )
        regiao = st.selectbox(
            "Região", 
            options=["Todas"] + sorted(df['Região'].unique()),
            key="vis_regiao"
        )
        
        municipio_input = st.text_input("Buscar Município:")
        sugestoes = []
        if municipio_input:
            sugestoes = sugerir_municipios(municipio_input, df)
            if sugestoes:
                st.markdown(f"<small>Sugestões: {', '.join(sugestoes[:3])}</small>", unsafe_allow_html=True)

        tipo_grafico = st.selectbox(
            "Tipo de Visualização",
            options=["Mapa", "Gráfico de Barras", "Gráfico de Linhas", "Hierarquia"],
            format_func=lambda x: f"📊 {x}",
            key="tipo_grafico"
        )

    filtered_df = df[df['Ano'] == ano]
    
    if estado != "Todos":
        filtered_df = filtered_df[filtered_df['UF'] == estado]
        
    if regiao != "Todas":
        filtered_df = filtered_df[filtered_df['Região'] == regiao]
        
    if municipio_input and sugestoes:
        filtered_df = filtered_df[filtered_df['Município'].isin(sugestoes)]
        
    st.header("🌍 Visualização Interativa")
    
    if tipo_grafico == "Mapa":
        display_map(filtered_df)
        
    elif tipo_grafico == "Gráfico de Barras":
        col1, col2 = st.columns(2)
        with col1:
            x_axis = st.selectbox("Eixo X", options=['UF', 'Região', 'Município'])
        with col2:
            y_axis = st.selectbox("Eixo Y", options=['População'])
            
        display_graphs(filtered_df, x_axis, y_axis, 'Barra')
        
    elif tipo_grafico == "Gráfico de Linhas":
        display_graphs(filtered_df, 'Ano', 'População', 'Linha')
        
    elif tipo_grafico == "Hierarquia":
        fig = px.treemap(
            filtered_df,
            path=['Região', 'UF', 'Município'],
            values='População',
            color='População',
            color_continuous_scale='Blues',
            title=f"Distribuição Hierárquica - {ano}"
        )
        fig.update_layout(margin=dict(t=40, l=20, r=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
        
def css():
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] {
        background: #f0f2f6;
    }
    .ag-theme-streamlit {
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .ag-header-cell-label {
        font-weight: 600 !important;
        color: #2c3e50 !important;
    }
    .ag-cell {
        font-family: 'Segoe UI', sans-serif;
    }
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e0e0e0;
    }
    .stSelectbox [data-baseweb="select"] {
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    css()
    st.title("🌍 Análise Populacional Brasileira")
    
    menu = option_menu(
        menu_title=None,
        options=["Carregar Dados", "Estatísticas", "Visualização"],
        icons=["cloud-upload", "bar-chart", "map"],
        orientation="horizontal",
        styles={
            "container": {"padding": "10px", "background-color": "#f8f9fa"},
            "nav-link": {"font-size": "14px", "margin": "0 10px"}
        }
    )

    if menu == "Carregar Dados":
        carregar_dados()
    elif menu == "Estatísticas":
        exibir_estatisticas()
    elif menu == "Visualização":
        exibir_visualizacao()

if __name__ == "__main__":
    main()
