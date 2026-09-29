"""
Testa só a integração do callback de resolução de ambiguidade
(`resolver_ambiguidade`) dentro de `executar_batch_steps`, sem precisar de
Excel de verdade — session/workbook são mocks, já que o que queremos
verificar é o fluxo de decisão, não a chamada COM em si.
"""

from unittest.mock import MagicMock

from populador import populate


def _sessao_fake():
    session = MagicMock()
    session.open_workbook.return_value = MagicMock()
    return session


def test_resolver_ambiguidade_usa_escolha_manual(tmp_path):
    # dois candidatos ambíguos pra carteira_final, sem "Inicial" no nome
    (tmp_path / "Carteira_x_31-12-2024.xlsx").touch()
    (tmp_path / "Carteira_x_31-12-2025.xlsx").touch()

    escolhido = tmp_path / "Carteira_x_31-12-2025.xlsx"
    resolver = MagicMock(return_value=escolhido)

    session = _sessao_fake()
    wb_destino = MagicMock()

    avisos = populate.executar_batch_steps(session, wb_destino, tmp_path, resolver_ambiguidade=resolver)

    mensagens_carteira = [a for a in avisos if "carteira_final" in a]
    assert len(mensagens_carteira) == 1
    assert "resolvida manualmente" in mensagens_carteira[0]
    assert escolhido.name in mensagens_carteira[0]
    resolver.assert_any_call("carteira_final", [tmp_path / "Carteira_x_31-12-2024.xlsx", escolhido])


def test_resolver_ambiguidade_none_mantem_ambiguo(tmp_path):
    (tmp_path / "Carteira_x_31-12-2024.xlsx").touch()
    (tmp_path / "Carteira_x_31-12-2025.xlsx").touch()

    resolver = MagicMock(return_value=None)  # usuário pulou (opção "0")

    session = _sessao_fake()
    wb_destino = MagicMock()

    avisos = populate.executar_batch_steps(session, wb_destino, tmp_path, resolver_ambiguidade=resolver)

    mensagens_carteira = [a for a in avisos if "carteira_final" in a]
    assert len(mensagens_carteira) == 1
    assert "ambíguos" in mensagens_carteira[0]


def test_sem_resolver_ambiguidade_nao_pergunta_nada(tmp_path):
    (tmp_path / "Carteira_x_31-12-2024.xlsx").touch()
    (tmp_path / "Carteira_x_31-12-2025.xlsx").touch()

    session = _sessao_fake()
    wb_destino = MagicMock()

    # sem resolver_ambiguidade (padrão), comportamento não-interativo de sempre
    avisos = populate.executar_batch_steps(session, wb_destino, tmp_path)

    mensagens_carteira = [a for a in avisos if "carteira_final" in a]
    assert len(mensagens_carteira) == 1
    assert "ambíguos" in mensagens_carteira[0]
