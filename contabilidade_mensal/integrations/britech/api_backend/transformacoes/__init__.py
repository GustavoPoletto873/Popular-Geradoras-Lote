"""Transformações PURAS (DataFrame/JSON → DataFrame) dos relatórios da Britech.

Portadas do downloader do Simplifica (`*_ctb_britech.py`) preservando o resultado byte a byte
no Excel gerado (paridade verificada contra o código original — ver tests/test_paridade_*.py
e tools/paridade/). Sem rede, sem disco, sem Streamlit.
"""
