import { useCallback, useEffect, useRef, useState } from "react";
import { askQuestion, fetchSources } from "../api/client";
import { RagContext } from "./ragContextValue";

export function RagProvider({children}){
    const wsRef = useRef(null);
    const pendingStatusRef = useRef({});
    const [messages, setMessages] = useState([]);
    const [citations, setCitations] = useState({});
    const [sessionId, setSessionId] = useState(null);
    const [sources , setSources] = useState([]);
    const [activeCite , setActiveCite] = useState(1);
    const [panelOpen, setPanelOpen] = useState(true);
    const [thinking, setThinking] = useState(false);
    const [sourcesLoading, setSourcesLoading] = useState(false);
    const [sourcesError, setSourcesError] = useState(null);

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

    const openCitation = useCallback((n)=>{
        setActiveCite(n);
        setPanelOpen(true);
    },[]);

    const closePanel = useCallback(() => setPanelOpen(false) ,[]);

    const sendMessage = useCallback(async(text)=>{
        if (thinking) return;
        const trimmed = text.trim();
        if(!trimmed) return;
        const userMsg = {id: `u-${Date.now()}`, role: "user", text: trimmed};
        setMessages((prev) => ([...prev, userMsg]));
        setThinking(true);

        const selectedIds = sources.filter((s)=> s.checked).map((s)=>s.id);
        if (selectedIds.length === 0) {
            setMessages((prev) => [...prev, {
                id: `a-${Date.now()}`,
                role: "assistant",
                parts: [{ text: "Bạn hãy chọn ít nhất một tài liệu ở bên trái trước khi hỏi nhé." }],
                usedSources: [],
            }]);
            setThinking(false);
            return;
        }
        try{
            const data = await askQuestion({question: trimmed, sourceIds: selectedIds, sessionId});
            const usedSources = (data.usedSources ?? data.sources?.map((source) => source.id) ?? selectedIds)
                .map((id) => Number(id));
            const nextCitations = normalizeCitations(data.citations);
            setSessionId(data.sessionId ?? sessionId);
            setCitations(nextCitations);
            const firstCitation = Number(Object.keys(nextCitations)[0]);
            if (firstCitation) {
                setActiveCite(firstCitation);
            }
            setMessages((prev)=> [...prev, {
                id: `a-${Date.now()}`,
                role: "assistant",
                parts: data.parts?.length ? data.parts : [{text: data.answer || "Không có câu trả lời."}],
                usedSources,
            }]);
        } catch (err) {
            console.error(err);
            const detail = err?.response?.data?.detail;
            const message = Array.isArray(detail)
                ? detail.map((item) => item.msg).join(" ")
                : detail;
            const reply = {
                id: `a-${Date.now()}`,
                role: "assistant",
                parts: [{ text: message || "Không tạo được câu trả lời từ tài liệu lúc này. Vui lòng thử lại hoặc kiểm tra backend." }],
                usedSources: [],
            }
            setMessages((prev)=>[...prev,reply]);
        } finally{
            setThinking(false);
        }
    },[sources, thinking, sessionId, normalizeCitations]);

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
        citations,
        panelOpen,
        closePanel,
    };

    return <RagContext.Provider value = {value}>
        {children}
    </RagContext.Provider>
}
