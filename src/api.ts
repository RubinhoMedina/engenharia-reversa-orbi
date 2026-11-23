export async function api(path: string, body?: unknown) {
  const response = await fetch(
    "/api/" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (response.status === 401 && path !== "auth/login")
    window.dispatchEvent(new Event("orbit-auth-required"));
  if (!response.ok) throw new Error(data.error || "Falha na operação.");
  return data;
}
