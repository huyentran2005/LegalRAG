import { useRag } from "../../context/useRag";
import SourceItem from "./SourceItem";
import UploadButton from "../chat/UploadButton";

export default function SourcesSidebar() {
  const { sources, sourcesLoading, sourcesError, toggleSource, selectAllSources } = useRag();
  const allSelected = sources.length > 0 && sources.every((s) => Boolean(s.checked));

  return (
    <aside className="w-[272px] flex-shrink-0 bg-panel border-r border-line flex flex-col">
      <div className="px-4 pt-4 pb-2.5 flex items-center justify-between">
        <span className="text-[12.5px] font-semibold tracking-wide text-inksoft uppercase">
          Nguồn tài liệu
        </span>
        <UploadButton />
      </div>

      <div className="flex-1 overflow-y-auto px-2.5 no-scrollbar">
        {sourcesLoading && (
          <div className="px-2 py-2 text-xs text-inkfaint">Đang tải nguồn dữ liệu...</div>
        )}
        {sourcesError && (
          <div className="px-2 py-2 text-xs text-[#A32D2D]">{sourcesError}</div>
        )}
        {!sourcesLoading && !sourcesError && sources.length === 0 && (
          <div className="px-2 py-2 text-xs text-inkfaint">Chưa có nguồn dữ liệu.</div>
        )}
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
