import streamlit as st
import psycopg2 as pg
import pandas as pd
import plotly.express as px

def renomear_colunas(df, mapeamento_colunas):
    """
    Renomeia as colunas de um DataFrame com base em um dicionário de mapeamento.
    """
    return df.rename(columns=mapeamento_colunas)

@st.cache_data
def load_data():
    """
    Carrega os dados do banco de dados e renomeia as colunas.
    """
    try:
        st.write("Tentando conectar ao banco de dados...")
        conexao = pg.connect(
            host=st.secrets["DB_HOST"],
            database=st.secrets["DB_NAME"],
            user=st.secrets["DB_USERNAME"],
            password=st.secrets["DB_PASSWORD"]
        )

        cur = conexao.cursor()
        st.write("Conexão estabelecida com sucesso.")

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

        cur.close()
        conexao.close()

        st.write("Dados carregados com sucesso.")

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

        if 'Ano' in df.columns:
            df['Ano'] = df['Ano'].astype(str)
        
        if 'População' in df.columns:
            df['População'] = pd.to_numeric(df['População'], errors='coerce')

        return df

    except KeyError as e:
        st.error(f"Chave de configuração faltando: {e}")
        return pd.DataFrame()  # Retornar DataFrame vazio em caso de exceção

    except Exception as e:
        st.error(f"Erro ao carregar os dados: {e}")
        return pd.DataFrame()  # Retornar DataFrame vazio em caso de exceção


def display_graphs(df, x_col, y_col, grafico_selecionado):
    """
    Exibe gráficos com base nas colunas e tipo de gráfico selecionado.
    """
    if df is not None and not df.empty:  # Adiciona verificação se o df não é None
        if 'Barra' in grafico_selecionado:
            fig1 = px.bar(df, x=x_col, y=y_col, color='Estados', barmode='group',
                          title=f'{y_col} por {x_col}')
            fig1.update_layout(xaxis_title=x_col, yaxis_title=y_col)
            st.plotly_chart(fig1)

        if 'Pizza' in grafico_selecionado:
            fig2 = px.pie(df, names=x_col, values=y_col,
                          title=f'Distribuição de {y_col} por {x_col}')
            fig2.update_layout(title_text=f'Distribuição de {y_col} por {x_col}')
            st.plotly_chart(fig2)

        if 'Linha' in grafico_selecionado:
            fig3 = px.line(df, x=x_col, y=y_col, color='Estados',
                           title=f'{y_col} ao longo de {x_col}')
            fig3.update_layout(xaxis_title=x_col, yaxis_title=y_col)
            st.plotly_chart(fig3)
    else:
        st.write("Nenhum dado disponível para os filtros selecionados.")

def display_map(df):
    """
    Exibe o mapa de população por município.
    """
    st.subheader("Mapa de População por Município")
    if df is not None and not df.empty and 'Latitude' in df.columns and 'Longitude' in df.columns:  # Adiciona verificação se o df não é None
        mapa_fig = px.scatter_mapbox(df, lat="Latitude", lon="Longitude", size="População",
                                     color="Estados", hover_name="Município",
                                     title="Distribuição Populacional",
                                     mapbox_style="carto-positron", zoom=3)
        st.plotly_chart(mapa_fig)
    else:
        st.write("Dados de latitude e longitude não disponíveis.")

def main():
    """
    Função principal para exibir a aplicação Streamlit.
    """
    st.title("Análise de Dados Populacionais")

    menu = st.sidebar.selectbox("Menu", ["Carregar Dados", "Estatísticas", "Visualização"])

    if menu == "Carregar Dados":
        st.subheader("Carregar e Visualizar Dados")
        
        df = load_data()

        if df is not None and df.empty:
            st.write("Nenhum dado disponível.")
        else:
            st.write("Visualização das primeiras linhas do DataFrame:")
            st.dataframe(df.head())
            st.session_state.df = df

    elif menu == "Estatísticas":
        st.subheader("Estatísticas Descritivas")
        if 'df' in st.session_state:
            df = st.session_state.df

            if df is not None and df.empty:
                st.write("Nenhum dado disponível.")
            else:
                st.sidebar.header("Filtros para Estatísticas")
                
                anos_disponiveis = df['Ano'].unique()
                estados_disponiveis = df['Estados'].unique()
                regioes_disponiveis = df['Regiões'].unique()

                ano_pesquisa = st.sidebar.selectbox("Ano da Pesquisa", options=sorted(anos_disponiveis, reverse=True), index=0)
                estado = st.sidebar.selectbox("Estado (opcional)", options=["Todos"] + sorted(estados_disponiveis))
                regiao = st.sidebar.selectbox("Região (opcional)", options=["Todas"] + sorted(regioes_disponiveis))

                filtered_df = df[
                    (df['Ano'] == ano_pesquisa) & 
                    ((df['Estados'] == estado) if estado != "Todos" else True) &
                    ((df['Regiões'] == regiao) if regiao != "Todas" else True)
                ]

                if not filtered_df.empty:
                    st.write("Estatísticas Descritivas para População:")
                    estatisticas = filtered_df['População'].describe()
                    st.write(estatisticas)
                else:
                    st.write("Nenhum dado disponível para os filtros selecionados.")
        else:
            st.write("Carregue os dados na seção 'Carregar Dados'.")

    elif menu == "Visualização":
        st.subheader("Visualização de Dados")

        if 'df' in st.session_state:
            df = st.session_state.df

            if df is not None and df.empty:
                st.write("Nenhum dado disponível.")
            else:
                st.sidebar.header("Filtros")

                anos_disponiveis = df['Ano'].unique()
                estados_disponiveis = df['Estados'].unique()
                regioes_disponiveis = df['Regiões'].unique()

                ano_pesquisa = st.sidebar.selectbox("Ano da Pesquisa", options=sorted(anos_disponiveis, reverse=True), index=0)
                estado = st.sidebar.selectbox("Estado", options=["Todos"] + sorted(estados_disponiveis))
                regiao = st.sidebar.selectbox("Região", options=["Todas"] + sorted(regioes_disponiveis))

                filtered_df = df[
                    (df['Ano'] == ano_pesquisa) & 
                    ((df['Estados'] == estado) if estado != "Todos" else True) &
                    ((df['Regiões'] == regiao) if regiao != "Todas" else True)
                ]

                grafico_selecionado = st.sidebar.multiselect(
                    "Escolha os gráficos para exibir:",
                    ["Barra", "Pizza", "Linha", "Mapa"],
                    default=["Barra", "Pizza", "Linha", "Mapa"]
                )

                st.write("### Selecione as Colunas para os Gráficos")
                col1, col2, col3 = st.columns([1, 2, 1])

                with col2:
                    x_col = st.selectbox("Selecione a coluna X:", options=filtered_df.columns)
                    y_col = st.selectbox("Selecione a coluna Y:", options=filtered_df.columns)

                display_graphs(filtered_df, x_col, y_col, grafico_selecionado)
                
                if 'Mapa' in grafico_selecionado:
                    display_map(filtered_df)
        else:
            st.write("Carregue os dados na seção 'Carregar Dados'.")

if __name__ == "__main__":
    main()
