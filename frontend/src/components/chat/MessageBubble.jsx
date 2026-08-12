import { useRag } from "../../context/useRag";
import CitationChip from "./CitationChip";
import SourcePill from "./SourcePill";

const URL_RE = /(https?:\/\/[^\s)>\]]+)/g;
const BOLD_RE = /(\*\*[^*]+\*\*)/g;

function TextWithBold({ text }) {
  return String(text || "")
    .split(BOLD_RE)
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={index} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return <span key={index}>{part}</span>;
    });
}

function TextWithLinks({ text }) {
  return String(text || "")
    .split(URL_RE)
    .map((part, index) => {
      if (!part.match(URL_RE)) {
        return <TextWithBold key={index} text={part} />;
      }

      const href = part.replace(/[.,;]+$/, "");
      const trailing = part.slice(href.length);
      return (
        <span key={index}>
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="text-indigo-700 underline decoration-indigo-300 underline-offset-2 break-all hover:text-indigo-dark"
          >
            {href}
          </a>
          {trailing}
        </span>
      );
    });
}

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
      <div className="whitespace-pre-wrap text-[14.5px] leading-[1.7] text-ink">
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
            <TextWithLinks key={i} text={p.text} />
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
