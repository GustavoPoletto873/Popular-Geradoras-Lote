"""PAS FALSA para testar os Page Objects sem tocar a Britech.

Reproduz, em HTML mínimo, os ids/estruturas que os seletores de `browser_backend/seletores.py` usam (login, menu,
iframe do Processo Contábil com grid cumulativo, tela de Balancete com downloads). É interceptada com
`context.route`: qualquer requisição que não seja para `*.britech.com.br` é ABORTADA, então o teste nunca sai da máquina.

NÃO prova que a Britech real se comporta assim — isso é o teste `@pytest.mark.browser` (tests/test_browser_real.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import BrowserContext, Route

CARTEIRAS = ["101", "1010", "44680491", "42754444", "700", "700"]  # "700" duplicado: busca ambígua

_LOGIN = """<!doctype html><html><body>
<input id="Login1_UserName"><input id="Login1_Password" type="password">
<div id="erro"></div>
<script>
document.getElementById('Login1_Password').addEventListener('keydown', async (e) => {
  if (e.key !== 'Enter') return;
  const r = await fetch('/PAS/login', {method: 'POST', body: JSON.stringify({
    u: document.getElementById('Login1_UserName').value, s: document.getElementById('Login1_Password').value})});
  if ((await r.json()).ok) location.href = '/PAS'; else document.getElementById('erro').textContent = 'Login inválido';
});
</script></body></html>"""

_PRINCIPAL = """<!doctype html><html><body>
<a id="LinkButtonSair" href="#">Sair</a>
<span class="dx-vam" id="m1">Processamento</span>
<span class="dx-vam" id="m2" style="display:none">Processo Contábil</span>
<div id="conteudo"></div>
<script>
document.getElementById('m1').onclick = () => document.getElementById('m2').style.display = 'inline';
document.getElementById('m2').onclick = () => setTimeout(() => {
  document.getElementById('conteudo').innerHTML = '<iframe id="f" src="/PAS/ProcessoContabil.aspx" width="600" height="400"></iframe>';
}, 300);
document.getElementById('LinkButtonSair').onclick = async (e) => {
  e.preventDefault(); await fetch('/PAS/logout', {method: 'POST'}); location.reload();
};
</script></body></html>"""

_PROCESSO_CONTABIL = """<!doctype html><html><body>
<input id="gridConsulta_DXFREditorcol1_I">
<table><tbody id="linhas"></tbody></table>
<div id="gridConsulta_DXSelBtn0_D" role="checkbox" aria-checked="false" style="width:30px;height:20px;border:1px solid">[ ]</div>
<button id="btnRun">Processar</button>
<script>
const TODAS = %(carteiras)s; const marcadas = new Set(); let visiveis = [];
const cx = document.getElementById('gridConsulta_DXSelBtn0_D');
function pintar() { cx.setAttribute('aria-checked', visiveis.length && marcadas.has(visiveis[0]) ? 'true' : 'false'); }
document.getElementById('gridConsulta_DXFREditorcol1_I').addEventListener('input', (e) => {
  const q = e.target.value;
  setTimeout(() => {
    visiveis = q ? TODAS.filter(c => c.includes(q)) : [];
    document.getElementById('linhas').innerHTML = visiveis.map(c => `<tr><td class="dxgv" title="${c}">${c}</td></tr>`).join('');
    pintar();
  }, 250);
});
cx.onclick = () => { if (!visiveis.length) return; const c = visiveis[0];
  marcadas.has(c) ? marcadas.delete(c) : marcadas.add(c); pintar(); };
document.getElementById('btnRun').onclick = () => fetch('/PAS/processar', {method: 'POST', body: JSON.stringify([...marcadas])});
</script></body></html>"""

_BALANCETE = """<!doctype html><html><body>
<div id="dropCliente_B-1Img" style="width:20px;height:20px;border:1px solid">v</div>
<div id="dropCliente_DDD_gv" style="display:none">
  <input id="dropCliente_DDD_gv_DXFREditorcol1_I">
  <table><tbody id="linhas"></tbody></table>
  <div id="dropCliente_DDD_gv_DXSelBtn0_D" role="checkbox" aria-checked="false" style="width:30px;height:20px;border:1px solid">[ ]</div>
</div>
<input id="textDataInicio_I"><input id="textDataFim_I">
<button id="btnPDF">PDF</button><button id="btnExcel">Excel</button>
<script>
const TODAS = %(carteiras)s; const marcadas = new Set(); let visiveis = [];
document.getElementById('dropCliente_B-1Img').onclick = () => document.getElementById('dropCliente_DDD_gv').style.display = 'block';
const cx = document.getElementById('dropCliente_DDD_gv_DXSelBtn0_D');
function pintar() { cx.setAttribute('aria-checked', visiveis.length && marcadas.has(visiveis[0]) ? 'true' : 'false'); }
const filtro = document.getElementById('dropCliente_DDD_gv_DXFREditorcol1_I');
filtro.addEventListener('keydown', (e) => { if (e.key !== 'Enter') return; const q = filtro.value;
  setTimeout(() => { visiveis = q ? TODAS.filter(c => c.includes(q)) : [];
    document.getElementById('linhas').innerHTML = visiveis.map(c => `<tr><td class="dxgv" title="${c}">${c}</td></tr>`).join('');
    pintar(); }, 250); });
