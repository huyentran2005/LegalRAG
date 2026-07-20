import { Plus } from "lucide-react";
import { useRag } from "../../context/useRag";
import SourceItem from "./SourceItem";

export default function SourcesSidebar() {
  const { sources, toggleSource, selectAllSources } = useRag();
  const allSelected = sources.length > 0 && sources.every((s) => Boolean(s.checked));

  return (
    <aside className="w-[272px] flex-shrink-0 bg-panel border-r border-line flex flex-col">
      <div className="px-4 pt-4 pb-2.5 flex items-center justify-between">
        <span className="text-[12.5px] font-semibold tracking-wide text-inksoft uppercase">
          Nguồn tài liệu
        </span>
        <button className="flex items-center gap-1 text-xs font-medium text-indigo px-1.5 py-1 hover:opacity-80">
          <Plus size={14} /> Thêm
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 no-scrollbar">
        {sources.map((s) => (
          <SourceItem key={s.id} source={s} onToggle={toggleSource} />
        ))}
      </div>

      <div className="px-4 py-4 border-t border-line">
        <button
          type="button"
          onClick={() => selectAllSources(!allSelected)}
          className="text-xs text-inksoft hover:text-ink"
        >
          {allSelected ? "Bỏ chọn tất cả" : "Chọn tất cả nguồn"}
        </button>
      </div>
    </aside>
  );
}
