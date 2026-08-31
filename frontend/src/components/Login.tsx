/**
 * 登录 / 注册表单
 * 未登录时由 App 渲染；成功后保存 token 并回调让父组件切换到聊天界面
 */
import { BarChart3 } from "lucide-react";
import { useState } from "react";
import { login, register } from "../lib/agentApi";
import { setToken } from "../lib/auth";

type Props = {
  onLogin: (username: string) => void;
};

export function Login({ onLogin }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const canSubmit = username.trim().length > 0 && password.length > 0 && !loading;

  const submit = async () => {
    if (!canSubmit) return;
    setError("");
    setLoading(true);
    try {
      const action = mode === "login" ? login : register;
      const result = await action(username.trim(), password);
      setToken(result.access_token);
      onLogin(result.username);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative grid h-dvh place-items-center overflow-hidden bg-parchment text-ink">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(90deg,rgba(32,32,29,0.045)_1px,transparent_1px),linear-gradient(rgba(32,32,29,0.035)_1px,transparent_1px)] bg-[size:48px_48px]" />
      <div className="pointer-events-none fixed inset-0 grain" />

      <div className="relative w-full max-w-sm border border-ink/10 bg-[#efe6d8]/90 p-8 backdrop-blur">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center bg-ink text-parchment">
            <BarChart3 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="text-base font-semibold tracking-[0.02em]">NL2SQL</div>
            <div className="text-xs text-ink/50">shopkeeper-agent</div>
          </div>
        </div>

        <h1 className="mb-6 text-lg font-semibold">
          {mode === "login" ? "登录" : "注册"}
        </h1>

        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <label className="grid gap-1.5 text-sm">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-ink/50">
              用户名
            </span>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="border border-ink/15 bg-white/70 px-3 py-2 text-sm outline-none transition focus:border-moss"
              placeholder="至少 3 个字符"
            />
          </label>

          <label className="grid gap-1.5 text-sm">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-ink/50">
              密码
            </span>
            <input
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="border border-ink/15 bg-white/70 px-3 py-2 text-sm outline-none transition focus:border-moss"
              placeholder="至少 6 个字符"
            />
          </label>

          {error ? (
            <p className="text-sm text-red-700" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={!canSubmit}
            className="mt-1 h-11 bg-ink text-sm font-semibold text-parchment transition hover:bg-soot disabled:cursor-not-allowed disabled:bg-ink/35"
          >
            {loading ? "处理中..." : mode === "login" ? "登录" : "注册"}
          </button>
        </form>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError("");
          }}
          className="mt-4 w-full text-center text-sm text-ink/55 transition hover:text-ink"
        >
          {mode === "login" ? "没有账号？去注册" : "已有账号？去登录"}
        </button>
      </div>
    </div>
  );
}
