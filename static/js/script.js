const form = document.getElementById("uploadForm");
form.addEventListener("submit", async (e) => {
  e.preventDefault();

  // Limpa resultados anteriores
  document.getElementById("resultado").style.display = "none";
  document.getElementById("formatado").innerHTML = "";
  document.getElementById("json").textContent = "";

  const fileInput = document.getElementById("file");
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const response = await fetch("/upload", {
    method: "POST",
    body: formData,
  });

  const data = await response.json();

  document.getElementById("resultado").style.display = "block";
  document.getElementById("json").textContent = JSON.stringify(data, null, 2);

  let html = `
    <div class="card">
        <h2>Nota Fiscal</h2>
        <p><b>Número da Nota:</b> ${data.numeroNotaFiscal || "N/A"}</p>
        <p><b>Data de Emissão:</b> ${data.dataEmissao || "N/A"}</p>
        <p><b>Valor Total:</b> R$ ${data.valorTotal || "N/A"}</p>
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
        ${(data.itens && data.itens.length > 0) ? `<ul>${data.itens.map(item => `
            <li>${item.descricao || "Não informado"} - ${item.quantidade || 0} x R$ ${item.valorUnitario || 0}</li>
        `).join("")}</ul>` : "<p>Não há itens informados</p>"}
    </div>

    <div class="card">
        <h2>Parcelas</h2>
        ${(data.parcelas && data.parcelas.length > 0) ? `<ul>${data.parcelas.map((parcela, idx) => `
            <li>
                Parcela ${idx + 1} - 
                Vencimento: ${parcela.dataVencimento || "Não informado"} - 
                Valor: R$ ${parcela.valorParcela?.toFixed(2) || "Não informado"}
            </li>
        `).join("")}</ul>` : "<p>Não há parcelas informadas</p>"}
    </div>

    <div class="card">
        <h2>Classificação da Despesa</h2>
        <p>${data.classificacaoDespesa || "Outros"}</p>
    </div>
  `;

  document.getElementById("formatado").innerHTML = html;
});

// Botão LIMPAR
document.getElementById("limpar").addEventListener("click", () => {
  document.getElementById("resultado").style.display = "none";
  document.getElementById("formatado").innerHTML = "";
  document.getElementById("json").textContent = "";
  document.getElementById("file").value = "";

  // Resetar abas
  document.querySelectorAll(".tab-content").forEach(div => div.style.display = "none");
  document.getElementById("formatado").style.display = "block";
  document.querySelectorAll(".tabs button").forEach(btn => btn.classList.remove("active"));
  const firstTabBtn = document.querySelector(".tabs button");
  if (firstTabBtn) firstTabBtn.classList.add("active");
});

function mostrar(aba) {
  document.querySelectorAll(".tab-content").forEach(div => div.style.display = "none");
  document.querySelectorAll(".tabs button").forEach(btn => btn.classList.remove("active"));

  document.getElementById(aba).style.display = "block";
  event.target.classList.add("active");
}
