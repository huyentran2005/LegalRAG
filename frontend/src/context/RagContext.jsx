import { useCallback, useEffect, useRef, useState } from "react";
import { askQuestion, fetchSources , fetchMessages} from "../api/client";
import { RagContext } from "./ragContextValue";
import {useAuth} from "./useAuth"

export function RagProvider({children}){
    const { token } = useAuth();
    const wsRef = useRef(null);
    const pendingStatusRef = useRef({});
    const [messages, setMessages] = useState([]);
    const [sessionId, setSessionId] = useState(null);
    const [sources , setSources] = useState([]);
    const [activeCite , setActiveCite] = useState(null);
    const [panelOpen, setPanelOpen] = useState(true);
    const [thinking, setThinking] = useState(false);
    const [sourcesLoading, setSourcesLoading] = useState(false);
    const [sourcesError, setSourcesError] = useState(null);
    const [historyLoading, setHistoryLoading] = useState(false);

    const normalizeSource = useCallback((source) => ({
        id: source.id ?? source.document_id,
        documentId: source.document_id ?? source.id,
        objectKey: source.object_key ?? source.objectKey,
        name: source.name ?? source.filename ?? "Tài liệu",
        meta: source.meta ?? (source.page_count ? `${source.page_count} trang` : ""),
        type: source.type ?? source.file_type ?? "application/pdf",
        status: typeof source.status === "string" ? source.status : source.status?.value,
        checked: source.checked ?? true,
    }), []);

    const normalizeCitations = useCallback((rawCitations) => {
        if (!rawCitations || typeof rawCitations !== "object") return {};

        return Object.fromEntries(
            Object.entries(rawCitations).map(([key, citation]) => [
                Number(key),
                {
                    ...citation,
                    sourceId: Number(citation.sourceId ?? citation.source_id),
                    sourceName: citation.sourceName ?? citation.source_name ?? "Tài liệu",
                    page: citation.page ?? "",
                    excerpt: citation.excerpt ?? "",
                },
            ])
        );
    }, []);

    const toggleSource = useCallback((id)=>{
        setSources((prev) => prev.map((s) => (s.id === id ? {...s, checked: !s.checked} : s)));
    },[]);
    
    const selectAllSources = useCallback((flag)=>{
        const shouldCheck = flag === true;
        setSources((prev) => prev.map((s) => ({...s, checked: shouldCheck})));
    },[]);

    const getSource = useCallback(async()=>{
        setSourcesLoading(true);
        setSourcesError(null);
        try{
            const data = await fetchSources();
            const normalized = Array.isArray(data)
                ? data.map((item) => {
                    const source = normalizeSource(item);
                    const pendingStatus = pendingStatusRef.current[source.documentId ?? source.id];
                    return pendingStatus ? { ...source, status: pendingStatus } : source;
                })
                : [];
            setSources(normalized);
            localStorage.setItem(
                "sources",
                JSON.stringify(normalized)
            );
        }catch(err){
            console.error(err);
            setSourcesError(err?.response?.data?.detail || "Không tải được danh sách nguồn dữ liệu.");
        } finally {
            setSourcesLoading(false);
        }
    },[normalizeSource]);

    useEffect(() => {
        getSource();
    }, [getSource]);

    const loadAllMessages = useCallback(async () => {
        if (!token) {
            setMessages([]); 
            return;
        }
        setHistoryLoading(true);
        try {
            const data = await fetchMessages();
            if (!Array.isArray(data) || data.length === 0) return;

            const restored = data.map((m) =>
                m.role === "user"
                    ? { id: `u-${m.id}`, role: "user", text: m.text }
                    : {
                        id: `a-${m.id}`,
                        role: "assistant",
                        parts: m.parts?.length ? m.parts : [{ text: m.text || "Không có câu trả lời." }],
                        usedSources: m.usedSources ?? [],
                        citations: normalizeCitations(m.citations),
                    }
            );
            setMessages(restored);
            setSessionId(data[data.length - 1].sessionId);
        } catch (err) {
            console.error("Không tải được lịch sử chat:", err);
        } finally {
            setHistoryLoading(false);
        }
    }, [normalizeCitations, token]);

    useEffect(() => { loadAllMessages(); }, [loadAllMessages]);

    useEffect(()=>{
        const token = localStorage.getItem("auth_token");
        if(!token) return;

        function connect(){
            const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || "ws://localhost:8000";
            const ws = new WebSocket(`${wsBaseUrl}/ws/documents?token=${encodeURIComponent(token)}`);
            wsRef.current = ws;

            ws.onmessage = (event) =>{
                try {
                    const data = JSON.parse(event.data);
                    const documentId = data.document_id ?? data.documentId ?? data.id;
                    const status = data.status ?? data.state;

                    if (documentId == null || status == null) return;

                    pendingStatusRef.current[documentId] = status;
                    setSources((prev) =>
                        prev.map((s) => {
                            const sourceId = s.documentId ?? s.id;
                            return sourceId === documentId ? { ...s, status } : s;
                        })
                    );
                } catch (err) {
                    console.error("WS payload error", err);
                }
            };

            ws.onclose = (event)=>{
                if(event.code === 1008){
                    console.warn("Token không hợp lệ!, không reconnect");
                    return ;
                }
                setTimeout(connect, 2000);
            }

            ws.onerror = () => ws.close();
        }

        connect();
        return () => wsRef.current?.close();
    },[]);

    const openCitation = useCallback((messageId, citationIndex) => {
        setActiveCite({ messageId, index: Number(citationIndex) });
        setPanelOpen(true);
    }, []);

    const closePanel = useCallback(() => setPanelOpen(false) ,[]);

    const sendMessage = useCallback(async (text, provider) => {
        if (thinking) return;
        const trimmed = text.trim();
        if (!trimmed) return;
        const userMsg = { id: `u-${Date.now()}`, role: "user", text: trimmed };
        setMessages((prev) => [...prev, userMsg]);
        setThinking(true);

        const selectedIds = sources.filter((s) => s.checked).map((s) => s.id);
        if (selectedIds.length === 0) {
            setMessages((prev) => [...prev, {
                id: `a-${Date.now()}`,
                role: "assistant",
                parts: [{ text: "Bạn hãy chọn ít nhất một tài liệu ở bên trái trước khi hỏi nhé." }],
                usedSources: [],
                citations: {},
            }]);
            setThinking(false);
            return;
        }
        try {
            const data = await askQuestion({ question: trimmed, sourceIds: selectedIds, sessionId, provider });
            const usedSources = (data.usedSources ?? data.sources?.map((source) => source.id) ?? selectedIds)
                .map((id) => Number(id));
            const nextCitations = normalizeCitations(data.citations);   
            setSessionId(data.sessionId ?? sessionId);

            const newMessageId = `a-${Date.now()}`;                    
            const firstCitationIndex = Number(Object.keys(nextCitations)[0]);
            if (firstCitationIndex) {
                setActiveCite({ messageId: newMessageId, index: firstCitationIndex });
            }

            setMessages((prev) => [...prev, {
                id: newMessageId,
                role: "assistant",
                parts: data.parts?.length ? data.parts : [{ text: data.answer || "Không có câu trả lời." }],
                usedSources,
                citations: nextCitations,   
            }]);
        } catch (err) {
            console.error(err);
            const detail = err?.response?.data?.detail;
            const message = Array.isArray(detail)
                ? detail.map((item) => item.msg).join(" ")
                : detail;
            setMessages((prev) => [...prev, {
                id: `a-${Date.now()}`,
                role: "assistant",
                parts: [{ text: message || "Không tạo được câu trả lời từ tài liệu lúc này. Vui lòng thử lại hoặc kiểm tra backend." }],
                usedSources: [],
                citations: {},
            }]);
        } finally {
            setThinking(false);
        }
    }, [sources, thinking, sessionId, normalizeCitations]);

    const value = {
        sources,
        setSources,
        normalizeSource,
        getSource,
        sourcesLoading,
        sourcesError,
        toggleSource,
        selectAllSources,
        messages,
        sendMessage,
        thinking,
        activeCite,
        openCitation,
        panelOpen,
        closePanel,
        historyLoading,
    };

    return <RagContext.Provider value = {value}>
        {children}
    </RagContext.Provider>
}
