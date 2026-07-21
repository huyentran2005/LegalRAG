import { Sparkles, LogOut } from "lucide-react";
import { useRag } from "../../context/useRag";
import { useAuth } from "../../context/useAuth";

export default function Header() {
  const { sources } = useRag();
  const { user, logout } = useAuth();
  const selectedCount = (sources ?? []).filter((s) => Boolean(s.checked)).length;
  const displayName = user?.full_name || user?.name || "";
  const initials = displayName
    ? displayName
        .trim()
        .split(/\s+/)
        .slice(-2)
        .map((s) => s[0])
        .join("")
        .toUpperCase()
    : (user?.email || "?").slice(0, 2).toUpperCase();

    
  return (
    <header className="h-14 flex-shrink-0 flex items-center justify-between px-5 border-b border-line bg-paper">
      <div className="flex items-center gap-2.5">
        <div className="w-10 h-10 rounded-xl bg-white shadow-sm border border-line flex items-center justify-center">
          <img
            src="/chatbot.png"
            alt="LegalRAG Logo"
            className="w-7 h-7 object-contain"
            onClick={() => window.location.reload()}
          />
        </div>
        <div>
          <div className="font-display text-base font-semibold leading-none">LegalRAG</div>
          <div className="text-[11px] text-inkfaint mt-0.5">Không gian làm việc</div>
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        <div className="flex items-center gap-1.5 text-xs text-inksoft bg-panel px-3 py-1.5 rounded-lg font-mono">
          <Sparkles size={13} className="text-indigo" />
          {selectedCount}/{sources.length} nguồn đang dùng
        </div>

        <div className="w-px h-5 bg-line mx-1" />

        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-indigo-soft text-indigo-dark text-[11px] font-medium flex items-center justify-center">
            {initials}
          </div>
          <button
            onClick={logout}
            title="Đăng xuất"
            className="p-1.5 rounded-lg text-inkfaint hover:text-ink hover:bg-panel"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </header>
  );
}
