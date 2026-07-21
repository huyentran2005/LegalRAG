import { Plus } from "lucide-react";
import { useRef } from "react";
import { uploadSource } from "../../api/client";
import { useRag } from "../../context/useRag";

export default function UploadButton(){
    const {setSources, normalizeSource} = useRag();
    const fileInputRef = useRef(null);

    const handleClick = () => {
        fileInputRef.current.click();
    };
    
    const handleUpload = async(e)=>{
        const file = e.target.files[0];
        if(!file) return ;
        try{
            const data = await uploadSource(file);
            console.log("Upload thành công:", data);
            setSources(
                (prev)=> [...prev, {
                    ...normalizeSource(data)
                }]
            );
        } catch(err){
            console.error("Upload thất bại:", err);
        } finally {
            e.target.value = "";
        }
    }

    return (
        <>
            <button
                onClick={handleClick}
                className="flex items-center gap-1 text-xs font-medium text-indigo px-1.5 py-1 hover:opacity-80"
            >
                <Plus size={14} /> Thêm
            </button>
            <input
                ref = {fileInputRef}
                type="file"
                className="hidden"
                onChange={handleUpload}
            />
        </>
    );
}
