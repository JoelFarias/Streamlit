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
    """Filtra os dados de acordo com ano, estado e região."""
    return df[
        (df['Ano'] == ano) &
        ((df['Estados'] == estado) if estado != "Todos" else True) &
        ((df['Regiões'] == regiao) if regiao != "Todas" else True)
    ]

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
        col1, col2, col3 = st.sidebar.columns([3, 2, 2])
        with col1:
            ano_pesquisa = st.selectbox("Ano da Pesquisa", sorted(df['Ano'].unique(), reverse=True))
        with col2:
            estado = st.selectbox("Estado", ["Todos"] + sorted(df['Estados'].unique()))
        with col3:
            regiao = st.selectbox("Região", ["Todas"] + sorted(df['Regiões'].unique()))

        filtered_df = filter_data(df, ano_pesquisa, estado, regiao)

        if not filtered_df.empty:
            min_pop = filtered_df.loc[filtered_df['População'].idxmin()]
            max_pop = filtered_df.loc[filtered_df['População'].idxmax()]
            
            stats_data = {
                "count": ("🏙️ Quantidade de Municípios", f"{len(filtered_df):,}"),
                "mean": ("📊 Média Populacional", f"{filtered_df['População'].mean():,.2f}"),
                "std": ("📈 Desvio Padrão", f"{filtered_df['População'].std():,.2f}"),
                "min": ("🔻 Menor População", f"{min_pop['Município']} ({min_pop['População']:,.0f} hab)"),
                "25%": ("📉 1º Quartil", f"{filtered_df['População'].quantile(0.25):,.0f}"),
                "50%": ("📐 Mediana", f"{filtered_df['População'].median():,.0f}"),
                "75%": ("📈 3º Quartil", f"{filtered_df['População'].quantile(0.75):,.0f}"),
                "max": ("🔺 Maior População", f"{max_pop['Município']} ({max_pop['População']:,.0f} hab)")
            }

            stats = pd.DataFrame({
                "Métrica": [v[0] for v in stats_data.values()],
                "Valor": [v[1] for v in stats_data.values()]
            })

            gb = GridOptionsBuilder.from_dataframe(stats)
            gb.configure_column("Métrica", headerName="Métrica", width=300, cellStyle={'font-weight': 'bold'})
            gb.configure_column("Valor", headerName="Valor", width=200, type=["rightAligned"])
            gb.configure_grid_options(domLayout='autoHeight', suppressRowHoverHighlight=True)
            grid_options = gb.build()

            st.markdown("### 📌 Estatísticas Descritivas")
            AgGrid(stats, 
                 gridOptions=grid_options,
                 height=350,
                 fit_columns_on_grid_load=True,
                 theme='streamlit')

        else:
            st.warning("⚠️ Nenhum dado encontrado para os filtros selecionados.")
            
def remover_acentos_e_lower(texto: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    ).lower()

def exibir_visualizacao():
    df = get_dataframe()
    if df is not None:
        ano_pesquisa = st.sidebar.selectbox(
            "Ano da Pesquisa", 
            sorted(df['Ano'].unique(), reverse=True), 
            key="ano_pesquisa"
        )
        estado = st.sidebar.selectbox(
            "Estado", 
            ["Todos"] + sorted(df['Estados'].unique()), 
            key="estado"
        )
        regiao = st.sidebar.selectbox(
            "Região", 
            ["Todas"] + sorted(df['Regiões'].unique()), 
            key="regiao"
        )
        filtered_df = filter_data(df, ano_pesquisa, estado, regiao)

        grafico_selecionado = st.sidebar.multiselect(
            "Escolha os gráficos para exibir:", 
            ["Barra", "Pizza", "Linha", "Mapa"], 
            key="grafico_selecionado"
        )

        colunas_categoricas = ['Município', 'Ano', 'Estados', 'Regiões']
        colunas_numericas = ['População']

        max_categorias = st.sidebar.slider(
            "Número máximo de categorias a exibir", 
            min_value=5, max_value=20, value=10, 
            key="max_categorias"
        )
        categoria_especifica = st.sidebar.text_input(
            "Buscar uma categoria específica (Município)", 
            "", key="categoria_especifica"
        )

        if categoria_especifica:
            sugestoes = sugerir_municipios(categoria_especifica, df, limite=5)
            st.sidebar.write(f"Você quis dizer: {', '.join(sugestoes)}?")
            
            municipio_selecionado = st.sidebar.selectbox(
                "Selecione um município sugerido", 
                sugestoes, key="municipio_selecionado"
            )
            categoria_especifica_normalizada = remover_acentos_e_lower(municipio_selecionado)
            df['Municipio_normalizado'] = df['Município'].apply(remover_acentos_e_lower)

        if 'Barra' in grafico_selecionado:
            x_col = st.selectbox(
                "Selecione a coluna X (categórica):", 
                options=colunas_categoricas, 
                key="barra_x_col"
            )
            y_col = st.selectbox(
                "Selecione a coluna Y (numérica):", 
                options=colunas_numericas, 
                key="barra_y_col"
            )

            top_n_df = filtered_df.nlargest(max_categorias, y_col)

            if categoria_especifica and municipio_selecionado:
                especifico_df = filtered_df[df['Municipio_normalizado'] == categoria_especifica_normalizada]
                top_n_df = pd.concat([top_n_df, especifico_df]).drop_duplicates()

            display_graphs(top_n_df, x_col, y_col, 'Barra')

        if 'Pizza' in grafico_selecionado:
            x_col = st.selectbox(
                "Selecione a coluna para as fatias (categórica):", 
                options=colunas_categoricas, 
                key="pizza_x_col"
            )
            y_col = st.selectbox(
                "Selecione a coluna para valores (numérica):", 
                options=colunas_numericas, 
                key="pizza_y_col"
            )

            top_n_df = filtered_df.nlargest(max_categorias, y_col)

            if categoria_especifica and municipio_selecionado:
                especifico_df = filtered_df[df['Municipio_normalizado'] == categoria_especifica_normalizada]
                top_n_df = pd.concat([top_n_df, especifico_df]).drop_duplicates()

            display_graphs(top_n_df, x_col, y_col, 'Pizza')

        if 'Linha' in grafico_selecionado:
            x_col = st.selectbox(
                "Selecione a coluna X (Ano ou categórica):", 
                options=['Ano'], 
                key="linha_x_col"
            )
            y_col = st.selectbox(
                "Selecione a coluna Y (numérica):", 
                options=colunas_numericas, 
                key="linha_y_col"
            )
            display_graphs(filtered_df, x_col, y_col, 'Linha')
        if 'Mapa' in grafico_selecionado:
            display_map(filtered_df)
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
    st.markdown("<h1>Análise de Dados Populacionais</h1>", unsafe_allow_html=True)

    menu = option_menu(
        menu_title="Menu",
        options=["Carregar Dados", "Estatísticas", "Visualização"],
        icons=["cloud-upload", "bar-chart", "eye"],
        menu_icon="cast",
        default_index=0,
        orientation="vertical",
        styles={
            "container": {"padding": "5px", "background-color": "#f0f2f6"},
            "icon": {"color": "orange", "font-size": "25px"},
            "nav-link": {
                "font-size": "16px", "text-align": "left",
                "margin": "0px",
                "--hover-color": "#eee",
            },
            "nav-link-selected": {"background-color": "#ff4b4b"},
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
