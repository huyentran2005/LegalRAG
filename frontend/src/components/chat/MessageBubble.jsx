import { useRag } from "../../context/useRag";
import CitationChip from "./CitationChip";
import SourcePill from "./SourcePill";

export default function MessageBubble({ message }) {
  const { activeCite, panelOpen, openCitation } = useRag();

  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-5">
        <div className="max-w-[78%] bg-indigo-soft text-indigo-dark px-3.5 py-2.5 rounded-2xl rounded-br-[4px] text-[14.5px] leading-relaxed">
          {message.text}
        </div>
      </div>
    );
  }

  const messageCitations = message.citations || {};

  return (
    <div className="mb-5">
      <div className="text-[14.5px] leading-[1.7] text-ink">
        {message.parts.map((p, i) =>
          p.cite ? (
            <CitationChip
              key={i}
              n={Number(p.cite)}
              active={
                panelOpen &&
                activeCite?.messageId === message.id &&
                Number(activeCite?.index) === Number(p.cite)
              }
              onClick={() => openCitation(message.id, p.cite)}
            />
          ) : (
            <span key={i}>{p.text}</span>
          )
        )}
      </div>

      <div className="flex justify-end mt-2">
        <span className="text-xs text-gray-500">
          {message.token} tokens
        </span>
      </div>

      {message.usedSources && (
        <div className="flex gap-1.5 mt-2.5 flex-wrap">
          {message.usedSources.map((sid) => {
            const sourceId = Number(sid);
            const citeEntry = Object.entries(messageCitations).find(
              ([, c]) => Number(c.sourceId) === sourceId
            );
            return (
              <SourcePill
                key={sid}
                sourceId={sourceId}
                onClick={() => citeEntry && openCitation(message.id, Number(citeEntry[0]))}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}