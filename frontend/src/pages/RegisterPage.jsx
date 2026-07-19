import { useState, useCallback } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function RegisterPage() {
  const { register, isAuthenticated, error1 } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const from = location.state?.from?.pathname || "/";

  if (isAuthenticated) return <Navigate to={from} replace />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);

    if (!fullName.trim() || !email.trim() || !password) return;

    if (password.length < 8) {
      setFormError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }
    if (password !== confirmPassword) {
      setFormError("Mật khẩu nhập lại không khớp.");
      return;
    }

    setSubmitting(true);
    const ok = await register({ email, password, fullName });
    setSubmitting(false);
    if (ok) navigate(from, { replace: true });
  };

  const displayError = formError || error1;

  return (
    <div className="h-screen w-full flex items-center justify-center bg-paper font-sans px-4 overflow-y-auto py-8">
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
          <h1 className="font-display text-lg font-semibold text-ink mb-1 text-center">
            Tạo tài khoản
          </h1>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div>
              <label htmlFor="fullName" className="block text-xs font-medium text-inksoft mb-1.5">
                Họ và tên
              </label>
              <input
                id="fullName"
                type="text"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Nguyễn Văn A"
                className="w-full border border-line rounded-full px-4 py-2.5 text-sm text-ink outline-none focus:border-indigo"
              />
            </div>

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
                className="w-full border border-line rounded-full px-4 py-2.5 text-sm text-ink outline-none focus:border-indigo"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-inksoft mb-1.5">
                Mật khẩu
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Tối thiểu 8 ký tự"
                className="w-full border border-line rounded-full px-4 py-2.5 text-sm text-ink outline-none focus:border-indigo"
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-xs font-medium text-inksoft mb-1.5">
                Nhập lại mật khẩu
              </label>
              <input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full border border-line rounded-full px-4 py-2.5 text-sm text-ink outline-none focus:border-indigo"
              />
            </div>

            {displayError && (
              <div className="text-[13px] text-[#A32D2D] bg-[#FCEBEB] border border-[#F0C0C0] rounded-lg px-3 py-2">
                {displayError}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-ink text-white text-sm font-medium rounded-full py-2.5 mt-1 disabled:opacity-60 hover:opacity-90"
            >
              {submitting ? "Đang tạo tài khoản…" : "Tạo tài khoản"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-inkfaint mt-5">
          Đã có tài khoản?{" "}
          <Link to="/login" className="text-indigo hover:underline">
            Đăng nhập
          </Link>
        </p>
      </div>
    </div>
  );
}