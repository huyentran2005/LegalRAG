export default function CitationChip({n, active, onClick}){
    return (
        <button
            onClick = {()=> onClick(n)}
            className={`inline-flex items-center justify-center min-w-[18px] h-[18px] px-1.5 mx-0.5 -translate-y-px
                font-mono text-[11px] font-medium rounded border border-amber transition-colors
                ${active ? "bg-amber text-white" : "bg-amber-soft text-amber hover:bg-[#F0DBAA]"}`}
        >
            {n}
        </button>
    )
}