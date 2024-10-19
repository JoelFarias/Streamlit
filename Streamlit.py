import plotly.express as px
import unicodedata
from fuzzywuzzy import process
import os
import psycopg2 as pg
import pandas as pd
import streamlit as st

@st.cache_data(ttl=600)
def load_data() -> pd.DataFrame | None:
    """Carrega os dados do banco de dados e renomeia as colunas."""
    try:
        conn = pg.connect(
            host=st.secrets["DB_HOST"],
            database=st.secrets["DB_NAME"],
            user=st.secrets["DB_USERNAME"],
            password=st.secrets["DB_PASSWORD"]
        )
        with conn.cursor() as cur:
            query = """
            SELECT 
                p.ano_pesquisa, 
                p.numero_habitantes, 
                p.faixa_populacao, 
                m.nome_municipio, 
                u.nome_uf, 
                r.nome_regiao, 
                m.latitude, 
                m.longitude 
            FROM populacao p
            JOIN municipio m ON p.codigo_municipio_dv = m.codigo_municipio_dv
            JOIN unidade_federacao u ON m.cd_uf = u.cd_uf
            JOIN regiao r ON u.cd_regiao = r.cd_regiao
            """
            cur.execute(query)
            data = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]

        df = pd.DataFrame(data, columns=colnames)

        mapeamento_colunas = {
            'ano_pesquisa': 'Ano',
            'numero_habitantes': 'População',
            'faixa_populacao': 'Faixa de População',
            'nome_municipio': 'Município',
            'nome_uf': 'Estados',
            'nome_regiao': 'Regiões',
            'latitude': 'Latitude',
            'longitude': 'Longitude'
        }
        df = renomear_colunas(df, mapeamento_colunas)
        df['Ano'] = df['Ano'].astype(str)
        df['População'] = pd.to_numeric(df['População'], errors='coerce')

        return df

    except (pg.Error, Exception) as e:
        st.error(f"Erro ao carregar os dados: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_dataframe() -> pd.DataFrame | None:
    """Recupera o DataFrame armazenado na sessão."""
    return st.session_state.get('df', None)

def renomear_colunas(df: pd.DataFrame, mapeamento_colunas: dict) -> pd.DataFrame:
    """Renomeia as colunas de um DataFrame."""
    return df.rename(columns=mapeamento_colunas)

def filter_data(df: pd.DataFrame, ano: str, estado: str, regiao: str) -> pd.DataFrame:
    """Filtra os dados com base nos parâmetros fornecidos."""
    return df[
        (df['Ano'] == ano) &
        ((df['Estados'] == estado) if estado != "Todos" else True) &
        ((df['Regiões'] == regiao) if regiao != "Todas" else True)
    ]

def display_graphs(df: pd.DataFrame, x_col: str, y_col: str, grafico: str):
    """Exibe gráficos com base na seleção."""
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
    """Exibe o mapa de população por município."""
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
    """Carrega e exibe os dados na interface."""
    with st.spinner('Carregando dados...'):
        df = load_data()
        if df is not None:
            st.dataframe(df.head())
            st.session_state.df = df

def exibir_estatisticas():
    """Exibe as estatísticas com base nos filtros de ano, estado e região."""
    df = get_dataframe()
    if df is not None:
        ano_pesquisa = st.sidebar.selectbox("Ano da Pesquisa", sorted(df['Ano'].unique(), reverse=True))
        estado = st.sidebar.selectbox("Estado", ["Todos"] + sorted(df['Estados'].unique()))
        regiao = st.sidebar.selectbox("Região", ["Todas"] + sorted(df['Regiões'].unique()))

        filtered_df = filter_data(df, ano_pesquisa, estado, regiao)
        if not filtered_df.empty:
            st.write("Estatísticas Descritivas para População:")
            st.write(filtered_df['População'].describe())

def remover_acentos_e_lower(texto: str) -> str:
    """Remove acentos e converte o texto para minúsculas."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    ).lower()

def sugerir_municipios(municipio_digitado: str, df: pd.DataFrame, limite: int = 5) -> list[str]:
    """Sugere municípios com base no nome digitado pelo usuário."""
    municipios = df['Município'].unique()
    municipios_normalizados = [remover_acentos_e_lower(m) for m in municipios]

    municipio_digitado_normalizado = remover_acentos_e_lower(municipio_digitado)
    sugestoes = process.extract(municipio_digitado_normalizado, municipios_normalizados, limit=limite)

    return [municipios[municipios_normalizados.index(m)] for m, _ in sugestoes]

def exibir_visualizacao():
    """Exibe gráficos e mapas de acordo com os filtros aplicados."""
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

        if 'Pizza' in grafico_selecionado or 'Barra' in grafico_selecionado:
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
            
def main():
    """Função principal para exibir a aplicação Streamlit."""
    st.title("Análise de Dados Populacionais")
    menu = st.sidebar.selectbox("Menu", ["Carregar Dados", "Estatísticas", "Visualização"])

    if menu == "Carregar Dados":
        carregar_dados()
    elif menu == "Estatísticas":
        exibir_estatisticas()
    elif menu == "Visualização":
        exibir_visualizacao()

if __name__ == "__main__":
    main()
