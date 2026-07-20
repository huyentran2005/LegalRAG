import { X, ExternalLink } from "lucide-react";
import { useRag } from "../../context/useRag";
import { FileTypeIcon } from "../sources/fileIcons";

export default function CitationPanel() {
  const { panelOpen, closePanel, activeCite, citations, sources } = useRag();
  const citation = citations[activeCite];
  const sourceMeta = citation ? sources.find((s) => s.id === citation.sourceId) : null;

  return (
    <aside
      className={`flex-shrink-0 bg-panel overflow-hidden transition-[width] duration-200 ${
        panelOpen ? "w-80 border-l border-line" : "w-0"
      }`}
    >
      <div className="w-80 h-full flex flex-col">
        <div className="px-[18px] py-4 flex items-center justify-between border-b border-line">
          <span className="text-[12.5px] font-semibold tracking-wide text-inksoft uppercase">
            Trích dẫn
          </span>
          <button onClick={closePanel} className="p-1 hover:opacity-70">
            <X size={16} className="text-inkfaint" />
          </button>
        </div>

        {citation && (
          <div className="p-[18px] overflow-y-auto no-scrollbar">
            <div className="flex items-center gap-1.5 mb-3.5">
              <FileTypeIcon type={sourceMeta?.type} size={15} className="text-inkfaint" />
              <span className="text-[13px] font-medium">{citation.sourceName}</span>
            </div>
            <div className="font-mono text-[11px] text-inkfaint mb-3">{citation.page}</div>

            <div className="relative bg-white border border-line rounded-[10px] pl-[18px] pr-4 py-4 -rotate-[0.6deg] shadow-[0_1px_0_rgba(27,29,35,0.03)]">
              <div className="absolute left-0 top-2.5 bottom-2.5 w-[3px] bg-amber rounded" />
              <p
                className="font-display text-[15px] leading-relaxed text-ink m-0"
                style={{
                  backgroundImage: "linear-gradient(#FBF2DD, #FBF2DD)",
                  backgroundRepeat: "no-repeat",
                  backgroundSize: "100% 40%",
                  backgroundPosition: "0 65%",
                }}
              >
                {citation.excerpt}
              </p>
            </div>

            <button className="flex items-center gap-1.5 mt-4 text-[12.5px] text-indigo border border-line rounded-lg px-3 py-2 hover:border-inkfaint">
              <ExternalLink size={13} /> Mở tài liệu gốc
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
