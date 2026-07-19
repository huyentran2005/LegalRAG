import { useRag } from "../../context/RagContext";
import { fileIconFor } from "../sources/SourceItem";

export default function SourcePill({ sourceId, onClick }) {
  const { sources } = useRag();
  const src = sources.find((s) => s.id === sourceId);
  if (!src) return null;
  const Icon = fileIconFor(src.type);

  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-line rounded-lg text-[12.5px] text-inksoft hover:border-inkfaint"
    >
      <Icon size={13} className="text-inkfaint" />
      {src.name}
    </button>
  );
}