cx.onclick = () => { if (!visiveis.length) return; const c = visiveis[0];
  marcadas.has(c) ? marcadas.delete(c) : marcadas.add(c); pintar(); };
for (const id of ['textDataInicio_I', 'textDataFim_I']) document.getElementById(id).addEventListener('input', (e) => {
  const d = e.target.value.replace(/\\D/g, '').slice(0, 8);
  e.target.value = d.length > 4 ? d.slice(0,2) + '/' + d.slice(2,4) + '/' + d.slice(4) : d.length > 2 ? d.slice(0,2) + '/' + d.slice(2) : d; });
function baixar(tipo) { const q = new URLSearchParams({carteiras: [...marcadas].join(','),
  ini: document.getElementById('textDataInicio_I').value, fim: document.getElementById('textDataFim_I').value});
  location.href = '/PAS/dl/' + tipo + '?' + q; }
document.getElementById('btnPDF').onclick = () => baixar('pdf');
document.getElementById('btnExcel').onclick = () => baixar('xls');
</script></body></html>"""


@dataclass
class PasFalsa:
    usuario: str = "usuario.teste"
    senha: str = "S3nh4-Secreta-Do-Teste"
    logado: bool = False
    logins: int = 0
    logouts: int = 0
    logout_funciona: bool = True  # False = a Britech "não deixa" sair (sessão presa)
    aceita_login: bool = True
    processamentos: list[list[str]] = field(default_factory=list)
    downloads: list[dict] = field(default_factory=list)
    requisicoes_bloqueadas: list[str] = field(default_factory=list)
    corpos_de_login: list[str] = field(default_factory=list)

    def derrubar_sessao(self) -> None:
        self.logado = False

    def instalar(self, contexto: BrowserContext) -> None:
        contexto.route(re.compile(r".*"), self._bloquear)  # registrada primeiro = menor prioridade
        contexto.route(re.compile(r"https://[^/]+\.britech\.com\.br/.*"), self._tratar)

    def _bloquear(self, rota: Route) -> None:
        self.requisicoes_bloqueadas.append(rota.request.url)
        rota.abort()

    def _html(self, rota: Route, corpo: str) -> None:
        rota.fulfill(status=200, content_type="text/html; charset=utf-8", body=corpo)

    def _json(self, rota: Route, dados) -> None:
        rota.fulfill(status=200, content_type="application/json", body=json.dumps(dados))

    def _tratar(self, rota: Route) -> None:
        req = rota.request
        url = urlparse(req.url)
        caminho = url.path.rstrip("/")
        carteiras = json.dumps(CARTEIRAS)

        if caminho == "/PAS/login":
            corpo = json.loads(req.post_data or "{}")
            self.corpos_de_login.append(req.post_data or "")
            ok = self.aceita_login and corpo.get("u") == self.usuario and corpo.get("s") == self.senha
            if ok:
                self.logado = True
                self.logins += 1
            return self._json(rota, {"ok": ok})
        if caminho == "/PAS/logout":
            if self.logout_funciona:
                self.logado = False
                self.logouts += 1
            return self._json(rota, {"ok": self.logout_funciona})
        if caminho == "/PAS/processar":
            self.processamentos.append(json.loads(req.post_data or "[]"))
            return self._json(rota, {"ok": True})

        if not self.logado:
            return self._html(rota, _LOGIN)  # qualquer tela sem sessão devolve o login

        if caminho == "/PAS":
            return self._html(rota, _PRINCIPAL)
        if caminho == "/PAS/ProcessoContabil.aspx":
            return self._html(rota, _PROCESSO_CONTABIL % {"carteiras": carteiras})
        if caminho.endswith("FiltroReportBalanceteContabil.aspx"):
            return self._html(rota, _BALANCETE % {"carteiras": carteiras})
        if caminho.startswith("/PAS/dl/"):
            tipo = caminho.rsplit("/", 1)[1]
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            self.downloads.append({"tipo": tipo, **q})
            corpo = f"balancete|{q.get('carteiras')}|{q.get('ini')}|{q.get('fim')}".encode()
            nome = f"BalanceteContabil_{q.get('carteiras')}.{tipo}"
            return rota.fulfill(
                status=200,
                body=corpo,
                headers={"Content-Type": "application/octet-stream", "Content-Disposition": f'attachment; filename="{nome}"'},
            )
        rota.fulfill(status=404, body="não encontrado")
