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

def css():
    st.markdown("""
    <style>
        [data-testid="stAppViewContainer"] {
            background: #f8fafc;
        }
        [data-testid="stSidebar"] {
            background: #ffffff !important;
            border-right: 1px solid #e2e8f0;
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
        .stSelectbox [data-baseweb="select"] {
            border-radius: 8px;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 15px;
        }
        .stPlotlyChart {
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 10px;
        }
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

def filter_data(df: pd.DataFrame, ano: str, estado: str, regiao: str) -> pd.DataFrame:
    """Filtra os dados de acordo com ano, estado e região."""
    filtered = df.copy()
    if ano != "Todos":
        filtered = filtered[filtered['Ano'] == ano]
    if estado != "Todos":
        filtered = filtered[filtered['Estados'] == estado]
    if regiao != "Todas":
        filtered = filtered[filtered['Regiões'] == regiao]
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
        st.warning("Nenhum dado disponível para os filtros selecionados.")
        return

    try:
        if grafico == 'Barra':
            fig = px.bar(df, x=x_col, y=y_col, color='Estados', 
                        barmode='group', template='plotly_white')
        elif grafico == 'Pizza':
            fig = px.pie(df, names=x_col, values=y_col, 
                        color_discrete_sequence=px.colors.qualitative.Pastel)
        elif grafico == 'Linha':
            fig = px.line(df, x=x_col, y=y_col, color='Estados', 
                         markers=True, template='plotly_white')
        fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao gerar gráfico: {e}")

def display_map(df: pd.DataFrame):
    if not df.empty and 'Latitude' in df.columns and 'Longitude' in df.columns:
        fig = px.scatter_mapbox(
            df, lat="Latitude", lon="Longitude", size="População",
            color="Estados", hover_name="Município", zoom=3,
            mapbox_style="carto-positron", height=600
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Dados geográficos incompletos")

def carregar_dados():
    with st.spinner('Carregando dados...'):
        df = load_data()
        if df is not None:
            st.session_state.df = df
            st.success("Dados carregados com sucesso!")
            st.dataframe(df.head(3))

def exibir_estatisticas():
    df = get_dataframe()
    if df is None:
        st.warning("Carregue os dados primeiro")
        return

    with st.sidebar:
        st.header("Filtros")
        ano = st.selectbox("Ano", ["Todos"] + sorted(df['Ano'].unique(), reverse=True))
        estado = st.selectbox("Estado", ["Todos"] + sorted(df['Estados'].unique()))
        regiao = st.selectbox("Região", ["Todas"] + sorted(df['Regiões'].unique()))

    filtered_df = filter_data(df, ano, estado, regiao)

    if not filtered_df.empty:
        st.header("Estatísticas Populacionais")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Municípios", len(filtered_df))
        with col2:
            st.metric("População Total", f"{filtered_df['População'].sum():,.0f}")
        with col3:
            st.metric("Média Municipal", f"{filtered_df['População'].mean():,.0f}")

        min_row = filtered_df.loc[filtered_df['População'].idxmin()]
        max_row = filtered_df.loc[filtered_df['População'].idxmax()]

        stats_data = {
            "População Mínima": f"{min_row['Município']} ({min_row['UF']}) - {min_row['Código']}: {min_row['População']:,.0f} hab",
            "População Máxima": f"{max_row['Município']} ({max_row['UF']}) - {max_row['Código']}: {max_row['População']:,.0f} hab",
            "Desvio Padrão": f"{filtered_df['População'].std():,.0f}",
            "1º Quartil": f"{filtered_df['População'].quantile(0.25):,.0f}",
            "Mediana": f"{filtered_df['População'].median():,.0f}",
            "3º Quartil": f"{filtered_df['População'].quantile(0.75):,.0f}"
        }

        stats_df = pd.DataFrame({
            "Métrica": stats_data.keys(),
            "Valor": stats_data.values()
        })

        AgGrid(
            stats_df,
            height=250,
            fit_columns_on_grid_load=True,
            theme='streamlit',
            gridOptions={
                "columnDefs": [
                    {"headerName": "Métrica", "field": "Métrica", "width": 150},
                    {"headerName": "Valor", "field": "Valor", "width": 400}
                ]
            }
        )
    else:
        st.warning("Nenhum dado encontrado com os filtros selecionados")
            
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
        st.header("Configurações")
        ano = st.selectbox("Ano", sorted(df['Ano'].unique()), key="vis_ano")
        tipo_grafico = st.selectbox("Tipo de Visualização", ["Mapa", "Gráfico Hierárquico"])

    filtered_df = df[df['Ano'] == ano]

    if tipo_grafico == "Mapa":
        display_map(filtered_df)
    else:
        fig = px.treemap(filtered_df, path=['Regiões', 'Estados', 'Município'], 
                         values='População', color='População',
                         color_continuous_scale='Blues')
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
