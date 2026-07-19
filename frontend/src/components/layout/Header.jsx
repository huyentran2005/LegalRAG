import { Sparkles, LogOut } from "lucide-react";
import { useRag } from "../../context/RagContext";
import { useAuth } from "../../context/AuthContext";

export default function Header() {
  const { sources } = useRag();
  const { user, logout } = useAuth();
  const selectedCount = sources.filter((s) => s.checked).length;
  const initials = (user?.name || user?.email || "?").slice(0, 2).toUpperCase();

  return (
    <header className="h-14 flex-shrink-0 flex items-center justify-between px-5 border-b border-line bg-paper">
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-[7px] bg-ink flex items-center justify-center">
          <span className="font-display text-paper text-[15px] font-semibold">M</span>
        </div>
        <div>
          <div className="font-display text-base font-semibold leading-none">Margin</div>
          <div className="text-[11px] text-inkfaint mt-0.5">Không gian làm việc RAG</div>
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
