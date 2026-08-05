import { MessageSquare, Plus } from "lucide-react";
import { useRag } from "../../context/useRag";
import { useState } from "react";

export default function SessionList() {
  const { sessions, sessionsLoading, sessionId, selectSession, startNewSession } = useRag();
  const [title, setTitle] = useState("Untitled");
  const[showModal, setShowModal] = useState(false);

  return (
    <div className="border-b border-line">
      <div className="px-4 pt-4 pb-2.5 flex items-center justify-between">
        <span className="text-[12.5px] font-semibold tracking-wide text-inksoft uppercase">
          Hội thoại
        </span>
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="p-1 rounded-md text-indigo hover:bg-panel"
          title="Tạo cuộc chat"
        >
          <Plus size={15} />
        </button>
      </div>
     {showModal && (
          <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
              <div className="w-96 rounded-xl bg-white p-5 shadow-xl">
                  <h2 className="text-lg font-semibold text-ink">
                      Tạo cuộc trò chuyện
                  </h2>

                  <input
                      autoFocus
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Nhập tiêu đề..."
                      className="mt-4 w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-indigo"
                  />

                  <div className="mt-5 flex justify-end gap-2">
                      <button
                          onClick={() => {
                              setShowModal(false);
                              setTitle("");
                          }}
                          className="px-3 py-1.5 text-sm rounded-lg text-inksoft hover:bg-panel"
                      >
                          Hủy
                      </button>

                      <button
                          onClick={async () => {
                              await startNewSession(title);
                              setShowModal(false);
                              setTitle("");
                          }}
                          disabled={!title.trim()}
                          className="px-3 py-1.5 text-sm rounded-lg bg-indigo text-white hover:opacity-90 disabled:bg-panel disabled:text-inkfaint"
                      >
                          Tạo
                      </button>
                  </div>
              </div>
          </div>
      )}

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
