import { useRag } from "../../context/useRag";
import { FileTypeIcon } from "../sources/fileIcons";

export default function SourcePill({ sourceId, onClick }) {
  const { sources } = useRag();
  const src = sources.find((s) => Number(s.id) === Number(sourceId));
  if (!src) return null;

  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-line rounded-lg text-[12.5px] text-inksoft hover:border-inkfaint"
    >
      <FileTypeIcon type={src.type} size={13} className="text-inkfaint" />
      {src.name}
    </button>
  );
}
