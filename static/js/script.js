const form = document.getElementById("uploadForm");
const resultado = document.getElementById("resultado");
const formatado = document.getElementById("formatado");
const jsonView = document.getElementById("json");
const verificacaoCard = document.getElementById("verificacao");
const acoesLancamento = document.querySelector(".acoes-lancamento");
const botaoLancar = document.getElementById("lancar");
const mensagemLancamento = document.getElementById("lancarMensagem");

let dadosExtraidos = null;

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  limparResultado();

  const fileInput = document.getElementById("file");
  if (!fileInput.files.length) {
    mensagemLancamento.textContent = "Selecione um arquivo PDF.";
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  try {
    const response = await fetch("/extrair", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();
    if (!response.ok) {
      mensagemLancamento.textContent = data.error || "Falha na extração.";
      return;
    }

    dadosExtraidos = data;
    preencherResultados(data);
  } catch (error) {
    mensagemLancamento.textContent = "Erro inesperado durante a extração.";
    console.error(error);
  }
});

botaoLancar.addEventListener("click", async () => {
  if (!dadosExtraidos) {
    return;
  }

  const payload = JSON.parse(JSON.stringify(dadosExtraidos));
  delete payload._verificacao;

  try {
    botaoLancar.disabled = true;
    mensagemLancamento.textContent = "Lançando conta...";

    const response = await fetch("/lancar_conta", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const resultado = await response.json();
    if (response.ok) {
      mensagemLancamento.textContent = resultado.mensagem || "Conta lançada com sucesso.";
    } else {
      mensagemLancamento.textContent = resultado.error || "Falha ao lançar conta.";
    }
  } catch (error) {
    mensagemLancamento.textContent = "Erro inesperado ao lançar conta.";
    console.error(error);
  } finally {
    botaoLancar.disabled = false;
  }
});

function preencherResultados(data) {
  resultado.style.display = "block";
  jsonView.textContent = JSON.stringify(data, null, 2);

  const parcelasHtml = (data.parcelas && data.parcelas.length > 0)
    ? `<ul>${data.parcelas.map((parcela, idx) => `
        <li>
            Parcela ${idx + 1} - 
            Vencimento: ${parcela.dataVencimento || "Não informado"} - 
            Valor: R$ ${formataValor(parcela.valorParcela)}
        </li>
      `).join("")}</ul>`
    : "<p>Não há parcelas informadas</p>";

  const itensHtml = (data.itens && data.itens.length > 0)
    ? `<ul>${data.itens.map(item => `
        <li>${item.descricao || "Não informado"} - ${item.quantidade || 0} x R$ ${formataValor(item.valorUnitario)}</li>
      `).join("")}</ul>`
    : "<p>Não há itens informados</p>";

  const html = `
    <div class="card">
        <h2>Nota Fiscal</h2>
        <p><b>Número da Nota:</b> ${data.numeroNotaFiscal || "N/A"}</p>
        <p><b>Data de Emissão:</b> ${data.dataEmissao || "N/A"}</p>
        <p><b>Valor Total:</b> R$ ${formataValor(data.valorTotal)}</p>
        <p><b>Protocolo de Autorização:</b> ${data.protocoloAutorizacao || "Não informado"}</p>
        <p><b>Chave de Acesso:</b> ${data.chaveAcesso || "Não informado"}</p>
    </div>

    <div class="card">
        <h2>Fornecedor</h2>
        <p><b>Razão Social:</b> ${data.fornecedor?.razaoSocial || "N/A"}</p>
        <p><b>CNPJ:</b> ${data.fornecedor?.cnpj || "N/A"}</p>
        <p><b>Fantasia:</b> ${data.fornecedor?.fantasia || "Não informado"}</p>
    </div>

    <div class="card">
        <h2>Faturado</h2>
        <p><b>Nome Completo:</b> ${data.faturado?.nomeCompleto || "Não informado"}</p>
        <p><b>CPF:</b> ${data.faturado?.cpf || "Não informado"}</p>
    </div>

    <div class="card">
        <h2>Endereço do Faturado</h2>
        <p><b>Endereço:</b> ${data.faturado?.endereco || "Não informado"}</p>
        <p><b>Bairro:</b> ${data.faturado?.bairro || "Não informado"}</p>
        <p><b>CEP:</b> ${data.faturado?.cep || "Não informado"}</p>
    </div>

    <div class="card">
        <h2>Itens</h2>
        ${itensHtml}
    </div>

    <div class="card">
        <h2>Parcelas</h2>
        ${parcelasHtml}
    </div>

    <div class="card">
        <h2>Classificação da Despesa</h2>
        <p>${Array.isArray(data.classificacaoDespesa) ? data.classificacaoDespesa.join(", ") : (data.classificacaoDespesa || "Outros")}</p>
    </div>
  `;

  formatado.innerHTML = html;
  renderizarVerificacao(data._verificacao, data);
}

function renderizarVerificacao(verificacao, dados) {
  if (!verificacao) {
    verificacaoCard.style.display = "none";
    acoesLancamento.style.display = "none";
    return;
  }

  const fornecedorInfo = verificacao.fornecedor || {};
  const faturadoInfo = verificacao.faturado || {};

  const fornecedorNome = dados.fornecedor?.razaoSocial || fornecedorInfo.nome || "Fornecedor";
  const fornecedorDoc = dados.fornecedor?.cnpj || fornecedorInfo.documento || "Não informado";
  const faturadoNome = dados.faturado?.nomeCompleto || faturadoInfo.nome || "Faturado";
  const faturadoDoc = dados.faturado?.cpf || faturadoInfo.documento || "Não informado";

  const fornecedorStatus = formatarStatus(fornecedorInfo);
  const faturadoStatus = formatarStatus(faturadoInfo);

  const classificacoes = (verificacao.classificacoes || []).map((item) => {
    const status = item && item.status === "EXISTE" && item.id
      ? `${item.status} – ID: ${item.id}`
      : item?.status || "DESCONHECIDO";
    return `
      <li>
        <p class="status-label">DESPESA</p>
        <p class="status-valor">${item?.descricao || "Não informado"}</p>
        <p class="status-resultado">${status}</p>
      </li>`;
  }).join("") || `
    <li>
      <p class="status-label">DESPESA</p>
      <p class="status-valor">Nenhuma classificação informada</p>
      <p class="status-resultado">NÃO INFORMADO</p>
    </li>`;

  verificacaoCard.innerHTML = `
    <h2>Verificação no Sistema</h2>
    <div class="status-secao">
      <p class="status-label">FORNECEDOR</p>
      <p class="status-valor">${fornecedorNome}</p>
      <p class="status-valor">Documento: ${formataDocumento(fornecedorDoc)}</p>
      <p class="status-resultado">${fornecedorStatus}</p>
    </div>
    <div class="status-secao">
      <p class="status-label">FATURADO</p>
      <p class="status-valor">${faturadoNome}</p>
      <p class="status-valor">Documento: ${formataDocumento(faturadoDoc)}</p>
      <p class="status-resultado">${faturadoStatus}</p>
    </div>
    <div class="status-secao">
      <p class="status-label">DESPESA</p>
      <ul class="status-lista">${classificacoes}</ul>
    </div>
  `;

  verificacaoCard.style.display = "block";
  acoesLancamento.style.display = "flex";
  mensagemLancamento.textContent = "";
}

function limparResultado() {
  resultado.style.display = "none";
  formatado.innerHTML = "";
  jsonView.textContent = "";
  verificacaoCard.style.display = "none";
  acoesLancamento.style.display = "none";
  mensagemLancamento.textContent = "";
  dadosExtraidos = null;
}

// Botão LIMPAR
document.getElementById("limpar").addEventListener("click", () => {
  limparResultado();
  document.getElementById("file").value = "";

  // Resetar abas
  document.querySelectorAll(".tab-content").forEach(div => div.style.display = "none");
  document.getElementById("formatado").style.display = "block";
  document.querySelectorAll(".tabs button").forEach(btn => btn.classList.remove("active"));
  const firstTabBtn = document.querySelector(".tabs button");
  if (firstTabBtn) firstTabBtn.classList.add("active");
});

function mostrar(aba, evento) {
  document.querySelectorAll(".tab-content").forEach(div => div.style.display = "none");
  document.querySelectorAll(".tabs button").forEach(btn => btn.classList.remove("active"));

  document.getElementById(aba).style.display = "block";
  if (evento && evento.target) {
    evento.target.classList.add("active");
  }
}

function formataValor(valor) {
  if (valor === null || valor === undefined || valor === "") {
    return "Não informado";
  }

  let numero = valor;
  if (typeof valor === "string") {
    numero = Number(valor.replace(/R\$|\s/g, "").replace(/\./g, "").replace(",", "."));
  }

  if (typeof numero !== "number") {
    numero = Number(numero);
  }

  if (Number.isNaN(numero)) {
    return valor;
  }

  return numero.toFixed(2);
}

function formataDocumento(doc) {
  if (!doc || doc === "Não informado") {
    return "Não informado";
  }

  const digits = doc.replace(/\D/g, "");
  if (digits.length === 14) {
    return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
  }
  if (digits.length === 11) {
    return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  }
  return doc;
}

function formatarStatus(info) {
  if (!info || info.status === "NÃO INFORMADO") {
    return "NÃO INFORMADO";
  }

  if (info.status === "EXISTE" && info.id) {
    return `EXISTE – ID: ${info.id}`;
  }

  return info.status || "DESCONHECIDO";
}
