import { MessageSquare, Plus } from "lucide-react";
import { useRag } from "../../context/useRag";

export default function SessionList() {
  const { sessions, sessionsLoading, sessionId, selectSession, startNewSession } = useRag();

  return (
    <div className="border-b border-line">
      <div className="px-4 pt-4 pb-2.5 flex items-center justify-between">
        <span className="text-[12.5px] font-semibold tracking-wide text-inksoft uppercase">
          Hội thoại
        </span>
        <button
          type="button"
          onClick={startNewSession}
          className="p-1 rounded-md text-indigo hover:bg-panel"
          title="Tạo cuộc chat"
        >
          <Plus size={15} />
        </button>
      </div>

      <div className="max-h-[220px] overflow-y-auto px-2.5 pb-2 no-scrollbar">
        {sessionsLoading && (
          <div className="px-2 py-2 text-xs text-inkfaint">Đang tải đoạn chat...</div>
        )}
        {!sessionsLoading && sessions.length === 0 && (
          <div className="px-2 py-2 text-xs text-inkfaint">Chưa có đoạn chat.</div>
        )}
        {sessions.map((session) => {
          const active = Number(session.id) === Number(sessionId);
          return (
            <button
              key={session.id}
              type="button"
              onClick={() => selectSession(session.id)}
              className={`w-full flex items-start gap-2 px-2 py-2 rounded-lg text-left mb-0.5 ${
                active ? "bg-indigo-soft text-indigo-dark" : "hover:bg-panelhover text-ink"
              }`}
            >
              <MessageSquare size={15} className="mt-0.5 flex-shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium truncate">{session.title}</span>
                <span className="block text-[11px] text-inkfaint font-mono mt-0.5">
                  {session.documentCount} tài liệu
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
