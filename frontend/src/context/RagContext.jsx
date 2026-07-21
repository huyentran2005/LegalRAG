import { useCallback, useEffect, useRef, useState } from "react";
import { CITATIONS, INITIAL_MESSAGES } from "../data/mockData";
import { askQuestion, fetchSources } from "../api/client";
import { RagContext } from "./ragContextValue";

export function RagProvider({children}){
    const wsRef = useRef(null);
    const pendingStatusRef = useRef({});
    const [messages, setMessages] = useState(INITIAL_MESSAGES);
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
            setThinking(false);
            return;
        }
        try{
            const data = await askQuestion({question: trimmed, sourceIds: selectedIds});
            const usedSources = data.sources?.map((source) => source.id) ?? selectedIds;
            setMessages((prev)=> [...prev, {
                id: `a-${Date.now()}`,
                role: "assistant",
                parts: [{text: data.answer || "Không có câu trả lời."}],
                usedSources,
            }]);
        } catch {
            const fallbackSource = sources.find((s)=>s.checked) || sources[0];
            const reply = {
                id: `a-${Date.now()}`,
                role: "assistant",
                parts:[
                    {text: "Dựa trên các nguồn bạ đã chọn, đây là điều tôi tìm thấy lien quan đến câu hỏi của bạn"},
                    {cite: 1},
                    {text: ". Bạn có thể mở nguồn để xem trích dẫn gốc"},
                ],
                usedSources: [fallbackSource.id],
            }
            setMessages((prev)=>[...prev,reply]);
        } finally{
            setThinking(false);
        }
    },[sources, thinking]);

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
        citations: CITATIONS,
        panelOpen,
        closePanel,
    };

    return <RagContext.Provider value = {value}>
        {children}
    </RagContext.Provider>
}
