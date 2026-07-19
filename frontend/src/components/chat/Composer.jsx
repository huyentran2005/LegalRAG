import { useState } from "react";
import { Send } from "lucide-react";
import { useRag } from "../../context/RagContext";

export default function Composer() {
  const { sendMessage, sources } = useRag();
  const [input, setInput] = useState("");
  const selectedCount = sources.filter((s) => s.checked).length;

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input);
    setInput("");
  };

  return (
    <div className="border-t border-line px-6 pt-4 pb-5">
      <div className="max-w-[660px] mx-auto">
        <div className="flex items-end gap-2 bg-white border border-line rounded-[14px] pl-4 pr-2 py-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Hỏi bất cứ điều gì về tài liệu của bạn…"
            rows={1}
            className="flex-1 resize-none border-none outline-none bg-transparent text-sm leading-relaxed text-ink py-1.5 max-h-[120px]"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className={`w-8 h-8 rounded-[9px] flex items-center justify-center flex-shrink-0 ${
              input.trim() ? "bg-indigo cursor-pointer" : "bg-panel cursor-default"
            }`}
          >
            <Send size={14} className={input.trim() ? "text-white" : "text-inkfaint"} />
          </button>
        </div>
        <div className="text-[11px] text-inkfaint mt-2 text-center">
          Câu trả lời được trích dẫn từ {selectedCount} nguồn đang chọn ở bên trái.
        </div>
      </div>
    </div>
  );
}
