"""
Gerenciamento da sessão COM do Excel e helpers de baixo nível que espelham,
linha a linha, as chamadas que o VBA original fazia (Range.Copy +
PasteSpecial, Cells.ClearContents, Cells.UnMerge, etc.).

Usamos COM real (pywin32) e não openpyxl porque o formato de saída real é
.xlsb (confirmado inspecionando arquivos já processados no disco) — openpyxl
não escreve .xlsb. Isso exige Excel instalado na máquina que roda o script.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import pythoncom
import win32com.client as win32

logger = logging.getLogger(__name__)

# Constantes do Excel (conferidas via win32com.client.constants nesta máquina).
XL_PASTE_ALL = -4104
XL_UP = -4162
XL_CALCULATION_MANUAL = -4135
XL_CALCULATION_AUTOMATIC = -4105
XL_CENTER = -4108

# msoAutomationSecurity (biblioteca Office, não exposta via constants do
# Excel) — ForceDisable impede que qualquer VBA embutido nas planilhas que
# abrirmos rode automaticamente enquanto o COM está no comando.
MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3
MSO_AUTOMATION_SECURITY_BY_UI = 1


class ExcelSession:
    """Uma instância do Excel controlada via COM, com as mesmas flags que
    ProcessarEmLoop define no início (ScreenUpdating, DisplayAlerts, etc.)."""

    def __init__(self, visible: bool = False):
        self.visible = visible
        self.app = None
        self._security_original = None

    def __enter__(self) -> "ExcelSession":
        pythoncom.CoInitialize()
        self.app = win32.gencache.EnsureDispatch("Excel.Application")
        self.app.Visible = self.visible
        self.app.DisplayAlerts = False
        self.app.ScreenUpdating = False
        self.app.AskToUpdateLinks = False
        self.app.EnableEvents = False
        # Application.Calculation só pode ser definida com pelo menos uma
        # pasta de trabalho aberta (senão o Excel recusa com COM error) —
        # setada em set_calculation_manual() logo após abrir o primeiro
        # workbook.
        try:
            self._security_original = self.app.AutomationSecurity
            self.app.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
        except Exception:
            logger.warning("Não foi possível ajustar AutomationSecurity.", exc_info=True)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.app is not None:
                try:
                    self.app.Calculation = XL_CALCULATION_AUTOMATIC
                except Exception:
                    pass
                self.app.EnableEvents = True
                self.app.AskToUpdateLinks = True
                self.app.ScreenUpdating = True
                self.app.DisplayAlerts = True
                if self._security_original is not None:
                    self.app.AutomationSecurity = self._security_original
        finally:
            try:
                if self.app is not None:
                    self.app.Quit()
            finally:
                pythoncom.CoUninitialize()

    def open_workbook(self, path: Path, read_only: bool = False):
        wb = self.app.Workbooks.Open(str(path), False, read_only)
        # só pode ser setado com pelo menos um workbook aberto; idempotente.
        try:
            self.app.Calculation = XL_CALCULATION_MANUAL
        except Exception:
            logger.warning("Não foi possível forçar cálculo manual.", exc_info=True)
        return wb


@contextmanager
def open_workbook(session: ExcelSession, path: Path, read_only: bool = False):
    """Abre uma pasta de trabalho e garante o fechamento mesmo em erro.

    Diferente do VBA original (que às vezes deixa workbooks abertos em
    caminhos de erro), aqui SEMPRE fechamos — sem salvar se algo explodiu no
    meio, para não persistir estado inconsistente e não deixar EXCEL.EXE
    travando arquivos na pasta compartilhada.
    """
    wb = session.open_workbook(path, read_only=read_only)
    try:
        yield wb
    except Exception:
        try:
            wb.Close(SaveChanges=False)
        except Exception:
            logger.warning("Falha ao fechar workbook após erro: %s", path, exc_info=True)
        raise
    else:
        pass  # fechamento com save explícito fica a cargo do chamador


def copy_paste_all(src_range, dst_top_left, app) -> None:
    """Réplica de:
        src.Copy
        dst.PasteSpecial xlPasteAll
        Application.CutCopyMode = False
    """
    src_range.Copy()
    dst_top_left.PasteSpecial(Paste=XL_PASTE_ALL)
    app.CutCopyMode = False


def last_row(sheet, column_letter: str) -> int:
    """Réplica de: ws.Cells(ws.Rows.Count, column).End(xlUp).Row"""
    rows_count = sheet.Rows.Count
    cell = sheet.Cells(rows_count, column_letter)
    return cell.End(XL_UP).Row


def clear_sheets(wb, sheet_names) -> None:
    """Réplica do loop `For Each ws In wbDestino.Worksheets / If IsInArray(...)`
    dentro de CopiarArquivoOrigem, mas indexando direto pelo nome em vez de
    varrer todas as abas — mesmo resultado, sem depender da ordem das abas."""
    existentes = {s.Name for s in wb.Worksheets}
    for nome in sheet_names:
        if nome in existentes:
            wb.Sheets(nome).Cells.ClearContents()
        else:
            logger.warning("Aba %r não existe no workbook %r — nada a limpar.", nome, wb.Name)


def unmerge_all(sheet) -> None:
    """Réplica de: wsTarget.Cells.UnMerge"""
    sheet.Cells.UnMerge()
