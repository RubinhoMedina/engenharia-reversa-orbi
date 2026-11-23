import { useState } from "react";
import {
  Activity,
  Bell,
  Check,
  KeyRound,
  Link,
  LoaderCircle,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Unplug,
} from "lucide-react";
import { api } from "./api";

type ConnectionStatus = Record<string, any>;
type Props = {
  status: ConnectionStatus;
  busy: boolean;
  action: (task: () => Promise<void>) => void;
  notify: (text: string) => void;
};

function applicationKey(value: string): ArrayBuffer {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const decoded = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const key = new Uint8Array(decoded.length);
  for (let i = 0; i < decoded.length; i++) key[i] = decoded.charCodeAt(i);
  return key.buffer;
}

export function Connections({ status, busy, action, notify }: Props) {
  const [check, setCheck] = useState("");
  const push = status.push || {},
    ai = status.ai || {},
    commerce = status.commerce || {},
    auth = status.auth || {};
  async function subscribe() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window))
      throw new Error(
        "Web Push exige navegador compatível e contexto seguro. No iPhone, instale na Tela de Início.",
      );
    if (!push.configured)
      throw new Error("Configure as chaves Web Push pelo assistente local.");
    if ((await Notification.requestPermission()) !== "granted")
      throw new Error("Permissão de notificações não concedida.");
    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription)
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationKey(push.public_key),
      });
    await api("push/subscribe", { subscription: subscription.toJSON() });
    notify("Este dispositivo foi inscrito para receber avisos.");
  }
  async function unsubscribe() {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await api("push/unsubscribe", { endpoint: subscription.endpoint });
      await subscription.unsubscribe();
    }
    notify("Avisos deste dispositivo desativados.");
  }
  return (
    <>
      <div className="connection-intro">
        <Link size={24} />
        <div>
          <h2>Conecte os motores do Orbit</h2>
          <p>
            Use Configure-Orbit.ps1 na pasta do projeto para informar
            credenciais em sua máquina. Reinicie o servidor e teste as conexões
            aqui.
          </p>
        </div>
      </div>
      <div className="settings-grid">
        <section className="panel form-panel">
          <div className="connection-title">
            <ShieldCheck size={19} />
            <h2>Acesso ao seu workspace</h2>
            <span className="tag">
              {auth.configured ? "Senha configurada" : "Acesso local"}
            </span>
          </div>
          <p>
            Login de proprietário único com senha protegida e sessão no
            navegador. O assistente permite criar sua senha.
          </p>
          <p className="muted">
            {status.config?.public_url ||
              "Servidor local · configure domínio HTTPS para acesso externo."}
          </p>
          {auth.configured && (
            <button
              className="secondary"
              onClick={() =>
                action(async () => {
                  await api("auth/logout", {});
                  window.dispatchEvent(new Event("orbit-auth-required"));
                })
              }
            >
              <LogOut size={15} /> Sair
            </button>
          )}
        </section>
        <section className="panel form-panel">
          <div className="connection-title">
            <Activity size={19} />
            <h2>Motor de inteligência</h2>
            <span className="tag">
              {ai.provider === "rules"
                ? "Regras locais"
                : ai.configured
                  ? "Configurado"
                  : "Aguardando configuração"}
            </span>
          </div>
          <p>
            {ai.provider === "rules"
              ? "Análise por regras e roteiro editorial disponíveis. Conecte um modelo para gerar conteúdo e diagnósticos personalizados."
              : `${ai.provider} · ${ai.model || "modelo ausente"}`}
          </p>
          <p>
            Ollama usa um modelo na sua máquina. OpenAI usa uma chave API e
            exige habilitação de chamadas remotas no assistente.
          </p>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              action(async () => {
                const result = await api("ai/test", {});
                setCheck(result.detail);
              })
            }
          >
            <RefreshCw size={15} /> Testar motor
          </button>
          {check && <p role="status">{check}</p>}
          <p className="muted">
            O teste consulta disponibilidade. A geração é acionada por você nas
            ferramentas.
          </p>
        </section>
        <section className="panel form-panel">
          <div className="connection-title">
            <Link size={19} />
            <h2>TikTok Shop Creator</h2>
            <span className="tag">
              {commerce.connected
                ? "Creator autorizado"
                : commerce.configured
                  ? "Pronto para autorizar"
                  : "Credenciais pendentes"}
            </span>
          </div>
          <p>
            Requer aplicativo aprovado no Partner Center, App Key, App Secret,
            callback e escopos Creator. O mercado Brasil precisa estar
            habilitado para seu aplicativo.
          </p>
          <a
            className="text-button"
            href="https://partner.tiktokshop.com/"
            target="_blank"
            rel="noreferrer"
          >
            Abrir Partner Center
          </a>
          <button
            className="primary"
            disabled={busy || !commerce.configured}
            onClick={() =>
              action(async () => {
                const result = await api("commerce/tiktok/start", {});
                window.location.assign(result.authorize_url);
              })
            }
          >
            <Link size={15} /> Autorizar no TikTok
          </button>
          {commerce.connected && (
            <div className="button-row">
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    await api("commerce/tiktok/refresh", {});
                    notify("Autorização renovada.");
                  })
                }
              >
                Renovar autorização
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    await api("commerce/tiktok/disconnect", {});
                    notify("Credenciais locais removidas.");
                  })
                }
              >
                <Unplug size={14} /> Desconectar
              </button>
            </div>
          )}
          <div className="info">
            A autorização conecta a identidade Creator. A sincronização de
            vendas oficiais aguarda validação do endpoint e dos campos
            disponíveis no aplicativo aprovado.
          </div>
          {commerce.oauth_status?.detail && (
            <p
              role="status"
              className={commerce.oauth_status.ok ? "muted" : "error-text"}
            >
              {commerce.oauth_status.detail}
            </p>
          )}
          {commerce.token_expired && (
            <p className="error-text">
              A validade do token terminou. Use Renovar autorização.
            </p>
          )}
          {commerce.granted_scopes?.length > 0 && (
            <p>Permissões recebidas · {commerce.granted_scopes.join(", ")}</p>
          )}
        </section>
        <section className="panel form-panel">
          <div className="connection-title">
            <RefreshCw size={19} />
            <h2>Exportações automáticas</h2>
            <span className="tag">
              {commerce.imports?.directory_exists
                ? "Pasta disponível"
                : "Pasta pendente"}
            </span>
          </div>
          <p>
            Escolha uma pasta no assistente e salve nela suas exportações CSV ou
            JSON no formato de pedidos do Orbit. O servidor verifica novos
            arquivos, concilia alterações e registra a origem manual.
          </p>
          <button
            className="secondary"
            disabled={busy || !commerce.imports?.configured}
            onClick={() =>
              action(async () => {
                const result = await api("commerce/imports/scan", {});
                notify(
                  `Importação verificada. ${result.changed || 0} alterações e ${result.errors?.length || 0} arquivos com erro.`,
                );
              })
            }
          >
            Verificar pasta agora
          </button>
          {commerce.imports?.last_run?.timestamp && (
            <p>
              Última verificação ·{" "}
              {new Date(
                commerce.imports.last_run.timestamp * 1000,
              ).toLocaleString("pt-BR")}
            </p>
          )}
          {commerce.imports?.last_run?.errors?.map((item: any) => (
            <p key={item.file} className="error-text">
              {item.file} · {item.error}
            </p>
          ))}
        </section>
        <section className="panel form-panel">
          <div className="connection-title">
            <Bell size={19} />
            <h2>Avisos no celular</h2>
            <span className="tag">
              {push.configured ? "Web Push configurado" : "Chaves pendentes"}
            </span>
          </div>
          <p>
            Configure o contato VAPID no assistente, instale o app e autorize
            este dispositivo. O worker entrega as novas atualizações enquanto o
            servidor estiver ligado.
          </p>
          <div className="button-row">
            <button
              className="primary"
              disabled={busy || !push.configured}
              onClick={() => action(subscribe)}
            >
              Ativar neste dispositivo
            </button>
            <button
              className="secondary"
              disabled={busy || !push.configured}
              onClick={() =>
                action(async () => {
                  const result = await api("push/test", {});
                  notify(
                    `Teste enfileirado para ${result.queued} dispositivo(s). A entrega depende do serviço push e do navegador.`,
                  );
                })
              }
            >
              Enviar teste
            </button>
          </div>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => action(unsubscribe)}
          >
            Desativar neste dispositivo
          </button>
          <p className="muted">
            {push.devices || 0} dispositivos · {push.pending || 0} entregas
            pendentes · worker {push.worker_running ? "ativo" : "parado"}
          </p>
          <p>
            Atualizações de demonstração e importação são identificadas como
            teste de atualização. Avisos de comissão oficial exigem fonte
            autorizada.
          </p>
        </section>
        <section className="panel form-panel">
          <div className="connection-title">
            <Check size={19} />
            <h2>Dados e transcrição</h2>
          </div>
          <p>
            SQLite mantém pedidos e históricos. FFmpeg prepara o áudio e Whisper
            transcreve localmente. Credenciais e inscrições push ficam
            protegidas no servidor.
          </p>
          <p>
            Este workspace atende um proprietário. Para manter alertas fora da
            sua máquina, é necessário hospedar backend, worker e armazenamento
            persistente com domínio HTTPS.
          </p>
        </section>
      </div>
    </>
  );
}

export function Login({ onLogin }: { onLogin: () => Promise<void> }) {
  const [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="login-page">
      <section className="panel form-panel">
        <KeyRound size={30} />
        <h1>Seu espaço no Orbit.</h1>
        <p>Entre com a senha de proprietário configurada nesta instalação.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              await api("auth/login", { password });
              setPassword("");
              await onLogin();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Falha no login.");
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Senha
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy && <LoaderCircle size={15} className="spin" />} Entrar
          </button>
        </form>
      </section>
    </div>
  );
}
