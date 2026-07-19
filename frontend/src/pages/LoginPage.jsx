import { useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login, isAuthenticated, error } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const from = location.state?.from?.pathname || "/";

  if (isAuthenticated) return <Navigate to={from} replace />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setSubmitting(true);
    const ok = await login({ email, password });
    setSubmitting(false);
    if (!ok) {
      return;
    }
  };

  return (
    <div className="h-screen w-full flex items-center justify-center bg-paper font-sans px-4">
      <div className="w-full max-w-[380px]">
        <div className="flex items-center gap-2.5 mb-8 justify-center">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center">
              <img
                  src="/chatbot.png"
                  className="w-6 h-6 object-contain"
              />
          </div>
          <span className="font-display text-xl font-semibold">LegalRAG</span>
        </div>

        <div className="bg-white border border-line rounded-card p-7">
          <h1 className="text-[20px] font-display text-lg font-semibold text-ink mb-1 text-center">Đăng nhập</h1>
          <p className="text-[11.5px] text-inksoft mb-6">
            Đăng nhập để xem tài liệu và tiếp tục cuộc trò chuyện của bạn
          </p>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-inksoft mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ban@congty.com"
                className="w-full border border-line rounded-lg px-3 py-2.5 text-sm text-ink outline-none focus:border-indigo"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-inksoft mb-1.5">
                Mật khẩu
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full border border-line rounded-lg px-3 py-2.5 text-sm text-ink outline-none focus:border-indigo"
              />
            </div>

            {error && (
              <div className="text-[13px] text-[#A32D2D] bg-[#FCEBEB] border border-[#F0C0C0] rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-indigo text-white text-sm font-medium rounded-lg py-2.5 mt-1 disabled:opacity-60"
            >
              {submitting ? "Đang đăng nhập…" : "Đăng nhập"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-inkfaint mt-5">
          Chưa có tài khoản?{" "}
          <Link to="/register" className="text-indigo hover:underline">
            Đăng ký
          </Link>
        </p>
      </div>
    </div>
  );
}
