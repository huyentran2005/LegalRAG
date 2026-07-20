import { useContext } from "react";
import { RagContext } from "./ragContextValue";

export function useRag(){
    const ctx = useContext(RagContext);
    if(!ctx){
        throw new Error("useRag must be used within a RagProvider");
    }
    return ctx;
}
