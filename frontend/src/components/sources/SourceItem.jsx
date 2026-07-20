import { Check } from "lucide-react";
import { FileTypeIcon } from "./fileIcons";

export default function SourceItem({ source, onToggle }) {
  return (
    <div
      onClick={() => onToggle(source.id)}
      className="flex items-start gap-2.5 px-2 py-2.5 rounded-lg cursor-pointer mb-0.5 hover:bg-panelhover"
    >
      <div
        className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 mt-0.5 border-[1.5px] ${
          source.checked ? "bg-indigo border-indigo" : "border-inkfaint bg-transparent"
        }`}
      >
        {source.checked && <Check size={11} strokeWidth={3} className="text-white" />}
      </div>
      <FileTypeIcon type={source.type} size={15} className="text-inkfaint mt-0.5 flex-shrink-0" />
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-ink truncate">{source.name}</div>
        <div className="text-[11px] text-inkfaint font-mono mt-0.5">{source.meta}</div>
      </div>
    </div>
  );
}
