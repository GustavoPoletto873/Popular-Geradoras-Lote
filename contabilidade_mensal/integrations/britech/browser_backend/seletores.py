"""Seletores da PAS — único lugar onde eles aparecem. Se a Britech mudar uma tela, o ajuste é aqui.

Origem: projeto do Lucas (britech/pas.py e balancete.py), observados na PAS real em 24/09/2026. Ids do DevExpress
(`dx*`) são estáveis por tela, mas dependem da versão do produto: por isso falhas de seletor viram `TelaMudou`.
"""

from __future__ import annotations

# --- login / sessão -------------------------------------------------------------------------------------------------
LOGIN_USUARIO = "#Login1_UserName"
LOGIN_SENHA = "#Login1_Password"
LINK_SAIR = "#LinkButtonSair"


def menu(texto: str) -> str:
    return f"span.dx-vam:has-text('{texto}')"


MENU_PROCESSAMENTO = menu("Processamento")
MENU_PROCESSO_CONTABIL = menu("Processo Contábil")

# --- Processo Contábil (grid dentro de iframe) ---------------------------------------------------------------------
PC_FILTRO_CARTEIRA = "#gridConsulta_DXFREditorcol1_I"
PC_CHECKBOX_PRIMEIRA_LINHA = "#gridConsulta_DXSelBtn0_D"
PC_BOTAO_PROCESSAR = "#btnRun"


def celula_com_titulo(valor: str) -> str:
    """Célula do grid cujo `title` é o id da carteira (é o que prova que o filtro já refletiu na tabela)."""
    return f"td.dxgv[title='{valor}']"


# --- Balancete Contábil ---------------------------------------------------------------------------------------------
BAL_CAMINHO = "Relatorios/Legais/Contabil/FiltroReportBalanceteContabil.aspx"
BAL_ABRIR_DROPDOWN = "#dropCliente_B-1Img"
BAL_FILTRO_CARTEIRA = "#dropCliente_DDD_gv_DXFREditorcol1_I"
BAL_CHECKBOX_PRIMEIRA_LINHA = "#dropCliente_DDD_gv_DXSelBtn0_D"
BAL_GRID = "#dropCliente_DDD_gv"
BAL_DATA_INICIO = "#textDataInicio_I"
BAL_DATA_FIM = "#textDataFim_I"
BAL_BOTAO_PDF = "#btnPDF"
BAL_BOTAO_EXCEL = "#btnExcel"
