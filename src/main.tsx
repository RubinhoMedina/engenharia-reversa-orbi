import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowUpRight,
  Bell,
  Check,
  ChevronRight,
  CircleHelp,
  Clapperboard,
  Home,
  LoaderCircle,
  Plus,
  Search,
  Settings,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import "./style.css";
import { api } from "./api";
import { Connections, Login } from "./connections";

type Row = Record<string, any>;
type State = {
  orders: Row[];
  scripts: Row[];
  creators: Row[];
  analyses: Row[];
};
const blank: State = { orders: [], scripts: [], creators: [], analyses: [] };
const money = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    n || 0,
  );
const businessDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Sao_Paulo",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
function saoPauloDay(value: Date) {
  const parts = businessDate.formatToParts(value);
  const part = (kind: string) =>
    parts.find((item) => item.type === kind)?.value;
  return [part("year"), part("month"), part("day")].join("-");
}
function orderDay(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const instant = new Date(value);
  return Number.isNaN(instant.getTime()) ? "" : saoPauloDay(instant);
}
function periodDays(count: number) {
  const today = Date.parse(saoPauloDay(new Date()) + "T12:00:00Z");
  return Array.from({ length: count }, (_, i) =>
    new Date(today - (count - 1 - i) * 86400000).toISOString().slice(0, 10),
  );
}
const pages = [
  { name: "Visão geral", icon: Home },
  { name: "Analisar vídeo", icon: Clapperboard },
  { name: "Criar conteúdo", icon: Sparkles },
  { name: "Creators", icon: Users },
  { name: "Conta e fontes", icon: Settings },
];
function App() {
  const [session, setSession] = useState<{
    authenticated: boolean;
    configured: boolean;
  } | null>(null);
  const [connections, setConnections] = useState<Record<string, any>>({});
  const [page, setPage] = useState(0),
    [data, setData] = useState<State>(blank),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [period, setPeriod] = useState("30"),
    [account, setAccount] = useState("Todas as contas"),
    [importing, setImporting] = useState(false),
    [source, setSource] = useState("manual");
  async function refresh() {
    try {
      const auth = await api("auth/status");
      setSession(auth);
      if (!auth.authenticated) {
        setData(blank);
        return;
      }
      const [s, integrations] = await Promise.all([
        api("state"),
        api("integrations"),
      ]);
      setData({ ...blank, ...s });
      setConnections(integrations);
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    refresh();
    const requireLogin = () => {
      setSession({ authenticated: false, configured: true });
      setData(blank);
    };
    window.addEventListener("orbit-auth-required", requireLogin);
    if ("serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    return () =>
      window.removeEventListener("orbit-auth-required", requireLogin);
  }, []);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const visibleDays = new Set(periodDays(Number(period)));
  const orders = data.orders.filter(
    (order) =>
      order.source === source &&
      (account === "Todas as contas" || order.account === account) &&
      visibleDays.has(orderDay(order.date)),
  );
  const valid = orders.filter((order) => order.status === "pago");
  const accounts = [
    ...new Set(
      data.orders
        .filter((order) => order.source === source)
        .map((order) => order.account),
    ),
  ];
  const sum = (key: string, items = valid) =>
    items.reduce(
      (total, order) => total + Math.round(Number(order[key] || 0) * 100),
      0,
    ) / 100;
  const demo =
    source === "demo" &&
    data.orders.some(
      (o) => o.source === "demo" || o.source === "DEMO" || o.is_demo,
    );
  function exportData() {
    const b = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(b);
    const a = document.createElement("a");
    a.href = url;
    a.download = "orbit-dados.json";
    a.click();
    URL.revokeObjectURL(url);
  }
  if (session && !session.authenticated) return <Login onLogin={refresh} />;
  if (!session && !error)
    return (
      <div className="login-page">
        <LoaderCircle className="spin" />
        <p>Conectando ao seu workspace…</p>
      </div>
    );
  return (
    <div className="shell">
      <aside>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage(0);
          }}
        >
          <span className="orbit-mark" />
          orbit<span className="brand-dot">.</span>
        </a>
        <div className="workspace">
          <span className="avatar">CC</span>
          <div>
            Meu workspace<small>Creator Commerce</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {pages.map((p, i) => (
            <button
              className={page === i ? "active" : ""}
              key={p.name}
              onClick={() => setPage(i)}
            >
              <p.icon size={18} />
              {p.name}
              {page === i && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="source-icon">
            <Activity size={18} />
          </div>
          <strong>Seus dados, com origem.</strong>
          <p>Conecte suas informações para acompanhar cada resultado.</p>
          <button className="secondary" onClick={() => setPage(4)}>
            Gerenciar fontes <ArrowUpRight size={15} />
          </button>
          <div className="help">
            <CircleHelp size={16} /> MVP local · versão 0.1
          </div>
        </div>
      </aside>
      <div className="main">
        <header>
          <span>
            Workspace <ChevronRight size={13} /> <b>{pages[page].name}</b>
          </span>
          <div>
            <button
              className="icon-button"
              title="Configurar notificações"
              onClick={() => setPage(4)}
            >
              <Bell size={18} />
            </button>
            <span className="header-avatar">CC</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <h1>
                {
                  [
                    "Seu próximo resultado começa aqui.",
                    "Um olhar atento ao seu conteúdo.",
                    "Do produto ao próximo vídeo.",
                    "Encontre referências para criar.",
                    "Conexões do seu workspace.",
                  ][page]
                }
              </h1>
              <p>
                {
                  [
                    "Acompanhe suas vendas e transforme dados em boas decisões.",
                    "Revise a estrutura do vídeo e encontre pontos para melhorar.",
                    "Organize seus argumentos e construa um roteiro para gravar.",
                    "Organize creators e métricas com uma fonte identificada.",
                    "Gerencie seus dados, a instalação e os avisos.",
                  ][page]
                }
              </p>
            </div>
            {page === 0 && (
              <button className="secondary" onClick={exportData}>
                <ArrowDownToLine size={16} /> Exportar dados
              </button>
            )}
          </div>
          {error && (
            <div role="alert" className="alert error">
              {error}
              <button onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="alert">
              {notice}
              <button onClick={() => setNotice("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {page === 0 && (
            <>
              <div className="source-strip">
                <span className="status-dot" />
                <span>
                  {orders.length
                    ? demo
                      ? "Demonstração · valores fictícios"
                      : "Importação manual · dados fornecidos"
                    : "Nenhuma fonte conectada"}
                </span>
                <span className="muted">
                  {orders.length
                    ? `${orders.length} registros disponíveis`
                    : "Comece importando seus pedidos"}
                </span>
                <button onClick={() => setPage(4)}>
                  Gerenciar <ArrowUpRight size={14} />
                </button>
              </div>
              <div className="section-toolbar">
                <h2>Seu desempenho</h2>
                <div className="filters">
                  <select
                    aria-label="Fonte"
                    value={source}
                    onChange={(e) => {
                      setSource(e.target.value);
                      setAccount("Todas as contas");
                    }}
                  >
                    <option value="manual">Importação manual</option>
                    <option value="demo">Demonstração</option>
                  </select>
                  <select
                    aria-label="Conta"
                    value={account}
                    onChange={(e) => setAccount(e.target.value)}
                  >
                    <option>Todas as contas</option>
                    {accounts.map((a) => (
                      <option key={a}>{a}</option>
                    ))}
                  </select>
                  <div className="segments">
                    {["1", "7", "30"].map((p) => (
                      <button
                        key={p}
                        className={period === p ? "selected" : ""}
                        onClick={() => setPeriod(p)}
                      >
                        {p === "1" ? "Hoje" : p + " dias"}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="metrics">
                {[
                  [
                    "Vendas · GMV",
                    money(sum("gmv")),
                    "Valor bruto dos pedidos válidos",
                  ],
                  [
                    "Comissão estimada",
                    money(
                      sum(
                        "commission",
                        valid.filter(
                          (o) =>
                            !o.commission_status ||
                            o.commission_status === "estimada",
                        ),
                      ),
                    ),
                    "Sujeita à validação da origem",
                  ],
                  [
                    "Comissão aprovada",
                    money(
                      sum(
                        "commission",
                        valid.filter((o) => o.commission_status === "aprovada"),
                      ),
                    ),
                    "Aprovada pela fonte",
                  ],
                  [
                    "Comissão liquidada",
                    money(
                      sum(
                        "commission",
                        valid.filter(
                          (o) => o.commission_status === "liquidada",
                        ),
                      ),
                    ),
                    "Pagamento informado na origem",
                  ],
                ].map(([label, value, sub], i) => (
                  <div className={"metric metric-" + i} key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                    <small>{sub}</small>
                  </div>
                ))}
              </div>
              <div className="chart-layout">
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Evolução das vendas</h2>
                      <p>GMV por dia no período selecionado</p>
                    </div>
                    <span className="legend">
                      <i />
                      Vendas
                    </span>
                  </div>
                  <Chart orders={valid} days={Number(period)} />
                  <div className="chart-footer">
                    <span>
                      {
                        new Set(
                          orders.map((order) =>
                            JSON.stringify([
                              order.account,
                              order.order_id || order.id,
                            ]),
                          ),
                        ).size
                      }{" "}
                      pedidos
                    </span>
                    <span>{sum("quantity", valid)} unidades vendidas</span>
                    <span>
                      {
                        orders.filter((order) =>
                          ["cancelado", "reembolsado"].includes(order.status),
                        ).length
                      }{" "}
                      itens cancelados ou devolvidos
                    </span>
                  </div>
                </section>
                <section className="next-panel">
                  <span className="mint-icon">
                    <Sparkles size={21} />
                  </span>
                  <h2>
                    O próximo vídeo
                    <br />
                    pode começar agora.
                  </h2>
                  <p>
                    Transforme o benefício do seu produto em ideias, ganchos e
                    um roteiro pronto para editar.
                  </p>
                  <button className="primary" onClick={() => setPage(2)}>
                    Criar meu conteúdo <ArrowUpRight size={16} />
                  </button>
                  <button className="text-button" onClick={() => setPage(1)}>
                    Ou analisar um vídeo <ChevronRight size={15} />
                  </button>
                </section>
              </div>
              <section className="panel orders">
                <div className="panel-heading">
                  <div>
                    <h2>Pedidos recentes</h2>
                    <p>Valores e status conforme a fonte de cada registro</p>
                  </div>
                  <button
                    className="secondary"
                    onClick={() => setImporting(true)}
                  >
                    <Plus size={15} /> Importar pedidos
                  </button>
                </div>
                {orders.length ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Produto / pedido</th>
                          <th>Conta</th>
                          <th>GMV</th>
                          <th>Comissão</th>
                          <th>Status</th>
                          <th>Origem</th>
                        </tr>
                      </thead>
                      <tbody>
                        {orders
                          .slice()
                          .sort((left, right) =>
                            orderDay(right.date).localeCompare(
                              orderDay(left.date),
                            ),
                          )
                          .slice(0, 30)
                          .map((o, i) => (
                            <tr key={o.id + "-" + i}>
                              <td>
                                <b>{o.product}</b>
                                <small>
                                  {o.order_id || o.source_id || o.id} ·{" "}
                                  {orderDay(o.date)}
                                </small>
                              </td>
                              <td>{o.account}</td>
                              <td>{money(o.gmv)}</td>
                              <td className="mint">{money(o.commission)}</td>
                              <td>
                                <span className="tag">{o.status}</span>
                              </td>
                              <td>{o.source || "Importação manual"}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty">
                    <Activity size={26} />
                    <h3>Seu histórico começa com o primeiro pedido</h3>
                    <p>
                      Importe um arquivo ou explore o painel com dados
                      demonstrativos.
                    </p>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        action(async () => {
                          await api("demo", {});
                          setSource("demo");
                          setAccount("Todas as contas");
                        })
                      }
                    >
                      Explorar demonstração
                    </button>
                  </div>
                )}
              </section>
            </>
          )}
          {page === 1 && <Video data={data} action={action} busy={busy} />}
          {page === 2 && (
            <Generator
              provider={connections.ai?.provider || "rules"}
              data={data}
              action={action}
              busy={busy}
              notify={setNotice}
            />
          )}
          {page === 3 && <Creators data={data} action={action} busy={busy} />}
          {page === 4 && (
            <Connections
              status={connections}
              busy={busy}
              action={action}
              notify={setNotice}
            />
          )}
        </main>
        <footer>
          Orbit Creator Commerce{" "}
          <span>Clareza para vender. Espaço para criar.</span>
        </footer>
      </div>
      {importing && (
        <ImportModal
          close={() => setImporting(false)}
          busy={busy}
          submit={(payload) =>
            action(async () => {
              await api("orders/import", payload);
              setImporting(false);
              setSource("manual");
              setAccount("Todas as contas");
              setNotice(
                "Importação concluída. Registros conciliados por identificador.",
              );
            })
          }
        />
      )}
    </div>
  );
}
function Chart({ orders, days }: { orders: Row[]; days: number }) {
  const count = Math.min(days, 30);
  const dates = periodDays(count);
  const values = dates.map((d) =>
    orders
      .filter((o) => orderDay(o.date) === d)
      .reduce((s, o) => s + Number(o.gmv || 0), 0),
  );
  const max = Math.max(...values, 1);
  const points = values
    .map(
      (v, i) =>
        `${40 + i * (650 / Math.max(count - 1, 1))},${190 - (v / max) * 145}`,
    )
    .join(" ");
  return (
    <div className="chart">
      <svg
        viewBox="0 0 730 230"
        role="img"
        aria-label="Gráfico de vendas diárias"
      >
        <defs>
          <linearGradient id="area" x1="0" x2="0" y1="0" y2="1">
            <stop stopColor="#65e5c4" stopOpacity=".18" />
            <stop offset="1" stopColor="#65e5c4" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <line
              x1="40"
              x2="690"
              y1={45 + i * 48}
              y2={45 + i * 48}
              stroke="#273237"
              strokeDasharray="3 6"
            />
            <text x="3" y={48 + i * 48} fill="#829198" fontSize="10">
              {Math.round(max * (1 - i / 3))}
            </text>
          </g>
        ))}
        <polygon points={`40,190 ${points} 690,190`} fill="url(#area)" />
        <polyline
          points={points}
          fill="none"
          stroke="#65e5c4"
          strokeWidth="2.5"
        />
        {[0, Math.floor((count - 1) / 2), count - 1].map((i, j) => (
          <text
            key={j}
            x={40 + (i * 650) / Math.max(count - 1, 1)}
            y="220"
            fill="#829198"
            fontSize="11"
            textAnchor="middle"
          >
            {dates[i]?.slice(5).split("-").reverse().join("/")}
          </text>
        ))}
      </svg>
      {!orders.length && (
        <span className="chart-empty">Aguardando seus dados</span>
      )}
    </div>
  );
}
function Generator({
  provider,
  data,
  action,
  busy,
  notify,
}: {
  provider: string;
  data: State;
  action: (f: () => Promise<void>) => void;
  busy: boolean;
  notify: (s: string) => void;
}) {
  const [form, setForm] = useState({
      product: "",
      persona: "",
      benefit: "",
      style: "Demonstração",
      duration: "30",
      objective: "Apresentar o produto",
    }),
    [result, setResult] = useState(""),
    [mode, setMode] = useState(provider === "rules" ? "editorial" : "ai"),
    [provenance, setProvenance] = useState<Record<string, any>>({
      method:
        provider === "rules"
          ? "Modelo editorial local v1"
          : "IA conectada · aguardando geração",
    });
  function field(k: keyof typeof form, label: string) {
    return (
      <label>
        {label}
        <input
          required
          value={form[k]}
          onChange={(e) => setForm({ ...form, [k]: e.target.value })}
        />
      </label>
    );
  }
  function generate() {
    if (mode === "editorial") {
      generateEditorial();
      setProvenance({ method: "Modelo editorial local v1" });
      return;
    }
    action(async () => {
      const response = await api("ai/generate", form);
      setResult(response.content);
      setProvenance(response);
    });
  }
  function generateEditorial() {
    const {
      product: p,
      benefit: b,
      persona: who,
      style,
      duration,
      objective,
    } = form;
    const end = Number(duration);
    setResult(
      `PRODUTO: ${p}\nPúblico: ${who} · Formato: ${style}\nObjetivo: ${objective}\n\n3 ÂNGULOS\n1. Demonstrar o uso do produto no cotidiano de ${who}.\n2. Explicar como verificar o benefício informado: ${b}.\n3. Mostrar o produto em detalhes e responder dúvidas frequentes.\n\n3 GANCHOS\n1. “Como ${p} entra na sua rotina? Vou mostrar.”\n2. “Antes de escolher ${p}, veja este detalhe.”\n3. “Você procura ${b}? Vamos olhar este produto de perto.”\n\nROTEIRO · ${duration}s\n[00–03s] Gancho: escolha uma das aberturas acima, mostrando o produto.\n[03–${Math.round(end * 0.4)}s] Contexto: apresente uma situação real do seu público, sem prometer resultados.\n[${Math.round(end * 0.4)}–${end - 5}s] Demonstração: mostre ${p} em uso e confira o benefício “${b}” com evidência própria.\n[${end - 5}–${end}s] CTA: “Confira os detalhes e veja se faz sentido para você.”\n\nLEGENDAS\n1. ${p} na prática. Veja os detalhes antes de escolher.\n2. Um olhar de perto em ${p}. O que você gostaria de saber?\n\nHASHTAGS SUGERIDAS\n#demonstracao #review #tiktokshop\n\nMétodo: modelo editorial local v1. Benefício fornecido pelo usuário, sem verificação automática.`,
    );
  }
  return (
    <div className="two-columns">
      <section className="panel form-panel">
        <h2>Seu produto, seu ponto de partida</h2>
        <p>Informe apenas benefícios que você consegue comprovar.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            generate();
          }}
        >
          <label>
            Motor de criação
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="editorial">Modelo editorial local</option>
              <option value="ai">IA conectada no servidor</option>
            </select>
          </label>
          {field("product", "Nome do produto")}
          {field("persona", "Para quem você vai falar?")}
          {field("benefit", "Benefício comprovável")}
          <div className="form-row">
            <label>
              Formato
              <select
                value={form.style}
                onChange={(e) => setForm({ ...form, style: e.target.value })}
              >
                {["Demonstração", "UGC", "Review", "Depoimento"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Duração
              <select
                value={form.duration}
                onChange={(e) => setForm({ ...form, duration: e.target.value })}
              >
                {["15", "30", "60"].map((v) => (
                  <option key={v} value={v}>
                    {v} segundos
                  </option>
                ))}
              </select>
            </label>
          </div>
          {field("objective", "Objetivo")}
          <button className="primary" type="submit" disabled={busy}>
            <Sparkles size={17} />{" "}
            {busy ? "Gerando conteúdo…" : "Gerar roteiro"}
          </button>
        </form>
        <h3>Roteiros salvos · {data.scripts.length}</h3>
        {data.scripts.map((s, i) => (
          <button
            className="history-row"
            key={i}
            onClick={() => {
              setResult(s.content || s.script || JSON.stringify(s));
              setProvenance({
                method: s.method || "Roteiro salvo",
                model: s.model,
                provider: s.provider,
              });
            }}
          >
            {s.product || s.title || "Roteiro salvo"}
            <ChevronRight size={14} />
          </button>
        ))}
      </section>
      <section className="panel form-panel">
        <h2>Seu roteiro</h2>
        <p className="muted">
          {provenance.method}
          {provenance.model ? " · " + provenance.model : ""}
        </p>
        <p>
          Edite o texto antes de gravar. Escolha o modelo editorial ou a IA
          configurada em Conta e fontes.
        </p>
        {result ? (
          <>
            <textarea
              aria-label="Roteiro editável"
              className="script"
              value={result}
              onChange={(e) => setResult(e.target.value)}
            />
            <div className="button-row">
              <button
                className="primary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    await api("scripts", {
                      ...form,
                      content: result,
                      method: provenance.method,
                      provider: provenance.provider,
                      model: provenance.model,
                      usage: provenance.usage,
                    });
                    notify("Roteiro salvo no histórico.");
                  })
                }
              >
                <Check size={16} /> Salvar roteiro
              </button>
              <button
                className="secondary"
                onClick={() =>
                  navigator.clipboard
                    .writeText(result)
                    .then(() => notify("Texto copiado."))
                    .catch(() => notify("Selecione o texto para copiar."))
                }
              >
                Copiar
              </button>
            </div>
          </>
        ) : (
          <div className="empty">
            <Sparkles size={30} />
            <h3>Uma ideia vira um bom começo.</h3>
            <p>
              Preencha os detalhes do produto para gerar três ganchos e um
              roteiro editável.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
function Video({
  data,
  action,
  busy,
}: {
  data: State;
  action: (f: () => Promise<void>) => void;
  busy: boolean;
}) {
  const [consent, setConsent] = useState(false);
  const [engine, setEngine] = useState("configured");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState(""),
    [name, setName] = useState(""),
    [duration, setDuration] = useState(0),
    [transcript, setTranscript] = useState(""),
    [result, setResult] = useState<Row | null>(null),
    [error, setError] = useState("");
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  return (
    <div className="two-columns">
      <section className="panel form-panel">
        <h2>Analise o seu vídeo</h2>
        <p>
          Transcrição local do áudio com Whisper e avaliação pelo motor
          configurado. O arquivo temporário é apagado após o processamento.
        </p>
        <label className="dropzone">
          <Clapperboard size={30} />
          <strong>{name || "Selecionar vídeo"}</strong>
          <span>MP4, WebM ou MOV · até 100 MB · 3 minutos</span>
          <input
            type="file"
            accept="video/mp4,video/webm,video/quicktime"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              if (
                f.size > 100 * 1024 * 1024 ||
                !["video/mp4", "video/webm", "video/quicktime"].includes(f.type)
              ) {
                setError("Use um vídeo válido de até 100 MB.");
                return;
              }
              setError("");
              setDuration(0);
              setConsent(false);
              setFile(f);
              setName(f.name);
              setUrl(URL.createObjectURL(f));
            }}
          />
        </label>
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />{" "}
          Tenho autorização para enviar e analisar este vídeo.
        </label>
        {file && (
          <button
            className="primary"
            disabled={busy || duration > 180 || !consent}
            onClick={() =>
              action(async () => {
                const r = await fetch("/api/videos", {
                  method: "POST",
                  headers: {
                    "Content-Type": file.type,
                    "X-Filename": encodeURIComponent(file.name),
                  },
                  body: file,
                });
                const value = await r.json();
                if (r.status === 401)
                  window.dispatchEvent(new Event("orbit-auth-required"));
                if (!r.ok)
                  throw Error(value.error || "Falha ao processar vídeo");
                setTranscript(value.transcript);
                setResult(value.analysis);
              })
            }
          >
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <Clapperboard size={16} />
            )}{" "}
            Transcrever e analisar vídeo
          </button>
        )}
        {url && (
          <video
            controls
            src={url}
            onLoadedMetadata={(e) => {
              const d = e.currentTarget.duration;
              setDuration(d);
              if (d > 180) setError("O limite deste piloto é de 3 minutos.");
            }}
          />
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            action(async () => {
              const a = await api("analyses", {
                transcript,
                duration: duration || 60,
                filename: name,
                engine,
              });
              setResult(a);
            });
          }}
        >
          <label>
            Transcrição do conteúdo
            <textarea
              required
              minLength={10}
              placeholder="Cole ou revise a fala do vídeo."
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
            />
          </label>
          <label>
            Motor da análise manual
            <select value={engine} onChange={(e) => setEngine(e.target.value)}>
              <option value="configured">Motor configurado</option>
              <option value="rules">Avaliação local por regras</option>
            </select>
          </label>
          <button
            className="primary"
            disabled={busy || duration > 180 || !consent}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Activity size={16} />
            )}{" "}
            Avaliar estrutura
          </button>
        </form>
      </section>
      <section className="panel form-panel">
        <h2>Diagnóstico e histórico</h2>
        <p>
          O motor configurado avalia a transcrição. O FFmpeg estima mudanças
          entre quadros. O significado das imagens e a entonação exigem revisão
          humana.
        </p>
        {result && <AnalysisReport value={result} />}
        {!result && !data.analyses.length && (
          <div className="empty">
            <Clapperboard size={30} />
            <h3>Seu conteúdo sob uma nova perspectiva</h3>
            <p>
              Receba observações sobre gancho, desenvolvimento, storytelling e
              CTA.
            </p>
          </div>
        )}
        {data.analyses.map((a, i) => (
          <button className="history-row" key={i} onClick={() => setResult(a)}>
            {a.filename || a.title || "Análise " + (i + 1)}
            <ChevronRight size={14} />
          </button>
        ))}
      </section>
    </div>
  );
}
function AnalysisReport({ value }: { value: Row }) {
  return (
    <div className="analysis-report">
      <div className="info">
        {value.method}
        <p>{value.limitations}</p>
      </div>
      {value.analysis_notice && (
        <p role="status" className="info">
          {value.analysis_notice}
        </p>
      )}
      {value.visual?.available && (
        <section>
          <h3>Mudanças visuais</h3>
          <p>
            {value.visual.change_count} mudanças estimadas ·{" "}
            {value.visual.method}
          </p>
          {value.visual.changes.length > 0 && (
            <p>
              {value.visual.changes
                .map((time: number) => time.toFixed(2) + "s")
                .join(" · ")}
            </p>
          )}
          <p>Movimento e iluminação também podem disparar a detecção.</p>
        </section>
      )}
      {value.dimensions?.map((d: Row) => (
        <section key={d.name}>
          <div className="panel-heading">
            <h3>{d.name}</h3>
            <span className="tag">{d.status}</span>
          </div>
          <p>{d.reason}</p>
          {d.evidence && (
            <p>
              {d.timestamp != null && <b>{d.timestamp}s · </b>}
              {d.evidence}
            </p>
          )}
          <p>{d.suggestion}</p>
        </section>
      ))}
      {value.segments?.length > 0 && (
        <details>
          <summary>Transcrição com tempos</summary>
          {value.segments.map((s: Row, i: number) => (
            <p key={i}>
              <b>{Number(s.start).toFixed(1)}s</b> {s.text}
            </p>
          ))}
        </details>
      )}
      <h3>Alternativa de gancho</h3>
      <p>{value.hook}</p>
      <h3>Estrutura sugerida</h3>
      <p style={{ whiteSpace: "pre-line" }}>{value.revised_script}</p>
    </div>
  );
}
function Creators({
  data,
  action,
  busy,
}: {
  data: State;
  action: (f: () => Promise<void>) => void;
  busy: boolean;
}) {
  const [q, setQ] = useState(""),
    [adding, setAdding] = useState(false),
    [form, setForm] = useState({
      handle: "",
      niche: "",
      url: "",
      caption: "",
      video_url: "",
      metric_source: "",
      gmv: "",
      sales: "",
      commissions: "",
      partnerships: "",
    });
  const filtered = data.creators.filter((c) =>
    [c.handle, c.niche, c.url, c.video_url, c.caption].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(q.trim().toLowerCase()),
    ),
  );
  return (
    <>
      <div className="section-toolbar">
        <div className="search">
          <Search size={17} />
          <input
            aria-label="Buscar creators"
            placeholder="Buscar por nome, nicho, URL ou legenda"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <button className="primary" onClick={() => setAdding(!adding)}>
          <Plus size={16} /> Adicionar creator
        </button>
      </div>
      {adding && (
        <form
          className="panel creator-form"
          onSubmit={(e) => {
            e.preventDefault();
            action(async () => {
              await api("creators", form);
              setAdding(false);
            });
          }}
        >
          {(["handle", "niche", "url"] as const).map((key, i) => (
            <label key={key}>
              {["Nome ou @identificador", "Nicho", "URL pública do perfil"][i]}
              <input
                required={key === "handle"}
                type={key === "url" ? "url" : "text"}
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </label>
          ))}
          <label>
            URL do vídeo de referência
            <input
              type="url"
              value={form.video_url}
              onChange={(e) => setForm({ ...form, video_url: e.target.value })}
            />
          </label>
          <label>
            Legenda e hashtags fornecidas
            <textarea
              value={form.caption}
              onChange={(e) => setForm({ ...form, caption: e.target.value })}
            />
          </label>
          <label>
            Fonte e data das métricas
            <input
              value={form.metric_source}
              onChange={(e) =>
                setForm({ ...form, metric_source: e.target.value })
              }
            />
          </label>
          {(["gmv", "sales", "commissions", "partnerships"] as const).map(
            (key, i) => (
              <label key={key}>
                {
                  [
                    "GMV informado (R$)",
                    "Vendas informadas",
                    "Comissões informadas (R$)",
                    "Parcerias informadas",
                  ][i]
                }
                <input
                  disabled={!form.metric_source.trim()}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
              </label>
            ),
          )}
          <button className="primary" disabled={busy}>
            Salvar referência
          </button>
        </form>
      )}
      <div className="info">
        GMV, vendas, comissões e parcerias de terceiros exigem uma fonte
        autorizada. Adicionar um perfil registra uma referência fornecida por
        você.
      </div>
      {filtered.length ? (
        <>
          <CreatorHashtags creators={filtered} />
          <div className="creator-grid">
            {filtered.map((c, i) => (
              <section key={i} className="panel form-panel">
                <span className="creator-avatar">
                  {c.handle?.replace("@", "").slice(0, 2).toUpperCase()}
                </span>
                <h2>{c.handle}</h2>
                <p>{c.niche || "Nicho não informado"}</p>
                {c.url && /^https?:\/\//.test(c.url) && (
                  <a
                    className="text-button"
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Abrir perfil <ArrowUpRight size={14} />
                  </a>
                )}
                <dl>
                  {["GMV", "Vendas", "Comissões", "Parcerias"].map((k, i) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>
                        {c.metric_source &&
                        c[["gmv", "sales", "commissions", "partnerships"][i]]
                          ? c[
                              ["gmv", "sales", "commissions", "partnerships"][i]
                            ]
                          : "Indisponível sem acesso autorizado"}
                      </dd>
                    </div>
                  ))}
                </dl>
                {c.metric_source && <p>Fonte informada · {c.metric_source}</p>}
                {c.caption && (
                  <>
                    <h3>Legenda de referência</h3>
                    <p>{c.caption}</p>
                    <h3>Hashtags no conteúdo</h3>
                    <p>
                      {[
                        ...new Set(c.caption.match(/#[\p{L}\p{N}_]+/gu) || []),
                      ].join(" ") || "Nenhuma hashtag fornecida"}
                    </p>
                  </>
                )}
                {c.video_url && /^https?:\/\//.test(c.video_url) && (
                  <a
                    className="text-button"
                    target="_blank"
                    rel="noreferrer"
                    href={c.video_url}
                  >
                    Vídeo fornecido <ArrowUpRight size={14} />
                  </a>
                )}
                <small className="muted">Origem · cadastro manual</small>
              </section>
            ))}
          </div>
        </>
      ) : (
        <section className="panel empty">
          <Users size={32} />
          <h3>
            {q
              ? "Nenhum creator encontrado"
              : "Construa seu repertório de referências"}
          </h3>
          <p>
            Adicione perfis que você acompanha e encontre-os por nome ou nicho.
          </p>
        </section>
      )}
    </>
  );
}
function CreatorHashtags({ creators }: { creators: Row[] }) {
  const totals = new Map<string, number>();
  const seen = new Set<string>();
  for (const creator of creators) {
    const caption = String(creator.caption || "").trim();
    if (!caption) continue;
    const key = JSON.stringify([
      creator.handle?.toLowerCase(),
      creator.video_url || caption,
    ]);
    if (seen.has(key)) continue;
    seen.add(key);
    const tags = new Set(
      caption.toLowerCase().match(/#[\p{L}\p{N}_]+/gu) || [],
    );
    for (const tag of tags) totals.set(tag, (totals.get(tag) || 0) + 1);
  }
  const top = [...totals]
    .sort(
      (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
    )
    .slice(0, 8);
  if (!top.length) return null;
  return (
    <section className="panel form-panel" style={{ marginBottom: 18 }}>
      <h2>Hashtags nas referências</h2>
      <p>
        Frequência nas {seen.size} legendas fornecidas que correspondem à busca.
      </p>
      <div className="button-row">
        {top.map(([tag, count]) => (
          <span key={tag} className="tag">
            {tag} · {count}
          </span>
        ))}
      </div>
    </section>
  );
}
function ImportModal({
  close,
  submit,
  busy,
}: {
  close: () => void;
  submit: (payload: { orders: Row[] } | { csv: string }) => void;
  busy: boolean;
}) {
  const [format, setFormat] = useState("json");
  const [text, setText] = useState(""),
    [error, setError] = useState("");
  return (
    <div className="modal-backdrop">
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Importar pedidos"
        className="modal panel form-panel"
      >
        <div className="panel-heading">
          <h2>Importar seus pedidos</h2>
          <button className="icon-button" aria-label="Fechar" onClick={close}>
            <X size={20} />
          </button>
        </div>
        <p>
          Envie um arquivo JSON ou CSV com identificadores únicos por item.
          Reimportar o mesmo identificador atualiza o registro.
        </p>
        <label>
          Formato da importação
          <select
            value={format}
            onChange={(e) => {
              setFormat(e.target.value);
              setText("");
              setError("");
            }}
          >
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
          </select>
        </label>
        <code>
          {format === "csv"
            ? "id,order_id,product,gmv,commission,status,date,account,quantity,commission_status"
            : '[{"id":"pedido-item","account":"minha-conta","product":"Produto","gmv":100,"commission":10,"quantity":1,"status":"pago","commission_status":"estimada","date":"2026-11-20"}]'}
        </code>
        <a className="secondary" href="/pedidos-modelo.csv" download>
          <ArrowDownToLine size={15} /> Baixar modelo CSV
        </a>
        <input
          type="file"
          accept=".csv,.json,text/csv,application/json"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) {
              if (f.size > 2 * 1024 * 1024) {
                setError("Limite de 2 MB por solicitação.");
                return;
              }
              setFormat(f.name.toLowerCase().endsWith(".csv") ? "csv" : "json");
              setText(await f.text());
              setError("");
            }
          }}
        />
        <textarea
          aria-label={format.toUpperCase() + " dos pedidos"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"Cole seu " + format.toUpperCase() + " aqui"}
        />
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <button
          disabled={busy}
          className="primary"
          onClick={() => {
            try {
              if (!text.trim()) throw Error("Informe o conteúdo do arquivo.");
              if (format === "csv") {
                submit({ csv: text });
                return;
              }
              const json = JSON.parse(text);
              const rows = Array.isArray(json) ? json : json.orders;
              if (!Array.isArray(rows) || !rows.length)
                throw Error("Informe uma lista com pelo menos um pedido.");
              submit({ orders: rows });
            } catch (e) {
              setError(e instanceof Error ? e.message : "JSON inválido");
            }
          }}
        >
          Importar e conciliar
        </button>
      </section>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
