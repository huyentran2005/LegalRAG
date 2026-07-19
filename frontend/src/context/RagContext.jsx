import { createContext, useContext, useCallback, useState } from "react";
import { CITATIONS, SOURCES, INITIAL_MESSAGES } from "../data/mockData";
import { askQuestion } from "../api/client";

const RagContext = createContext(null);

export function RagProvider({children}){
    const [messages, setMessages] = useState(INITIAL_MESSAGES);
    const [sources , setSources] = useState(SOURCES);
    const [activeCite , setActiveCite] = useState(1);
    const [panelOpen, setPanelOpen] = useState(true);
    const [thinking, setThinking] = useState(false);

    const toggleSource = useCallback((id)=>{
        setSources((prev) => prev.map((s) => (s.id === id ? {...s, checked: !Boolean(s.checked)} : s)));
    },[]);
    
    const selectAllSources = useCallback((flag)=>{
        const shouldCheck = flag === true;
        setSources((prev) => prev.map((s) => ({...s, checked: shouldCheck})));
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
            setMessages((prev)=> [...prev, data.message]);
        } catch (_){
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
    },[sources]);

    const value = {
        sources,
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

export function useRag(){
    const ctx = useContext(RagContext);
    if(!ctx){
        throw new Error("useRag must be used within a RagProvider");
    }
    return ctx;
}