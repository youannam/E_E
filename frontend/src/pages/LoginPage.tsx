import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { api } from "../api/client";

export function LoginPage() {
  const { login, notice } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);
  const [completeResetMode, setCompleteResetMode] = useState(false);
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [forgotMessage, setForgotMessage] = useState<string | null>(null);
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try { return localStorage.getItem("eagle-eye-theme") === "dark" ? "dark" : "light"; }
    catch { return "light"; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("eagle-eye-theme", theme); } catch { /* storage may be disabled */ }
  }, [theme]);

  useEffect(() => {
    if (!awaitingApproval || !username.trim()) return;
    let cancelled = false;
    const checkStatus = async () => {
      try {
        const result = await api.get<{ status: string }>(`/password-reset-requests/status?username=${encodeURIComponent(username.trim())}`);
        if (cancelled) return;
        if (result.status === "APPROVED") {
          setAwaitingApproval(false);
          setCompleteResetMode(true);
          setForgotMode(false);
          setForgotMessage("Your request was approved. Enter the temporary password sent to your email and choose a new password.");
        } else if (result.status === "REJECTED") {
          setAwaitingApproval(false);
          setForgotMessage("Your password reset request was rejected. Please contact the administrator.");
        }
      } catch { /* transient connection errors are retried on the next poll */ }
    };
    const timer = window.setInterval(checkStatus, 2500);
    void checkStatus();
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [awaitingApproval, username]);

  async function handleForgotSubmit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim()) {
      setForgotMessage("Enter your username or email, then contact your administrator to verify your identity.");
      return;
    }
    try {
      await api.post<{ message: string }>("/password-reset-requests", { username: username.trim() });
      setAwaitingApproval(true);
      setForgotMessage("Your request was sent. Waiting for administrator approval… This page will open the password-change form automatically after approval.");
    } catch (err) { setForgotMessage((err as Error).message); }
  }

  async function handleCompleteReset(event: FormEvent) {
    event.preventDefault(); setForgotMessage(null); setError(null);
    if (!username.trim() || !temporaryPassword || newPassword.length < 10 || newPassword !== confirmPassword) {
      setForgotMessage(newPassword !== confirmPassword ? "New password and confirmation do not match." : "Enter your username, temporary password, and a new password of at least 10 characters."); return;
    }
    setBusy(true);
    try {
      const result = await api.post<{message:string}>("/password-reset-requests/complete", {username: username.trim(), temporary_password: temporaryPassword, new_password: newPassword, confirm_password: confirmPassword});
      setForgotMessage(result.message); setTemporaryPassword(""); setNewPassword(""); setConfirmPassword("");
      setCompleteResetMode(false); setForgotMode(false);
    } catch (err) { setForgotMessage((err as Error).message); }
    finally { setBusy(false); }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <button className="button button-theme login-theme" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
        {theme === "dark" ? "☀ Light mode" : "☾ Dark mode"}
      </button>
      <form className="login-form" onSubmit={completeResetMode ? handleCompleteReset : forgotMode ? handleForgotSubmit : handleSubmit} noValidate>
        <div className="brand brand-large">
          <img src="/eagle-eye-icon.svg" alt="" aria-hidden="true" className="brand-mark" />
          <span>Eagle Eye</span>
        </div>
        <p className="muted">{completeResetMode ? "Use the temporary password from your email to set a new password." : forgotMode ? "Request a password reset. An administrator must review and approve it." : "Insider threat detection for security analysts."}</p>

        {notice && <p className="form-notice">{notice}</p>}

        <label htmlFor="username">Username or email</label>
        <input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)}
               autoFocus />

        {!forgotMode && !completeResetMode && <>
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </>}

        {completeResetMode && <>
          <label htmlFor="temporary-password">Temporary password</label>
          <input id="temporary-password" type="password" autoComplete="one-time-code" value={temporaryPassword} onChange={(e) => setTemporaryPassword(e.target.value)} />
          <label htmlFor="new-password">New password (10+ characters)</label>
          <input id="new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          <label htmlFor="confirm-password">Confirm new password</label>
          <input id="confirm-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
        </>}
        {forgotMessage && <p className="form-notice" role="status">{forgotMessage}</p>}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <button className="button button-wide" type="submit" disabled={busy || awaitingApproval}>
          {completeResetMode ? (busy ? "Changing password…" : "Change password") : forgotMode ? (awaitingApproval ? "Waiting for approval…" : "Request password reset") : busy ? "Logging in…" : "Log in"}
        </button>
        <p style={{ textAlign: "center", marginTop: 16 }}>
          <button className="button button-ghost" type="button" onClick={() => { if (forgotMode || completeResetMode) { setForgotMode(false); setCompleteResetMode(false); setAwaitingApproval(false); } else { setForgotMode(true); } setError(null); setForgotMessage(null); }}>
            {completeResetMode ? "Back to log in" : forgotMode ? "Back to log in" : "Forgot password?"}
          </button>
        </p>
        {!completeResetMode && !awaitingApproval && <p style={{ textAlign: "center", marginTop: 8 }}>
          <button className="button button-ghost" type="button" onClick={() => { setCompleteResetMode(true); setForgotMode(false); setError(null); setForgotMessage(null); }}>
            I have a temporary password
          </button>
        </p>}
      </form>
    </div>
  );
}
