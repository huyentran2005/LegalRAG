import { useRag } from "../../context/RagContext";
import { useAutoScroll } from "../../hooks/useAutoScroll";
import MessageBubble from "./MessageBubble";
import ThinkingIndicator from "./ThinkingIndicator";

export default function ChatThread() {
  const { messages, thinking } = useRag();
  const scrollRef = useAutoScroll([messages, thinking]);

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto py-7 no-scrollbar">
      <div className="max-w-[660px] mx-auto px-6">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {thinking && <ThinkingIndicator />}
      </div>
    </div>
  );
}
