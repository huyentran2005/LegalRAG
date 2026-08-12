import { useState, useRef ,useEffect} from "react";
import { Send, ChevronDown, Check } from "lucide-react";
import { useRag } from "../../context/useRag";


const MODELS= [
  {id: "gpt-4o",label: "gpt-4o"},
  {id: "gemini-3.6-flash", label: "Gemini 3.6"},
  {id: "qwen2.5:3b", label:"Qwen 2.5"},
];

export default function Composer() {
  const { sendMessage, sources } = useRag();
  const [input, setInput] = useState("");
  const selectedCount = sources.filter((s) => s.checked).length;
  const [open, setOpen] = useState(false);
  const [model, setModel] = useState(MODELS[0]);
  const dropdownRef = useRef(null);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input, model.id);
    setInput("");
  };

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
          <div className="items-center justify-between relative" ref={dropdownRef}>
            <button
              onClick={() => setOpen((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-inkfaint hover:text-ink bg-panel px-2.5 py-1 rounded-lg transition-colors"
            >
              <span>{model.label}</span>
              <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
            </button>

            {open && (
              <div className="absolute bottom-full left-0 mb-1 w-48 bg-white border border-line rounded-[10px] shadow-lg py-1 z-10">
                {MODELS.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => {
                      setModel(m);
                      setOpen(false);
                    }}
                    className="w-full flex items-center justify-between px-3 py-1.5 text-sm text-ink hover:bg-panel"
                  >
                    <span>{m.label}</span>
                    {m.id === model.id && <Check size={13} className="text-indigo" />}
                  </button>
                ))}
              </div>
            )}
          </div>
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
