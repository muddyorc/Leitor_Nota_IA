document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("apiKeyInput");
  const salvarBtn = document.getElementById("salvarApiKey");
  const limparBtn = document.getElementById("limparApiKey");
  const statusEl = document.getElementById("apiKeyStatus");

  if (!input || !salvarBtn || !limparBtn) {
    return;
  }

  const setStatus = (texto, tipo = "info") => {
    if (!statusEl) {
      return;
    }
    statusEl.textContent = texto;
    statusEl.dataset.status = tipo;
  };

  const atualizarIndicador = async () => {
    try {
      const resp = await fetch("/status_api_key");
      if (!resp.ok) {
        setStatus("Não foi possível verificar a chave (status).", "erro");
        return;
      }
      const data = await resp.json();
      if (data.hasKey) {
        setStatus("Chave ativa para esta sessão/ambiente.", "ok");
      } else {
        setStatus("Nenhuma chave configurada. Cole a sua ou defina GOOGLE_API_KEY.", "alerta");
      }
    } catch (error) {
      console.error(error);
      setStatus("Erro ao verificar chave.", "erro");
    }
  };

  const enviarChave = async (valor) => {
    try {
      const resp = await fetch("/configurar_api_key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: valor }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setStatus(data.error || "Falha ao configurar a chave.", "erro");
        return;
      }
      setStatus(data.mensagem || "Chave atualizada.", valor ? "ok" : "alerta");
      if (!valor && input) {
        input.value = "";
      }
    } catch (error) {
      console.error(error);
      setStatus("Erro ao atualizar a chave.", "erro");
    } finally {
      atualizarIndicador();
    }
  };

  salvarBtn.addEventListener("click", () => {
    enviarChave(input.value.trim());
  });

  limparBtn.addEventListener("click", () => {
    enviarChave("");
  });

  atualizarIndicador();
});
