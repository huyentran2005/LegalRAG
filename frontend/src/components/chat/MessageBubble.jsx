import { useRag } from "../../context/RagContext";
import CitationChip from "./CitationChip";
import SourcePill from "./SourcePill";

export default function MessageBubble({ message }) {
  const { activeCite, panelOpen, openCitation, citations } = useRag();

  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-5">
        <div className="max-w-[78%] bg-indigo-soft text-indigo-dark px-3.5 py-2.5 rounded-2xl rounded-br-[4px] text-[14.5px] leading-relaxed">
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div className="mb-5">
      <div className="text-[14.5px] leading-[1.7] text-ink">
        {message.parts.map((p, i) =>
          p.cite ? (
            <CitationChip
              key={i}
              n={p.cite}
              active={panelOpen && activeCite === p.cite}
              onClick={openCitation}
            />
          ) : (
            <span key={i}>{p.text}</span>
          )
        )}
      </div>

      {message.usedSources && (
        <div className="flex gap-1.5 mt-2.5 flex-wrap">
          {message.usedSources.map((sid) => {
            const citeEntry = Object.entries(citations).find(([, c]) => c.sourceId === sid);
            return (
              <SourcePill
                key={sid}
                sourceId={sid}
                onClick={() => citeEntry && openCitation(Number(citeEntry[0]))}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
